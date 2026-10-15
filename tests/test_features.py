"""Tests for DevHub-scope features: password reset, post editing, files and
attachments (with an S3-compatible fake), projects, collaboration requests,
notifications with links, and search. Run with:  pytest -q
"""

import io
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if not os.environ.get("DATABASE_URL"):
    os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "features.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as appmod  # noqa: E402

HDR = {"X-Requested-With": "XMLHttpRequest"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n% test document\n"
ZIP = b"PK\x03\x04" + b"\x00" * 40


def _em(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower()) + "@example.com"


def uname(prefix="ft"):
    return (prefix + uuid.uuid4().hex[:8])[:15]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    appmod._RATE.clear()
    sent = []
    monkeypatch.setattr(appmod, "send_email", lambda to, subj, text: sent.append((to, subj, text)) or True)
    monkeypatch.delenv("S3_BUCKET", raising=False)
    yield {"sent": sent}


def signup(c, name=None, password="password123"):
    name = name or uname()
    r = c.post("/api/auth/signup", json={"username": name, "email": _em(name), "password": password}, headers=HDR)
    assert r.status_code == 201, r.get_json()
    return name


def user(factory):
    c = factory()
    return c, signup(c)


def upload(c, data, filename):
    return c.post("/api/media", data={"file": (io.BytesIO(data), filename)}, headers=HDR,
                  content_type="multipart/form-data")


@pytest.fixture()
def factory():
    return appmod.app.test_client


# --------------------------------------------------------------------------- #
# Accounts: email, login by email, password reset
# --------------------------------------------------------------------------- #
def test_signup_requires_valid_unique_email(factory):
    c = factory()
    base = {"username": uname(), "password": "password123"}
    assert c.post("/api/auth/signup", json={**base, "email": "not-an-email"}, headers=HDR).status_code == 400
    assert c.post("/api/auth/signup", json={**base}, headers=HDR).status_code == 400
    name = signup(c)
    dup = factory().post("/api/auth/signup", json={"username": uname(), "email": _em(name).upper(),
                                                   "password": "password123"}, headers=HDR)
    assert dup.status_code == 409


def test_login_accepts_username_or_email_and_returns_private_email(factory):
    c = factory()
    name = signup(c)
    by_email = factory().post("/api/auth/login", json={"username": _em(name), "password": "password123"}, headers=HDR)
    assert by_email.status_code == 200
    assert by_email.get_json()["user"]["email"] == _em(name)
    # Other users must not see the email on public profiles.
    other, _ = user(factory)
    prof = other.get("/api/users/" + name).get_json()
    assert "email" not in prof.get("user", prof)


def test_password_reset_full_flow(factory, _env):
    c, name = user(factory)
    r = factory().post("/api/auth/forgot", json={"email": _em(name)}, headers=HDR)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert _env["sent"], "a reset email should have been sent"
    to, subject, text = _env["sent"][-1]
    assert to == _em(name)
    token = re.search(r"reset\?token=([A-Za-z0-9_\-]+)", text).group(1)

    bad = factory().post("/api/auth/reset", json={"token": "nope", "password": "newpassword1"}, headers=HDR)
    assert bad.status_code == 400
    ok = factory().post("/api/auth/reset", json={"token": token, "password": "newpassword1"}, headers=HDR)
    assert ok.status_code == 200
    # Single use.
    again = factory().post("/api/auth/reset", json={"token": token, "password": "another123"}, headers=HDR)
    assert again.status_code == 400
    assert factory().post("/api/auth/login", json={"username": name, "password": "password123"},
                          headers=HDR).status_code == 401
    assert factory().post("/api/auth/login", json={"username": name, "password": "newpassword1"},
                          headers=HDR).status_code == 200


def test_forgot_password_reveals_nothing_about_unknown_emails(factory, _env):
    before = len(_env["sent"])
    r = factory().post("/api/auth/forgot", json={"email": "nobody-here@example.com"}, headers=HDR)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert len(_env["sent"]) == before  # nothing sent, same response


def test_expired_reset_token_is_rejected(factory, _env):
    c, name = user(factory)
    factory().post("/api/auth/forgot", json={"email": _em(name)}, headers=HDR)
    token = re.search(r"reset\?token=([A-Za-z0-9_\-]+)", _env["sent"][-1][2]).group(1)
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="microseconds")
    d = appmod.dbm.Conn()
    d.execute("UPDATE password_resets SET expires_at = ? WHERE token_hash = ?", (past, appmod._hash_token(token)))
    d.commit()
    d.close()
    r = factory().post("/api/auth/reset", json={"token": token, "password": "newpassword1"}, headers=HDR)
    assert r.status_code == 400


def test_profile_email_and_linkedin_validation(factory):
    c, name = user(factory)
    assert c.patch("/api/me", json={"linkedin": "https://example.com/me"}, headers=HDR).status_code == 400
    ok = c.patch("/api/me", json={"linkedin": "https://www.linkedin.com/in/ada"}, headers=HDR)
    assert ok.status_code == 200 and ok.get_json()["user"]["linkedin"].endswith("/in/ada")
    assert c.patch("/api/me", json={"email": "bad"}, headers=HDR).status_code == 400
    other, other_name = user(factory)
    assert c.patch("/api/me", json={"email": _em(other_name)}, headers=HDR).status_code == 409


# --------------------------------------------------------------------------- #
# Post editing
# --------------------------------------------------------------------------- #
def test_edit_post_owner_only_and_marks_edited(factory):
    c, _ = user(factory)
    other, _ = user(factory)
    pid = c.post("/api/posts", json={"body": "first draft #python"}, headers=HDR).get_json()["post"]["id"]
    assert other.patch(f"/api/posts/{pid}", json={"body": "hacked"}, headers=HDR).status_code == 403
    r = c.patch(f"/api/posts/{pid}", json={"body": "final #rust", "code": "fn main() {}", "code_lang": "rust"},
                headers=HDR)
    assert r.status_code == 200
    post = r.get_json()["post"]
    assert post["body"] == "final #rust" and post["code_lang"] == "rust" and post["edited_at"]
    assert c.patch(f"/api/posts/{pid}", json={"body": ""}, headers=HDR).status_code == 400  # empty
    tags = c.get("/api/search?q=%23rust").get_json()["posts"]
    assert any(p["id"] == pid for p in tags)
    assert not any(p["id"] == pid for p in c.get("/api/search?q=%23python").get_json()["posts"])


# --------------------------------------------------------------------------- #
# Files and attachments
# --------------------------------------------------------------------------- #
def test_upload_document_types_and_rejections(factory):
    c, _ = user(factory)
    r = upload(c, PDF, "design.pdf")
    assert r.status_code == 201
    body = r.get_json()
    assert body["kind"] == "file" and body["name"] == "design.pdf" and body["mime"] == "application/pdf"
    assert upload(c, ZIP, "src.zip").get_json()["kind"] == "file"
    assert upload(c, b"print('hi')\n", "main.py").status_code == 201
    assert upload(c, b"print('x')\x00", "bad.py").status_code == 415      # binary in a text type
    assert upload(c, b"MZ\x90\x00", "tool.exe").status_code == 415       # not allowed
    assert upload(c, b"<html>x</html>", "page.html").status_code == 415  # active content not allowed
    assert upload(c, b"%PDF-1.4", "fake.zip").status_code == 415         # extension must match contents
    assert upload(c, b"", "empty.txt").status_code == 400
    big = b"a" * (10 * 1024 * 1024 + 1)
    assert upload(c, big, "big.txt").status_code == 413


def test_document_download_is_forced_attachment(factory):
    c, _ = user(factory)
    mid = upload(c, PDF, "spec v1.pdf").get_json()["id"]
    r = c.get(f"/media/{mid}")
    assert r.status_code == 200 and r.data == PDF
    assert r.headers["Content-Disposition"].startswith("attachment")
    assert "spec%20v1.pdf" in r.headers["Content-Disposition"]
    img = upload(c, PNG, "pic.png").get_json()["id"]
    assert "Content-Disposition" not in c.get(f"/media/{img}").headers


def test_post_with_file_attachment_and_delete(factory):
    c, _ = user(factory)
    mid = upload(c, ZIP, "project.zip").get_json()["id"]
    r = c.post("/api/posts", json={"body": "source drop", "media_ids": [mid]}, headers=HDR)
    assert r.status_code == 201
    att = r.get_json()["post"]["attachments"]
    assert att[0]["kind"] == "file" and att[0]["name"] == "project.zip" and att[0]["size"] == len(ZIP)
    pid = r.get_json()["post"]["id"]
    assert c.delete(f"/api/posts/{pid}", headers=HDR).status_code == 200


def test_direct_message_file_attachment_and_privacy(factory):
    alice, a = user(factory)
    bob, b = user(factory)
    eve, _ = user(factory)
    cid = alice.post("/api/conversations", json={"username": b}, headers=HDR).get_json()["id"]
    mid = upload(alice, PDF, "notes.pdf").get_json()["id"]
    r = alice.post(f"/api/conversations/{cid}/messages", json={"body": "see attached", "media_id": mid}, headers=HDR)
    assert r.status_code == 201
    msg = r.get_json()["message"]
    assert msg["media"]["name"] == "notes.pdf" and msg["media"]["kind"] == "file"
    got = bob.get(f"/api/conversations/{cid}/messages").get_json()["messages"]
    assert got[-1]["media"]["name"] == "notes.pdf"
    assert bob.get(f"/media/{mid}").data == PDF
    # A user outside the conversation can't read it or post to it.
    assert eve.get(f"/api/conversations/{cid}/messages").status_code == 404
    assert eve.post(f"/api/conversations/{cid}/messages", json={"body": "hi"}, headers=HDR).status_code == 404
    # Another user can't attach someone else's file.
    other_mid = upload(eve, PDF, "theirs.pdf").get_json()["id"]
    assert alice.post(f"/api/conversations/{cid}/messages", json={"body": "x", "media_id": other_mid},
                      headers=HDR).status_code == 400


def test_message_notification_once_per_batch_and_links(factory):
    alice, a = user(factory)
    bob, b = user(factory)
    cid = alice.post("/api/conversations", json={"username": b}, headers=HDR).get_json()["id"]
    alice.post(f"/api/conversations/{cid}/messages", json={"body": "one"}, headers=HDR)
    alice.post(f"/api/conversations/{cid}/messages", json={"body": "two"}, headers=HDR)
    items = bob.get("/api/notifications").get_json()["items"]
    msgs = [n for n in items if n["type"] == "message"]
    assert len(msgs) == 1 and msgs[0]["link"] == f"/messages/{cid}"
    bob.get(f"/api/conversations/{cid}/messages")  # reading marks messages read
    alice.post(f"/api/conversations/{cid}/messages", json={"body": "three"}, headers=HDR)
    msgs = [n for n in bob.get("/api/notifications").get_json()["items"] if n["type"] == "message"]
    assert len(msgs) == 2


# --------------------------------------------------------------------------- #
# S3-compatible storage (in-memory fake; same calls as boto3)
# --------------------------------------------------------------------------- #
class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[Key] = bytes(Body)

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


def test_uploads_go_to_object_storage_when_configured(factory, monkeypatch):
    fake = FakeS3()
    monkeypatch.setenv("S3_BUCKET", "devx-test")
    monkeypatch.setattr(appmod, "_s3", lambda: fake)
    c, _ = user(factory)
    mid = upload(c, PDF, "stored.pdf").get_json()["id"]
    d = appmod.dbm.Conn()
    row = d.execute("SELECT data, storage_key FROM media WHERE id = ?", (mid,)).fetchone()
    d.close()
    assert row["storage_key"].startswith("media/") and bytes(row["data"]) == b""
    assert fake.objects[row["storage_key"]] == PDF
    assert c.get(f"/media/{mid}").data == PDF
    pid = c.post("/api/posts", json={"body": "with file", "media_ids": [mid]}, headers=HDR).get_json()["post"]["id"]
    assert c.delete(f"/api/posts/{pid}", headers=HDR).status_code == 200
    assert row["storage_key"] not in fake.objects  # deleted from the bucket with the post


# --------------------------------------------------------------------------- #
# Projects & portfolios
# --------------------------------------------------------------------------- #
def test_project_crud_validation_and_tags(factory):
    c, name = user(factory)
    other, _ = user(factory)
    bad = {"title": "", "description": "x"}
    assert c.post("/api/projects", json=bad, headers=HDR).status_code == 400
    assert c.post("/api/projects", json={"title": "x", "repo_url": "ftp://nope"}, headers=HDR).status_code == 400
    assert c.post("/api/projects", json={"title": "x", "tags": "bad tag!"}, headers=HDR).status_code == 400
    assert c.post("/api/projects", json={"title": "x", "status": "weird"}, headers=HDR).status_code == 400
    r = c.post("/api/projects", json={
        "title": "Tiny Compiler", "description": "A toy compiler", "repo_url": "https://github.com/ada/tiny",
        "live_url": "https://tiny.example.com", "status": "building", "tags": "Rust, compilers, wasm"},
        headers=HDR)
    assert r.status_code == 201
    p = r.get_json()["project"]
    assert p["tags"] == ["rust", "compilers", "wasm"] and p["mine"] is True and p["status"] == "building"
    pid = p["id"]

    seen = other.get(f"/api/projects/{pid}").get_json()["project"]
    assert seen["mine"] is False
    assert other.patch(f"/api/projects/{pid}", json={"title": "pwned"}, headers=HDR).status_code == 403
    assert other.delete(f"/api/projects/{pid}", headers=HDR).status_code == 403

    up = c.patch(f"/api/projects/{pid}", json={"status": "shipped", "tags": "rust"}, headers=HDR).get_json()["project"]
    assert up["status"] == "shipped" and up["tags"] == ["rust"]

    tagged = [x["id"] for x in other.get("/api/projects?tag=rust").get_json()["items"]]
    assert pid in tagged
    assert pid not in [x["id"] for x in other.get("/api/projects?tag=wasm").get_json()["items"]]
    assert pid in [x["id"] for x in other.get("/api/projects?status=shipped").get_json()["items"]]
    assert pid in [x["id"] for x in other.get("/api/projects?q=tiny").get_json()["items"]]
    assert pid in [x["id"] for x in other.get(f"/api/users/{name}/projects").get_json()["items"]]

    assert c.delete(f"/api/projects/{pid}", headers=HDR).status_code == 200
    assert other.get(f"/api/projects/{pid}").status_code == 404


def test_project_like_notifies_owner_with_link(factory):
    owner, _ = user(factory)
    fan, _ = user(factory)
    pid = owner.post("/api/projects", json={"title": "Pie", "tags": "python"}, headers=HDR).get_json()["project"]["id"]
    assert fan.post(f"/api/projects/{pid}/like", headers=HDR).status_code == 200
    fan.post(f"/api/projects/{pid}/like", headers=HDR)  # idempotent
    proj = fan.get(f"/api/projects/{pid}").get_json()["project"]
    assert proj["like_count"] == 1 and proj["liked"] is True
    notes = [n for n in owner.get("/api/notifications").get_json()["items"] if n["type"] == "project_like"]
    assert len(notes) == 1 and notes[0]["link"] == f"/projects/{pid}"
    assert fan.delete(f"/api/projects/{pid}/like", headers=HDR).status_code == 200
    assert fan.get(f"/api/projects/{pid}").get_json()["project"]["like_count"] == 0


def test_collaborators_found_through_shared_project_tags(factory):
    # A per-run tag keeps results stable when the Postgres test DB persists between runs.
    tag = "tg" + uuid.uuid4().hex[:8]
    owner, _ = user(factory)
    peer, peer_name = user(factory)
    stranger, stranger_name = user(factory)
    pid = owner.post("/api/projects", json={"title": "Ledger", "tags": f"python,{tag}"}, headers=HDR).get_json()["project"]["id"]
    peer.post("/api/projects", json={"title": "Query lab", "tags": f"sql,{tag}"}, headers=HDR)
    stranger.post("/api/projects", json={"title": "Pottery", "tags": "clay"}, headers=HDR)
    items = owner.get(f"/api/projects/{pid}/collaborators").get_json()["items"]
    names = [i["user"]["username"] for i in items]
    assert peer_name in names and stranger_name not in names
    entry = next(i for i in items if i["user"]["username"] == peer_name)
    assert entry["shared_tags"] == [tag] and entry["projects"][0]["title"] == "Query lab"


# --------------------------------------------------------------------------- #
# Collaboration requests
# --------------------------------------------------------------------------- #
def test_collab_lifecycle_and_authorization(factory):
    owner, owner_name = user(factory)
    applicant, applicant_name = user(factory)
    stranger, _ = user(factory)
    pid = owner.post("/api/projects", json={"title": "Open source CLI", "tags": "go"}, headers=HDR).get_json()["project"]["id"]

    assert owner.post("/api/collab", json={"description": "no title"}, headers=HDR).status_code == 400
    assert owner.post("/api/collab", json={"title": "Need a designer", "project_id": 999999},
                      headers=HDR).status_code == 400
    assert applicant.post("/api/collab", json={"title": "x", "project_id": pid}, headers=HDR).status_code == 400
    r = owner.post("/api/collab", json={"title": "Need a Go dev", "description": "CLI polish",
                                        "goals": "ship v1 by December", "skills": "go, cli",
                                        "project_id": pid}, headers=HDR)
    assert r.status_code == 201
    req = r.get_json()["request"]
    cid = req["id"]
    assert req["status"] == "open" and req["skills"] == ["go", "cli"] and req["project"]["id"] == pid

    assert [x["id"] for x in applicant.get("/api/collab?skill=go").get_json()["items"]].count(cid) == 1
    assert cid not in [x["id"] for x in applicant.get("/api/collab?skill=rust").get_json()["items"]]

    assert owner.post(f"/api/collab/{cid}/interest", json={}, headers=HDR).status_code == 400  # own request
    assert applicant.post(f"/api/collab/{cid}/interest", json={"message": "I'd love to help"},
                          headers=HDR).status_code == 201
    assert applicant.post(f"/api/collab/{cid}/interest", json={}, headers=HDR).status_code == 409

    owner_view = owner.get(f"/api/collab/{cid}").get_json()["request"]
    assert owner_view["interest_count"] == 1
    interests = owner.get(f"/api/collab/{cid}").get_json()["request"]["interests"]
    assert interests[0]["applicant"]["username"] == applicant_name and interests[0]["status"] == "pending"
    assert "interests" not in applicant.get(f"/api/collab/{cid}").get_json()["request"]

    notes = [n for n in owner.get("/api/notifications").get_json()["items"] if n["type"] == "collab_interest"]
    assert notes and notes[0]["link"] == f"/collab/{cid}"

    iid = interests[0]["id"]
    assert stranger.patch(f"/api/collab/{cid}/interests/{iid}", json={"status": "accepted"},
                          headers=HDR).status_code == 403
    assert applicant.patch(f"/api/collab/{cid}/interests/{iid}", json={"status": "accepted"},
                           headers=HDR).status_code == 403
    assert owner.patch(f"/api/collab/{cid}/interests/{iid}", json={"status": "accepted"},
                       headers=HDR).status_code == 200
    status_notes = [n for n in applicant.get("/api/notifications").get_json()["items"] if n["type"] == "collab_status"]
    assert status_notes and status_notes[0]["link"] == f"/collab/{cid}"
    assert applicant.get(f"/api/collab/{cid}").get_json()["request"]["my_interest"] == "accepted"

    assert stranger.patch(f"/api/collab/{cid}", json={"status": "closed"}, headers=HDR).status_code == 403
    assert owner.patch(f"/api/collab/{cid}", json={"status": "closed"}, headers=HDR).status_code == 200
    assert applicant.post(f"/api/collab/{cid}/interest", json={}, headers=HDR).status_code == 400  # closed
    assert cid in [x["id"] for x in applicant.get("/api/collab?status=closed").get_json()["items"]]
    assert cid not in [x["id"] for x in applicant.get("/api/collab?status=open").get_json()["items"]]

    assert applicant.delete(f"/api/collab/{cid}/interest", headers=HDR).status_code == 200
    assert owner.delete(f"/api/collab/{cid}", headers=HDR).status_code == 200
    assert applicant.get(f"/api/collab/{cid}").status_code == 404


def test_withdraw_and_reapply(factory):
    owner, _ = user(factory)
    applicant, _ = user(factory)
    cid = owner.post("/api/collab", json={"title": "Pair on Rust"}, headers=HDR).get_json()["request"]["id"]
    applicant.post(f"/api/collab/{cid}/interest", json={}, headers=HDR)
    assert applicant.delete(f"/api/collab/{cid}/interest", headers=HDR).status_code == 200
    assert applicant.get(f"/api/collab/{cid}").get_json()["request"]["my_interest"] is None
    assert applicant.post(f"/api/collab/{cid}/interest", json={}, headers=HDR).status_code == 201


# --------------------------------------------------------------------------- #
# Search and LinkedIn
# --------------------------------------------------------------------------- #
def test_search_finds_projects_and_filters_posts_by_language(factory):
    c, _ = user(factory)
    token = "zq" + uuid.uuid4().hex[:6]
    c.post("/api/projects", json={"title": f"{token} engine", "tags": "rust"}, headers=HDR)
    c.post("/api/posts", json={"body": f"{token} go post", "code": "package main", "code_lang": "go"}, headers=HDR)
    c.post("/api/posts", json={"body": f"{token} rust post", "code": "fn main(){}", "code_lang": "rust"}, headers=HDR)
    res = c.get(f"/api/search?q={token}").get_json()
    assert len(res["posts"]) == 2
    assert [p["title"] for p in res["projects"]] == [f"{token} engine"]
    only_rust = c.get(f"/api/search?q={token}&lang=rust").get_json()["posts"]
    assert len(only_rust) == 1 and only_rust[0]["code_lang"] == "rust"
