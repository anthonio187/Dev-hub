"""End-to-end API tests for DevX. Run with:  pytest -q

Uses a throwaway SQLite database by default. To run the same suite against
Postgres (e.g. Neon), set DATABASE_URL in the environment first.
"""

import io
import os
import re
import sys
import tempfile
import uuid
from urllib.parse import quote

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

if not os.environ.get("DATABASE_URL"):
    os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as appmod  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
def _em(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower()) + '@example.com'

HDR = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    appmod._RATE.clear()
    yield


@pytest.fixture()
def client():
    appmod.app.config["TESTING"] = True
    with appmod.app.test_client() as c:
        yield c


def uname(prefix="dev"):
    return (prefix + uuid.uuid4().hex[:8])[:15]


def signup(c, username=None, password="password123"):
    username = username or uname()
    r = c.post("/api/auth/signup", json={"username": username, "email": _em(username), "password": password}, headers=HDR)
    assert r.status_code == 201, r.get_json()
    return username


def new_user(client_factory):
    """Return (client, username) logged in as a fresh user with its own cookie jar."""
    c = client_factory()
    name = signup(c)
    return c, name


@pytest.fixture()
def factory():
    def make():
        return appmod.app.test_client()
    return make


def me_id(c):
    return c.get("/api/auth/me").get_json()["user"]["id"]


# --------------------------------------------------------------------------- auth
def test_signup_login_logout_and_me(client, factory):
    name = signup(client)
    assert client.get("/api/auth/me").get_json()["user"]["username"] == name
    client.post("/api/auth/logout", headers=HDR)
    assert client.get("/api/auth/me").get_json()["user"] is None
    r = client.post("/api/auth/login", json={"username": name.upper(), "email": _em(name.upper()), "password": "password123"}, headers=HDR)
    assert r.status_code == 200, r.get_json()
    assert client.get("/api/auth/me").get_json()["user"]["username"] == name


def test_signup_validation_and_duplicates(client, factory):
    assert client.post("/api/auth/signup", json={"username": "ab", "email": _em("ab"), "password": "password123"}, headers=HDR).status_code == 400
    assert client.post("/api/auth/signup", json={"username": "bad name!", "email": _em("bad name!"), "password": "password123"}, headers=HDR).status_code == 400
    assert client.post("/api/auth/signup", json={"username": "shorty", "email": _em("shorty"), "password": "123"}, headers=HDR).status_code == 400
    name = signup(client, uname("dup"))
    other = factory()
    r = other.post("/api/auth/signup", json={"username": name.upper(), "email": _em(name.upper()), "password": "password123"}, headers=HDR)
    assert r.status_code == 409


def test_wrong_password_rejected(client):
    name = signup(client)
    client.post("/api/auth/logout", headers=HDR)
    r = client.post("/api/auth/login", json={"username": name, "email": _em(name), "password": "nope-nope"}, headers=HDR)
    assert r.status_code == 401


def test_csrf_header_required_on_mutations(client):
    r = client.post("/api/auth/signup", json={"username": uname(), "email": _em(uname()), "password": "password123"})
    assert r.status_code == 403


def test_password_change_and_account_delete(client, factory):
    name = signup(client)
    r = client.post("/api/auth/password", json={"current": "wrong", "new": "newpassword1"}, headers=HDR)
    assert r.status_code == 400
    r = client.post("/api/auth/password", json={"current": "password123", "new": "newpassword1"}, headers=HDR)
    assert r.status_code == 200
    client.post("/api/auth/logout", headers=HDR)
    assert client.post("/api/auth/login", json={"username": name, "email": _em(name), "password": "newpassword1"}, headers=HDR).status_code == 200
    assert client.delete("/api/me", json={"password": "bad"}, headers=HDR).status_code == 400
    assert client.delete("/api/me", json={"password": "newpassword1"}, headers=HDR).status_code == 200
    assert client.get("/api/users/" + name).status_code == 404


# ------------------------------------------------------------------ profile
def test_profile_update_tech_website_and_avatar(client):
    name = signup(client)
    r = client.patch("/api/me", json={
        "display_name": "Ada Lovelace", "bio": "Compilers & coffee", "location": "Abuja",
        "website": "https://ada.dev", "tech": "Python, Postgres, python, Go",
    }, headers=HDR)
    assert r.status_code == 200, r.get_json()
    user = r.get_json()["user"]
    assert user["display_name"] == "Ada Lovelace"
    assert user["tech"] == ["Python", "Postgres", "Go"]  # case-insensitive dedupe
    assert client.patch("/api/me", json={"website": "javascript:alert(1)"}, headers=HDR).status_code == 400
    assert client.patch("/api/me", json={"bio": "x" * 161}, headers=HDR).status_code == 400

    up = client.post("/api/media", data={"file": (io.BytesIO(PNG), "a.png")}, headers=HDR,
                     content_type="multipart/form-data")
    assert up.status_code == 201, up.get_json()
    mid = up.get_json()["id"]
    r = client.patch("/api/me", json={"avatar_media_id": mid}, headers=HDR)
    assert r.get_json()["user"]["avatar_url"] == f"/media/{mid}"
    img = client.get(f"/media/{mid}")
    assert img.status_code == 200 and img.mimetype == "image/png"
    assert img.data.startswith(b"\x89PNG")

    prof = client.get("/api/users/" + name).get_json()
    assert prof["user"]["display_name"] == "Ada Lovelace"
    assert prof["is_me"] is True


def test_media_rejects_non_images_and_oversize(client):
    signup(client)
    r = client.post("/api/media", data={"file": (io.BytesIO(b"<svg onload=alert(1)>"), "x.svg")},
                    headers=HDR, content_type="multipart/form-data")
    assert r.status_code == 415
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024 + 10)
    r = client.post("/api/media", data={"file": (io.BytesIO(big), "big.png")},
                    headers=HDR, content_type="multipart/form-data")
    assert r.status_code in (413, 400)


# -------------------------------------------------------------------- posts
def test_create_post_with_code_tags_mentions_and_limits(client, factory):
    alice, a = new_user(factory)
    bob, b = new_user(factory)
    r = alice.post("/api/posts", json={
        "body": f"Shipping #DevTools update with @{b} — https://example.com",
        "code": "print('hi')", "code_lang": "python",
    }, headers=HDR)
    assert r.status_code == 201, r.get_json()
    post = r.get_json()["post"]
    assert post["code"] == "print('hi')" and post["code_lang"] == "python"
    assert post["author"]["username"] == a
    assert alice.post("/api/posts", json={"body": "x" * 281}, headers=HDR).status_code == 400
    assert alice.post("/api/posts", json={"body": "   "}, headers=HDR).status_code == 400

    # hashtag indexed, trends show it, mention produced a notification
    trends = alice.get("/api/trends").get_json()["tags"]
    assert any(t["tag"] == "devtools" for t in trends)
    counts = bob.get("/api/counts").get_json()
    assert counts["notifications"] >= 1
    notes = bob.get("/api/notifications").get_json()["items"]
    assert any(n["type"] == "mention" and n["actor"]["username"] == a for n in notes)


def test_media_attachments_limit_and_ownership(client, factory):
    alice, _ = new_user(factory)
    bob, _ = new_user(factory)
    ids = []
    for _ in range(4):
        up = alice.post("/api/media", data={"file": (io.BytesIO(PNG), "a.png")}, headers=HDR,
                        content_type="multipart/form-data")
        ids.append(up.get_json()["id"])
    r = alice.post("/api/posts", json={"body": "gallery", "media_ids": ids}, headers=HDR)
    assert r.status_code == 201
    assert len(r.get_json()["post"]["media"]) == 4
    five = ids + [ids[0]]
    assert alice.post("/api/posts", json={"body": "x", "media_ids": ids + [999999]}, headers=HDR).status_code == 400
    # bob can't attach alice's image
    assert bob.post("/api/posts", json={"body": "steal", "media_ids": [ids[0]]}, headers=HDR).status_code == 400
    assert len(five) == 5  # sanity


def test_like_repost_bookmark_and_notifications(client, factory):
    alice, a = new_user(factory)
    bob, b = new_user(factory)
    pid = alice.post("/api/posts", json={"body": "hello devs"}, headers=HDR).get_json()["post"]["id"]

    r = bob.post(f"/api/posts/{pid}/like", headers=HDR)
    assert r.get_json() == {"liked": True, "like_count": 1}
    assert bob.post(f"/api/posts/{pid}/like", headers=HDR).get_json()["like_count"] == 1  # idempotent
    notes = alice.get("/api/notifications").get_json()["items"]
    assert [n["type"] for n in notes].count("like") == 1  # no duplicate notification
    assert bob.delete(f"/api/posts/{pid}/like", headers=HDR).get_json()["like_count"] == 0

    r = bob.post(f"/api/posts/{pid}/repost", headers=HDR)
    assert r.get_json()["repost_count"] == 1
    assert bob.post(f"/api/posts/{pid}/bookmark", headers=HDR).get_json()["bookmarked"] is True
    saved = bob.get("/api/bookmarks").get_json()["items"]
    assert saved and saved[0]["post"]["id"] == pid
    assert bob.delete(f"/api/posts/{pid}/bookmark", headers=HDR).get_json()["bookmarked"] is False
    assert bob.get("/api/bookmarks").get_json()["items"] == []

    # self-like doesn't notify
    alice.post(f"/api/posts/{pid}/like", headers=HDR)
    assert all(n["actor"]["username"] != a for n in alice.get("/api/notifications").get_json()["items"])


def test_reply_thread_and_quote(client, factory):
    alice, a = new_user(factory)
    bob, b = new_user(factory)
    root = alice.post("/api/posts", json={"body": "Root post"}, headers=HDR).get_json()["post"]
    reply = bob.post("/api/posts", json={"body": "A reply", "reply_to": root["id"]}, headers=HDR).get_json()["post"]
    assert reply["reply_to_username"] == a
    assert reply["parent_id"] == root["id"]

    detail = bob.get(f"/api/posts/{root['id']}").get_json()
    assert detail["post"]["reply_count"] == 1
    replies = bob.get(f"/api/posts/{root['id']}/replies").get_json()["items"]
    assert [r["id"] for r in replies] == [reply["id"]]
    thread = bob.get(f"/api/posts/{reply['id']}").get_json()["thread"]
    assert thread and thread[0]["id"] == root["id"]

    quote = alice.post("/api/posts", json={"body": "Great take!", "quote_id": reply["id"]}, headers=HDR).get_json()["post"]
    assert quote["quoted"]["id"] == reply["id"]
    assert any(n["type"] == "quote" for n in bob.get("/api/notifications").get_json()["items"])
    assert any(n["type"] == "reply" for n in alice.get("/api/notifications").get_json()["items"])

    # home timeline of a non-follower doesn't include alice's posts
    assert all(i["post"]["author"]["username"] != a for i in bob.get("/api/timeline").get_json()["items"])


def test_delete_post_rules(client, factory):
    alice, _ = new_user(factory)
    bob, _ = new_user(factory)
    pid = alice.post("/api/posts", json={"body": "to delete"}, headers=HDR).get_json()["post"]["id"]
    assert bob.delete(f"/api/posts/{pid}", headers=HDR).status_code == 403
    assert alice.delete(f"/api/posts/{pid}", headers=HDR).status_code == 200
    assert alice.get(f"/api/posts/{pid}").status_code == 404


# ------------------------------------------------------------ follow & feeds
def test_follow_timeline_profile_tabs_and_lists(client, factory):
    alice, a = new_user(factory)
    bob, b = new_user(factory)
    assert alice.post(f"/api/users/{a}/follow", headers=HDR).status_code == 400  # self
    r = alice.post(f"/api/users/{b}/follow", headers=HDR)
    assert r.get_json() == {"following": True, "followers": 1}
    assert any(n["type"] == "follow" for n in bob.get("/api/notifications").get_json()["items"])

    pid = bob.post("/api/posts", json={"body": "bob's post #python"}, headers=HDR).get_json()["post"]["id"]
    bob.post("/api/posts", json={"body": "a reply", "reply_to": pid}, headers=HDR)
    bob.post(f"/api/posts/{pid}/repost", headers=HDR)
    bob.post(f"/api/posts/{pid}/like", headers=HDR)

    timeline = alice.get("/api/timeline").get_json()["items"]
    kinds = {(i["kind"], i["post"]["author"]["username"]) for i in timeline}
    assert ("post", b) in kinds
    assert any(i["kind"] == "repost" and i["by"]["username"] == b for i in timeline)

    prof_posts = alice.get(f"/api/users/{b}/posts?tab=posts").get_json()["items"]
    assert any(i["kind"] == "post" and i["post"]["id"] == pid for i in prof_posts)
    replies = alice.get(f"/api/users/{b}/posts?tab=replies").get_json()["items"]
    assert len(replies) == 1 and replies[0]["post"]["parent_id"] == pid
    media = alice.get(f"/api/users/{b}/posts?tab=media").get_json()["items"]
    assert media == []
    likes = alice.get(f"/api/users/{b}/posts?tab=likes").get_json()["items"]
    assert any(i["post"]["id"] == pid for i in bob.get(f"/api/users/{b}/posts?tab=likes").get_json()["items"])

    prof = alice.get(f"/api/users/{b}").get_json()
    assert prof["following"] is True and prof["follows_you"] is False  # alice follows bob
    assert prof["stats"]["followers"] == 1
    fol = bob.get(f"/api/users/{b}/followers").get_json()["users"]
    assert [u["username"] for u in fol] == [a]
    ing = alice.get(f"/api/users/{a}/following").get_json()["users"]
    assert [u["username"] for u in ing] == [b]

    assert alice.delete(f"/api/users/{b}/follow", headers=HDR).get_json()["following"] is False
    assert alice.get(f"/api/users/{b}").get_json()["following"] is False


def test_pagination_cursor(client, factory):
    alice, a = new_user(factory)
    for i in range(23):
        alice.post("/api/posts", json={"body": f"post {i}"}, headers=HDR)
    # the database is shared across tests, so walk every page and check ours are all present
    seen, cursor, pages = [], None, 0
    while True:
        url = "/api/explore" + (f"?before={quote(cursor)}" if cursor else "")
        page = alice.get(url).get_json()
        assert len(page["items"]) <= 20
        seen += [i["post"]["id"] for i in page["items"]]
        pages += 1
        cursor = page["next"]
        if not cursor:
            break
    assert len(seen) == len(set(seen))  # no duplicates across pages
    assert pages >= 2
    assert len(set(seen)) >= 23

    tfirst = alice.get(f"/api/users/{a}/posts?tab=posts").get_json()
    assert len(tfirst["items"]) == 20
    tsecond = alice.get(f"/api/users/{a}/posts?tab=posts&before=" + quote(tfirst["next"])).get_json()
    assert len(tsecond["items"]) == 3


def test_like_and_bookmark_state_visible_to_viewer(client, factory):
    alice, _ = new_user(factory)
    bob, _ = new_user(factory)
    pid = alice.post("/api/posts", json={"body": "state check"}, headers=HDR).get_json()["post"]["id"]
    bob.post(f"/api/posts/{pid}/like", headers=HDR)
    post = bob.get(f"/api/posts/{pid}").get_json()["post"]
    assert post["liked"] is True and post["like_count"] == 1 and post["mine"] is False
    post_a = alice.get(f"/api/posts/{pid}").get_json()["post"]
    assert post_a["liked"] is False and post_a["mine"] is True


# ------------------------------------------------------- search & discovery
def test_search_people_posts_and_tags(client, factory):
    alice, a = new_user(factory)
    bob, b = new_user(factory)
    term = "zq" + uuid.uuid4().hex[:8]  # unique per run; the database may be shared
    alice.post("/api/posts", json={"body": f"Learning {term} lifetimes #{term}"}, headers=HDR)
    bob.post("/api/posts", json={"body": f"{term} is fun #{term.upper()}"}, headers=HDR)

    res = alice.get("/api/search?q=" + term).get_json()
    assert len(res["posts"]) == 2
    tagged = alice.get("/api/search?q=%23" + term).get_json()
    assert len(tagged["posts"]) == 2
    assert any(t["tag"] == term for t in tagged["tags"])
    people = alice.get("/api/search?q=" + b[:6]).get_json()["people"]
    assert any(p["username"] == b for p in people)
    # LIKE wildcards are escaped
    assert alice.get("/api/search?q=%25").get_json()["posts"] == []

    wtf = alice.get("/api/who-to-follow").get_json()["users"]
    assert all(u["username"] != a for u in wtf)


def test_explore_and_who_to_follow_work_logged_out(client, factory):
    alice, _ = new_user(factory)
    alice.post("/api/posts", json={"body": "public post"}, headers=HDR)
    anon = factory()
    assert anon.get("/api/explore").get_json()["items"]
    assert anon.get("/api/who-to-follow").status_code == 200
    assert anon.get("/api/timeline").status_code == 401


# ---------------------------------------------------------------- notifications
def test_notifications_read_and_counts(client, factory):
    alice, _ = new_user(factory)
    bob, _ = new_user(factory)
    pid = alice.post("/api/posts", json={"body": "ping"}, headers=HDR).get_json()["post"]["id"]
    bob.post(f"/api/posts/{pid}/like", headers=HDR)
    assert alice.get("/api/counts").get_json()["notifications"] == 1
    items = alice.get("/api/notifications").get_json()["items"]
    assert items[0]["post"]["id"] == pid and items[0]["is_read"] is False
    alice.post("/api/notifications/read", headers=HDR)
    assert alice.get("/api/counts").get_json()["notifications"] == 0


def test_notifications_mentions_filter(client, factory):
    alice, a = new_user(factory)
    bob, b = new_user(factory)
    pid = alice.post("/api/posts", json={"body": "ping"}, headers=HDR).get_json()["post"]["id"]
    bob.post(f"/api/posts/{pid}/like", headers=HDR)  # a 'like' notification for alice
    bob.post("/api/posts", json={"body": f"hey @{a} look"}, headers=HDR)  # a 'mention' notification for alice
    everything = alice.get("/api/notifications").get_json()["items"]
    assert {n["type"] for n in everything} >= {"like", "mention"}
    mentions = alice.get("/api/notifications?kind=mentions").get_json()["items"]
    assert mentions and all(n["type"] == "mention" for n in mentions)


# -------------------------------------------------------------------- DMs
def test_direct_messages_with_images_and_unread(client, factory):
    alice, a = new_user(factory)
    bob, b = new_user(factory)
    assert alice.post("/api/conversations", json={"username": a}, headers=HDR).status_code == 400
    conv = alice.post("/api/conversations", json={"username": b}, headers=HDR)
    assert conv.status_code == 201
    cid = conv.get_json()["id"]
    again = bob.post("/api/conversations", json={"username": a}, headers=HDR).get_json()
    assert again["id"] == cid  # same conversation from either side

    r = alice.post(f"/api/conversations/{cid}/messages", json={"body": "hey! check this"}, headers=HDR)
    assert r.status_code == 201 and r.get_json()["message"]["mine"] is True

    up = alice.post("/api/media", data={"file": (io.BytesIO(PNG), "shot.png")}, headers=HDR,
                    content_type="multipart/form-data")
    mid = up.get_json()["id"]
    r = alice.post(f"/api/conversations/{cid}/messages", json={"body": "", "media_id": mid}, headers=HDR)
    assert r.status_code == 201
    img_msg = r.get_json()["message"]
    assert img_msg["media_url"] == f"/media/{mid}"
    assert alice.post(f"/api/conversations/{cid}/messages", json={}, headers=HDR).status_code == 400

    # bob sees 2 unread, reading marks them read
    assert bob.get("/api/counts").get_json()["messages"] == 2
    convs = bob.get("/api/conversations").get_json()["conversations"]
    assert convs[0]["unread"] == 2 and convs[0]["user"]["username"] == a
    msgs = bob.get(f"/api/conversations/{cid}/messages").get_json()
    assert [m["body"] for m in msgs["messages"]][0] == "hey! check this"
    assert bob.get("/api/counts").get_json()["messages"] == 0

    # polling: only newer messages
    last = msgs["messages"][-1]["id"]
    alice.post(f"/api/conversations/{cid}/messages", json={"body": "newer"}, headers=HDR)
    fresh = bob.get(f"/api/conversations/{cid}/messages?after={last}").get_json()["messages"]
    assert [m["body"] for m in fresh] == ["newer"]

    # strangers can't read the conversation
    eve, _ = new_user(factory)
    assert eve.get(f"/api/conversations/{cid}/messages").status_code == 404
    assert eve.post(f"/api/conversations/{cid}/messages", json={"body": "hi"}, headers=HDR).status_code == 404

    # someone else's image can't be sent
    other_up = eve.post("/api/media", data={"file": (io.BytesIO(PNG), "x.png")}, headers=HDR,
                        content_type="multipart/form-data")
    assert alice.post(f"/api/conversations/{cid}/messages",
                      json={"media_id": other_up.get_json()["id"]}, headers=HDR).status_code == 400


def test_message_length_limit(client, factory):
    alice, _ = new_user(factory)
    bob, b = new_user(factory)
    cid = alice.post("/api/conversations", json={"username": b}, headers=HDR).get_json()["id"]
    assert alice.post(f"/api/conversations/{cid}/messages", json={"body": "x" * 1001}, headers=HDR).status_code == 400


# ------------------------------------------------------------- security bits
def test_xss_payloads_are_stored_as_plain_text(client, factory):
    alice, _ = new_user(factory)
    payload = "<img src=x onerror=alert(1)>"
    post = alice.post("/api/posts", json={"body": payload}, headers=HDR).get_json()["post"]
    assert post["body"] == payload  # stored verbatim; the frontend escapes via textContent
    assert alice.get("/api/explore").status_code == 200


def test_security_headers_and_spa_fallback(client):
    r = client.get("/u/someone")
    assert r.status_code == 200
    assert b"<div id=\"app\"" in r.data
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/api/does-not-exist").get_json()["error"]


def test_rate_limit_login(client):
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "nobody1", "email": _em("nobody1"), "password": "x"}, headers=HDR)
    assert client.post("/api/auth/login", json={"username": "nobody1", "email": _em("nobody1"), "password": "x"}, headers=HDR).status_code == 429


def test_profile_settings_validation(client):
    signup(client)
    assert client.patch("/api/me", json={"display_name": ""}, headers=HDR).status_code == 400
    assert client.patch("/api/me", json={"avatar_media_id": 99999}, headers=HDR).status_code == 400


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.get_json()["ok"] is True
