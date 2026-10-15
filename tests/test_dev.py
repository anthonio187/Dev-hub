"""Tests for developer integrations. Network calls are mocked so these run offline."""

import os
import re
import sys
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if not os.environ.get("DATABASE_URL"):
    import tempfile
    os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "dev.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as appmod  # noqa: E402
import devint  # noqa: E402
from devint import ProviderError  # noqa: E402

def _em(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower()) + '@example.com'

HDR = {"X-Requested-With": "XMLHttpRequest"}


def fake_profile(provider, handle):
    if handle.startswith("ghost"):
        raise ProviderError("not_found")
    if handle.startswith("down"):
        raise ProviderError("unreachable")
    return {"name": handle.title(), "bio": "", "url": f"https://example.test/{handle}",
            "avatar_url": None, "followers": 3, "public_repos": 2, "total_stars": 7,
            "languages": [{"name": "Python", "repos": 2}], "top_repos": [
                {"name": "tool", "url": "https://github.com/x/tool", "description": "A tool",
                 "stars": 7, "language": "Python"}]}


@pytest.fixture(autouse=True)
def mocks(monkeypatch):
    appmod._RATE.clear()
    state = {"bio": ""}
    monkeypatch.setattr(devint, "fetch_profile", fake_profile)
    monkeypatch.setattr(devint, "github_bio", lambda handle: state["bio"])
    monkeypatch.setattr(devint, "github_repo", lambda owner, name: {
        "kind": "github_repo", "full_name": f"{owner}/{name}", "url": f"https://github.com/{owner}/{name}",
        "description": "Repo desc", "stars": 42, "forks": 3, "language": "Go", "owner_avatar": None})
    return state


@pytest.fixture()
def factory():
    return lambda: appmod.app.test_client()


def new_user(factory):
    c = factory()
    name = "dev" + uuid.uuid4().hex[:9]
    r = c.post("/api/auth/signup", json={"username": name, "email": _em(name), "password": "password123"}, headers=HDR)
    assert r.status_code == 201
    return c, name


def test_providers_list(factory):
    c = factory()
    ids = [p["id"] for p in c.get("/api/devs/providers").get_json()["providers"]]
    assert ids == ["github", "gitlab", "devto", "npm"]


def test_github_link_requires_bio_verification(factory, mocks):
    c, _ = new_user(factory)
    handle = "gh" + uuid.uuid4().hex[:6]
    r = c.post("/api/me/dev/github", json={"handle": "@" + handle}, headers=HDR)
    assert r.status_code == 201, r.get_json()
    acc = r.get_json()["accounts"]["github"]
    assert acc["verified"] is False
    code = acc["verify_code"]
    assert code.startswith("devx-")

    # bio without the code is rejected
    mocks["bio"] = "I love Python"
    r = c.post("/api/me/dev/github/verify", headers=HDR)
    assert r.status_code == 400 and code in r.get_json()["error"]

    # once the code is in the bio, verification succeeds and the code is removed
    mocks["bio"] = f"Backend dev. {code}"
    r = c.post("/api/me/dev/github/verify", headers=HDR)
    assert r.status_code == 200
    acc = r.get_json()["accounts"]["github"]
    assert acc["verified"] is True and "verify_code" not in acc
    assert acc["data"]["languages"][0]["name"] == "Python"


def test_invalid_and_missing_handles(factory):
    c, _ = new_user(factory)
    assert c.post("/api/me/dev/github", json={"handle": "bad handle!"}, headers=HDR).status_code == 400
    assert c.post("/api/me/dev/github", json={"handle": "-leading"}, headers=HDR).status_code == 400
    assert c.post("/api/me/dev/npm", json={"handle": "UPPER"}, headers=HDR).status_code == 400
    r = c.post("/api/me/dev/github", json={"handle": "ghost123"}, headers=HDR)
    assert r.status_code == 404 and "ghost123" in r.get_json()["error"]
    r = c.post("/api/me/dev/github", json={"handle": "down-host"}, headers=HDR)
    assert r.status_code == 502
    assert c.post("/api/me/dev/myspace", json={"handle": "x"}, headers=HDR).status_code == 404


def test_github_handle_cannot_be_claimed_twice(factory, mocks):
    a, _ = new_user(factory)
    b, _ = new_user(factory)
    handle = "shared" + uuid.uuid4().hex[:5]
    code = a.post("/api/me/dev/github", json={"handle": handle}, headers=HDR).get_json()["accounts"]["github"]["verify_code"]
    mocks["bio"] = code
    assert a.post("/api/me/dev/github/verify", headers=HDR).status_code == 200
    r = b.post("/api/me/dev/github", json={"handle": handle}, headers=HDR)
    assert r.status_code == 409


def test_gitlab_npm_devto_link_show_on_profile_and_hide_secrets(factory):
    owner, name = new_user(factory)
    viewer, _ = new_user(factory)
    for prov, handle in (("gitlab", "gl" + uuid.uuid4().hex[:5]), ("devto", "dt" + uuid.uuid4().hex[:5]), ("npm", "np" + uuid.uuid4().hex[:5])):
        r = owner.post(f"/api/me/dev/{prov}", json={"handle": handle}, headers=HDR)
        assert r.status_code == 201, (prov, r.get_json())
        assert r.get_json()["accounts"][prov]["handle"] == handle
    r = owner.post("/api/me/dev/npm/verify", headers=HDR)
    assert r.status_code == 400  # npm doesn't need verification

    prof = viewer.get(f"/api/users/{name}").get_json()["dev"]
    assert set(prof["accounts"]) == {"gitlab", "devto", "npm"}
    assert all("verify_code" not in a for a in prof["accounts"].values())

    r = owner.delete("/api/me/dev/npm", headers=HDR)
    assert "npm" not in r.get_json()["accounts"]


def test_verify_code_only_visible_to_owner(factory, mocks):
    c, name = new_user(factory)
    handle = "priv" + uuid.uuid4().hex[:5]
    c.post("/api/me/dev/github", json={"handle": handle}, headers=HDR)
    other, _ = new_user(factory)
    prof = other.get(f"/api/users/{name}").get_json()["dev"]
    assert "github" in prof["accounts"] and "verify_code" not in prof["accounts"]["github"]
    mine = c.get("/api/me/dev").get_json()["accounts"]["github"]
    assert mine["verify_code"].startswith("devx-")


def test_availability_and_directory_filters(factory):
    c, name = new_user(factory)
    r = c.patch("/api/me", json={"open_to_work": True, "available_for": "Remote contract work", "tech": "Python, Postgres"}, headers=HDR)
    assert r.status_code == 200
    prof = c.get(f"/api/users/{name}").get_json()
    assert prof["dev"]["open_to_work"] is True
    assert prof["dev"]["available_for"] == "Remote contract work"

    d = c.get("/api/devs?tech=postgres").get_json()["users"]
    assert any(u["username"] == name for u in d)
    assert c.get("/api/devs?tech=rust").get_json()["users"] == [] or all(u["username"] != name for u in c.get("/api/devs?tech=rust").get_json()["users"])
    avail = c.get("/api/devs?available=1").get_json()["users"]
    assert avail and all(u["dev"]["open_to_work"] for u in avail)
    assert any(u["username"] == name for u in avail)

    c.patch("/api/me", json={"open_to_work": False}, headers=HDR)
    assert c.get(f"/api/users/{name}").get_json()["dev"]["open_to_work"] is False


def test_stale_refresh_failure_keeps_last_good_data(factory, monkeypatch):
    c, name = new_user(factory)
    c.post("/api/me/dev/gitlab", json={"handle": "stale" + uuid.uuid4().hex[:4]}, headers=HDR)
    # force the stored data to look old
    d = appmod.dbm.Conn()
    d.execute("UPDATE dev_accounts SET fetched_at = '2000-01-01T00:00:00+00:00' WHERE user_id = ?",
              (c.get("/api/auth/me").get_json()["user"]["id"],))
    d.commit()
    d.close()

    def boom(provider, handle):
        raise ProviderError("rate_limited")
    monkeypatch.setattr(devint, "fetch_profile", boom)
    acc = c.get(f"/api/users/{name}").get_json()["dev"]["accounts"]["gitlab"]
    assert acc["error"] == "rate_limited"
    assert acc["data"]["name"]  # last good data survives


def test_link_preview_github_repo(factory):
    c = factory()
    r = c.get("/api/link-preview?url=" + "https://github.com/psf/requests").get_json()["preview"]
    assert r["full_name"] == "psf/requests" and r["stars"] == 42
    assert c.get("/api/link-preview?url=https://example.com/x").get_json()["preview"] is None
    assert c.get("/api/link-preview?url=https://github.com/a/b/c").get_json()["preview"] is None
    assert c.get("/api/link-preview?url=javascript:alert(1)").get_json()["preview"] is None


def test_parse_github_repo_url():
    assert devint.parse_github_repo_url("https://github.com/psf/requests") == ("psf", "requests")
    assert devint.parse_github_repo_url("https://github.com/psf/requests.git/") == ("psf", "requests")
    assert devint.parse_github_repo_url("https://github.com/psf") is None
    assert devint.parse_github_repo_url("http://github.com/psf/requests") is None
    assert devint.parse_github_repo_url("https://github.com/psf/..") is None


def test_health_reports_ok(factory):
    r = factory().get("/api/health")
    assert r.status_code == 200 and r.get_json()["ok"] is True
