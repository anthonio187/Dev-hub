"""DevX — a developer-focused X (Twitter) clone.

Flask backend + vanilla JS single-page frontend.
Postgres (Neon) when DATABASE_URL is set, SQLite for local development.

Features: accounts, profiles (avatar/banner/bio/tech stack), posts (280 chars,
code snippets, up to 4 images), replies, reposts, quote posts, likes, bookmarks,
follows, home timeline, profile tabs, explore/trends, search (posts, people,
#hashtags), notifications, and direct messages with image attachments.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import time
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, abort, g, jsonify, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import db as dbm
import devint
from devint import ProviderError

log = logging.getLogger("devx")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_PATH = os.path.join(BASE_DIR, ".secret_key")

PAGE = 20
POST_MAX = 280
CODE_MAX = 4000
DM_MAX = 1000
BIO_MAX = 160
NAME_MAX = 50
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_MEDIA_PER_POST = 4
DEFAULT_BEFORE_TS = "9999"          # sorts after every ISO timestamp
LANGS = (
    "javascript", "typescript", "python", "go", "rust", "java", "kotlin", "swift",
    "c", "cpp", "csharp", "php", "ruby", "sql", "bash", "html", "css", "json",
    "yaml", "dart", "text",
)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,15}$")
URL_RE = re.compile(r"^https?://\S+$")
TAG_RE = re.compile(r"(?<![A-Za-z0-9_&])#([A-Za-z][A-Za-z0-9_]{0,49})")
MENTION_RE = re.compile(r"(?<![A-Za-z0-9_@])@([A-Za-z0-9_]{1,15})")
TIMESTAMP_RE = re.compile(r"^[0-9T:.+\-]{10,40}$")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        bio TEXT NOT NULL DEFAULT '',
        location TEXT NOT NULL DEFAULT '',
        website TEXT NOT NULL DEFAULT '',
        linkedin TEXT NOT NULL DEFAULT '',
        email TEXT NOT NULL DEFAULT '',
        tech TEXT NOT NULL DEFAULT '',
        avatar_media_id INTEGER,
        banner_media_id INTEGER,
        created_at TEXT NOT NULL
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users (LOWER(username))",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (LOWER(email)) WHERE email <> ''",
    """CREATE TABLE IF NOT EXISTS media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        mime TEXT NOT NULL,
        data BLOB NOT NULL,
        size INTEGER NOT NULL,
        filename TEXT NOT NULL DEFAULT '',
        storage_key TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        body TEXT NOT NULL DEFAULT '',
        parent_id INTEGER REFERENCES posts(id) ON DELETE SET NULL,
        quote_id INTEGER REFERENCES posts(id) ON DELETE SET NULL,
        code TEXT NOT NULL DEFAULT '',
        code_lang TEXT NOT NULL DEFAULT '',
        edited_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_posts_user ON posts (user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_posts_parent ON posts (parent_id)",
    """CREATE TABLE IF NOT EXISTS post_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
        position INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        UNIQUE (user_id, post_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_likes_user ON likes (user_id, created_at)",
    """CREATE TABLE IF NOT EXISTS reposts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        UNIQUE (user_id, post_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_reposts_user ON reposts (user_id, created_at)",
    """CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        UNIQUE (user_id, post_id)
    )""",
    """CREATE TABLE IF NOT EXISTS follows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        followee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        UNIQUE (follower_id, followee_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_follows_followee ON follows (followee_id)",
    """CREATE TABLE IF NOT EXISTS hashtags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        tag TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_hashtags_tag ON hashtags (tag)",
    """CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        actor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        link TEXT NOT NULL DEFAULT '',
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_notif_recipient ON notifications (recipient_id, id)",
    """CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_a INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        user_b INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (user_a, user_b)
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        body TEXT NOT NULL DEFAULT '',
        media_id INTEGER REFERENCES media(id) ON DELETE SET NULL,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages (conversation_id, id)",
    """CREATE TABLE IF NOT EXISTS dev_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        provider TEXT NOT NULL,
        handle TEXT NOT NULL,
        verified INTEGER NOT NULL DEFAULT 0,
        verify_code TEXT NOT NULL DEFAULT '',
        data TEXT NOT NULL DEFAULT '{}',
        error TEXT NOT NULL DEFAULT '',
        fetched_at TEXT NOT NULL DEFAULT '',
        UNIQUE (user_id, provider)
    )""",
    """CREATE TABLE IF NOT EXISTS dev_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        open_to_work INTEGER NOT NULL DEFAULT 0,
        available_for TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS link_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL UNIQUE,
        data TEXT NOT NULL,
        fetched_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_dev_accounts_handle ON dev_accounts (provider, handle)",
    """CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        repo_url TEXT NOT NULL DEFAULT '',
        live_url TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'idea',
        tags TEXT NOT NULL DEFAULT '',
        screenshot_media_id INTEGER REFERENCES media(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_projects_user ON projects (user_id, id)",
    """CREATE TABLE IF NOT EXISTS project_likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        UNIQUE (user_id, project_id)
    )""",
    """CREATE TABLE IF NOT EXISTS collab_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        goals TEXT NOT NULL DEFAULT '',
        skills TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_collab_status ON collab_requests (status, id)",
    """CREATE TABLE IF NOT EXISTS collab_interests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL REFERENCES collab_requests(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        message TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        UNIQUE (request_id, user_id)
    )""",
]


def init_db() -> None:
    conn = dbm.Conn()
    try:
        conn.script(SCHEMA)
    finally:
        conn.close()


def _load_or_create_secret_key() -> str:
    env = os.environ.get("SECRET_KEY", "").strip()
    if env:
        return env
    if IS_PROD:
        raise RuntimeError("SECRET_KEY must be set in production.")
    try:
        if os.path.exists(SECRET_PATH):
            with open(SECRET_PATH, "r", encoding="utf-8") as fh:
                key = fh.read().strip()
            if key:
                return key
        key = secrets.token_hex(32)
        with open(SECRET_PATH, "w", encoding="utf-8") as fh:
            fh.write(key)
        return key
    except OSError:
        return secrets.token_hex(32)


IS_PROD = bool(os.environ.get("PRODUCTION") or os.environ.get("RENDER"))

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(
    SECRET_KEY=_load_or_create_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PROD,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
)

_RATE = {}


def rate_limited(key: str, limit: int = 10, window: int = 300) -> bool:
    now = time.time()
    hits = [t for t in _RATE.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _RATE[key] = hits
        return True
    hits.append(now)
    _RATE[key] = hits
    return False


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.msg = msg
        self.code = code


# --------------------------------------------------------------------------- #
# Request plumbing
# --------------------------------------------------------------------------- #
def db():
    if "db" not in g:
        g.db = dbm.Conn()
    return g.db


@app.teardown_appcontext
def _close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.before_request
def _csrf_guard():
    # Browsers can't send custom headers cross-site without CORS, so requiring
    # this header on mutating API calls blocks classic CSRF.
    if request.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return jsonify(error="Missing X-Requested-With header."), 403


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if IS_PROD:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'self'",
    )
    return resp


@app.errorhandler(ApiError)
def _api_error(e):
    return jsonify(error=e.msg), e.code


@app.errorhandler(404)
def _not_found(_e):
    if request.path.startswith("/api/") or request.path.startswith("/media/"):
        return jsonify(error="Not found."), 404
    return render_template("index.html"), 404


@app.errorhandler(405)
def _bad_method(_e):
    return jsonify(error="Method not allowed."), 405


@app.errorhandler(413)
def _too_large(_e):
    return jsonify(error="Upload too large (max 10 MB per file)."), 413


@app.errorhandler(500)
def _server_error(e):
    log.error("Unhandled error on %s %s", request.method, request.path,
              exc_info=getattr(e, "original_exception", None) or True)
    return jsonify(error="Something went wrong on our side."), 500


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def ph_of(seq) -> str:
    return ",".join(["?"] * len(seq))


def like_escape(s: str) -> str:
    return s.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def to_int(value, what="id") -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiError(f"Invalid {what}.", 400)


def ts_before():
    b = request.args.get("before", "").replace(" ", "+")  # a raw '+' in a query string decodes to a space
    return b if b and TIMESTAMP_RE.match(b) else DEFAULT_BEFORE_TS


def id_before():
    b = request.args.get("before", "")
    return int(b) if b.isdigit() else 2 ** 62


def current():
    if "me" in g:
        return g.me
    uid = session.get("uid")
    g.me = db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone() if uid else None
    return g.me


def viewer_id():
    u = current()
    return u["id"] if u else None


def need_user():
    u = current()
    if not u:
        raise ApiError("Log in to continue.", 401)
    return u


def find_user(username: str):
    row = db().execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone()
    if not row:
        raise ApiError("No account with that username.", 404)
    return row


def media_url(mid):
    return f"/media/{mid}" if mid else None


def user_lite(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "avatar_url": media_url(row["avatar_media_id"]),
    }


def user_full(row, private=False) -> dict:
    tech = [t.strip() for t in (row["tech"] or "").split(",") if t.strip()]
    out = {
        **user_lite(row),
        "bio": row["bio"],
        "location": row["location"],
        "website": row["website"],
        "linkedin": row["linkedin"],
        "tech": tech,
        "banner_url": media_url(row["banner_media_id"]),
        "created_at": row["created_at"],
    }
    if private:
        out["email"] = row["email"]
    return out


def user_stats(uid: int) -> dict:
    r = db().execute(
        """SELECT (SELECT COUNT(*) FROM posts WHERE user_id = ?) AS posts,
                  (SELECT COUNT(*) FROM follows WHERE followee_id = ?) AS followers,
                  (SELECT COUNT(*) FROM follows WHERE follower_id = ?) AS following""",
        (uid, uid, uid),
    ).fetchone()
    return {"posts": r["posts"], "followers": r["followers"], "following": r["following"]}


def _count_by(d, table, ids):
    rows = d.execute(
        f"SELECT post_id, COUNT(*) AS c FROM {table} WHERE post_id IN ({ph_of(ids)}) GROUP BY post_id",
        ids,
    ).fetchall()
    return {r["post_id"]: r["c"] for r in rows}


def load_posts(ids, viewer, with_quote=True) -> dict:
    """Return {post_id: serialized post} with counts and viewer state filled in."""
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    d = db()
    ph = ph_of(ids)
    rows = d.execute(
        f"""SELECT p.id, p.user_id, p.body, p.parent_id, p.quote_id, p.code, p.code_lang, p.edited_at, p.created_at,
                   u.username, u.display_name, u.avatar_media_id,
                   pu.username AS parent_username
            FROM posts p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN posts pp ON pp.id = p.parent_id
            LEFT JOIN users pu ON pu.id = pp.user_id
            WHERE p.id IN ({ph})""",
        ids,
    ).fetchall()
    if not rows:
        return {}

    media, attachments = {}, {}
    for r in d.execute(
        f"""SELECT pm.post_id, pm.media_id, m.mime, m.filename, m.size FROM post_media pm
            JOIN media m ON m.id = pm.media_id WHERE pm.post_id IN ({ph}) ORDER BY pm.position, pm.id""", ids
    ).fetchall():
        media.setdefault(r["post_id"], []).append(media_url(r["media_id"]))
        attachments.setdefault(r["post_id"], []).append(attachment_out(r))

    likes = _count_by(d, "likes", ids)
    reposts = _count_by(d, "reposts", ids)
    replies = {
        r["parent_id"]: r["c"]
        for r in d.execute(
            f"SELECT parent_id, COUNT(*) AS c FROM posts WHERE parent_id IN ({ph}) GROUP BY parent_id", ids
        ).fetchall()
    }

    mine = {"liked": set(), "reposted": set(), "bookmarked": set()}
    if viewer:
        for table, key in (("likes", "liked"), ("reposts", "reposted"), ("bookmarks", "bookmarked")):
            mine[key] = {
                r["post_id"]
                for r in d.execute(
                    f"SELECT post_id FROM {table} WHERE user_id = ? AND post_id IN ({ph})",
                    [viewer, *ids],
                ).fetchall()
            }

    quoted = {}
    qids = [r["quote_id"] for r in rows if r["quote_id"]]
    if with_quote and qids:
        quoted = load_posts(qids, viewer, with_quote=False)

    out = {}
    for r in rows:
        pid = r["id"]
        out[pid] = {
            "id": pid,
            "body": r["body"],
            "code": r["code"],
            "code_lang": r["code_lang"],
            "created_at": r["created_at"],
            "parent_id": r["parent_id"],
            "reply_to_username": r["parent_username"],
            "author": {
                "id": r["user_id"],
                "username": r["username"],
                "display_name": r["display_name"] or r["username"],
                "avatar_url": media_url(r["avatar_media_id"]),
            },
            "media": media.get(pid, []),
            "attachments": attachments.get(pid, []),
            "edited_at": r["edited_at"],
            "like_count": likes.get(pid, 0),
            "repost_count": reposts.get(pid, 0),
            "reply_count": replies.get(pid, 0),
            "liked": pid in mine["liked"],
            "reposted": pid in mine["reposted"],
            "bookmarked": pid in mine["bookmarked"],
            "mine": bool(viewer) and r["user_id"] == viewer,
            "quoted": quoted.get(r["quote_id"]) if r["quote_id"] else None,
        }
    return out


def feed_page(kind: str, user_ids: list, before: str, viewer):
    """Cursor-paginated feed. kind: timeline | posts | replies | media | likes."""
    if not user_ids:
        return {"items": [], "next": None}
    d = db()
    ph = ph_of(user_ids)
    if kind == "timeline":
        sql = f"""SELECT p.id AS pid, p.created_at AS sort_at, CAST(NULL AS INTEGER) AS by_id
                  FROM posts p WHERE p.user_id IN ({ph}) AND p.created_at < ?
                  UNION ALL
                  SELECT r.post_id, r.created_at, r.user_id
                  FROM reposts r WHERE r.user_id IN ({ph}) AND r.created_at < ?"""
        params = user_ids + [before] + user_ids + [before]
    elif kind == "posts":
        sql = f"""SELECT p.id AS pid, p.created_at AS sort_at, CAST(NULL AS INTEGER) AS by_id
                  FROM posts p WHERE p.user_id IN ({ph}) AND p.parent_id IS NULL AND p.created_at < ?
                  UNION ALL
                  SELECT r.post_id, r.created_at, r.user_id
                  FROM reposts r WHERE r.user_id IN ({ph}) AND r.created_at < ?"""
        params = user_ids + [before] + user_ids + [before]
    elif kind == "replies":
        sql = f"""SELECT p.id AS pid, p.created_at AS sort_at, CAST(NULL AS INTEGER) AS by_id
                  FROM posts p WHERE p.user_id IN ({ph}) AND p.parent_id IS NOT NULL AND p.created_at < ?"""
        params = user_ids + [before]
    elif kind == "media":
        sql = f"""SELECT p.id AS pid, p.created_at AS sort_at, CAST(NULL AS INTEGER) AS by_id
                  FROM posts p WHERE p.user_id IN ({ph}) AND p.created_at < ?
                  AND EXISTS (SELECT 1 FROM post_media m WHERE m.post_id = p.id)"""
        params = user_ids + [before]
    elif kind == "likes":
        sql = f"""SELECT l.post_id AS pid, l.created_at AS sort_at, CAST(NULL AS INTEGER) AS by_id
                  FROM likes l WHERE l.user_id IN ({ph}) AND l.created_at < ?"""
        params = user_ids + [before]
    else:
        raise ApiError("Unknown feed.", 400)

    rows = d.execute(sql + " ORDER BY sort_at DESC LIMIT ?", params + [PAGE + 1]).fetchall()
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]
    posts = load_posts([r["pid"] for r in rows], viewer)
    by_ids = [r["by_id"] for r in rows if r["by_id"]]
    by_users = {}
    if by_ids:
        for u in d.execute(
            f"SELECT * FROM users WHERE id IN ({ph_of(by_ids)})", by_ids
        ).fetchall():
            by_users[u["id"]] = user_lite(u)

    items = []
    for r in rows:
        post = posts.get(r["pid"])
        if not post:
            continue
        item = {"kind": "repost" if r["by_id"] else "post", "sort_at": r["sort_at"], "post": post}
        if r["by_id"]:
            item["by"] = by_users.get(r["by_id"])
        items.append(item)
    return {"items": items, "next": rows[-1]["sort_at"] if has_more and rows else None}


def notify(recipient: int, actor: int, ntype: str, post_id=None, link: str = ""):
    if not recipient or recipient == actor:
        return
    db().execute(
        "INSERT INTO notifications (recipient_id, actor_id, type, post_id, link, is_read, created_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (recipient, actor, ntype, post_id, link, now_iso()),
    )


def validate_media(uid: int, ids: list) -> list:
    clean = []
    for mid in ids:
        if mid in clean:
            continue
        row = db().execute("SELECT id FROM media WHERE id = ? AND user_id = ?", (mid, uid)).fetchone()
        if not row:
            raise ApiError("One of the attached images is invalid.", 400)
        clean.append(mid)
    return clean


def sniff_image(data: bytes):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalize_tech(raw: str) -> str:
    seen, items = set(), []
    for part in re.split(r"[,\n]", raw or ""):
        t = part.strip()[:24]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            items.append(t)
    if len(items) > 10:
        raise ApiError("Add at most 10 tech stack items.", 400)
    return ",".join(items)


def serialize_message(row, viewer):
    return {
        "id": row["id"],
        "body": row["body"],
        "media_url": media_url(row["media_id"]),
        "media": attachment_out({"media_id": row["media_id"], "mime": row["media_mime"],
                                 "filename": row["media_name"], "size": row["media_size"]}) if row["media_id"] else None,
        "sender_id": row["sender_id"],
        "mine": row["sender_id"] == viewer,
        "created_at": row["created_at"],
    }


# --------------------------------------------------------------------------- #
# Pages (SPA shell)
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/<path:subpath>")
def spa(subpath):
    if subpath.startswith(("api/", "media/", "static/")):
        abort(404)
    return render_template("index.html")


@app.get("/api/health")
def health():
    try:
        db().execute("SELECT 1").fetchone()
    except Exception:  # database unreachable (e.g. Neon waking up)
        log.exception("health check failed")
        return jsonify(ok=False, database="unreachable"), 503
    return jsonify(ok=True, database="postgres" if dbm.IS_PG else "sqlite")


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESET_TTL = timedelta(hours=1)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def app_base_url() -> str:
    return (os.environ.get("APP_URL") or request.host_url).rstrip("/")


def send_email(to: str, subject: str, text: str) -> bool:
    """Send via SMTP (Brevo's relay works: SMTP_HOST=smtp-relay.brevo.com, port 587).

    Without SMTP_HOST, development prints the message to the console. Production
    logs an error instead, so reset links never end up in logs.
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        if IS_PROD:
            log.error("Email not sent to a user: SMTP_HOST is not configured.")
        else:
            log.warning("[dev email] to=%s subject=%s\n%s", to, subject, text)
        return False
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("MAIL_FROM", "DevX <no-reply@example.com>")
    msg["To"] = to
    msg.set_content(text)
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
            s.starttls()
            user = os.environ.get("SMTP_USER", "").strip()
            if user:
                s.login(user, os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return True
    except Exception:
        log.exception("SMTP send failed")
        return False


@app.post("/api/auth/signup")
def signup():
    if rate_limited(f"signup:{request.remote_addr}"):
        raise ApiError("Too many attempts. Try again in a few minutes.", 429)
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    if not USERNAME_RE.match(username):
        raise ApiError("Usernames are 4–15 characters: letters, numbers and underscores.")
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise ApiError("Enter a valid email address.")
    if len(password) < 8 or len(password) > 200:
        raise ApiError("Password must be 8–200 characters.")
    d = db()
    if d.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,)).fetchone():
        raise ApiError("That username is taken.", 409)
    if d.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,)).fetchone():
        raise ApiError("That email is already registered. Log in or reset your password.", 409)
    try:
        uid = d.execute(
            "INSERT INTO users (username, email, password_hash, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, email, generate_password_hash(password), username, now_iso()),
        ).lastrowid
        d.commit()
    except dbm.IntegrityError:
        d.rollback()
        raise ApiError("That username or email is already taken.", 409)
    session.clear()
    session.permanent = True
    session["uid"] = uid
    g.me = d.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return jsonify(user=user_full(g.me, private=True)), 201


@app.post("/api/auth/login")
def login():
    if rate_limited(f"login:{request.remote_addr}"):
        raise ApiError("Too many attempts. Try again in a few minutes.", 429)
    data = request.get_json(silent=True) or {}
    ident = str(data.get("username") or data.get("email") or "").strip()
    password = str(data.get("password") or "")
    row = db().execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR (email <> '' AND LOWER(email) = LOWER(?))",
        (ident, ident),
    ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        raise ApiError("Wrong username/email or password.", 401)
    session.clear()
    session.permanent = True
    session["uid"] = row["id"]
    g.me = row
    return jsonify(user=user_full(row, private=True))


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.post("/api/auth/forgot")
def forgot_password():
    """Always answers the same way, so the form can't reveal which emails have accounts."""
    if rate_limited(f"forgot:{request.remote_addr}", limit=5, window=900):
        raise ApiError("Too many reset requests. Try again in 15 minutes.", 429)
    data = request.get_json(silent=True) or {}
    email = str(data.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError("Enter a valid email address.")
    d = db()
    row = d.execute("SELECT id, username FROM users WHERE LOWER(email) = ?", (email,)).fetchone()
    if row:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        d.execute(
            "INSERT INTO password_resets (user_id, token_hash, expires_at, used, created_at) VALUES (?, ?, ?, 0, ?)",
            (row["id"], _hash_token(token), (now + RESET_TTL).isoformat(timespec="microseconds"), now_iso()),
        )
        d.commit()
        link = f"{app_base_url()}/reset?token={token}"
        send_email(
            email,
            "Reset your DevX password",
            f"Hi {row['username']},\n\nUse this link to choose a new password. It expires in 1 hour "
            f"and works once:\n\n{link}\n\nIf you didn't ask for this, you can ignore this email.",
        )
    return jsonify(ok=True, message="If an account uses that email, a reset link is on its way.")


@app.post("/api/auth/reset")
def reset_password():
    if rate_limited(f"reset:{request.remote_addr}", limit=10, window=900):
        raise ApiError("Too many attempts. Try again in 15 minutes.", 429)
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    password = str(data.get("password") or "")
    if len(password) < 8 or len(password) > 200:
        raise ApiError("Password must be 8–200 characters.")
    d = db()
    row = d.execute("SELECT * FROM password_resets WHERE token_hash = ?", (_hash_token(token),)).fetchone() if token else None
    invalid = ApiError("This reset link is invalid or has expired. Request a new one.", 400)
    if not row or row["used"]:
        raise invalid
    if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
        raise invalid
    d.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), row["user_id"]))
    d.execute("UPDATE password_resets SET used = 1 WHERE user_id = ?", (row["user_id"],))
    d.commit()
    session.clear()
    return jsonify(ok=True)


@app.get("/api/auth/me")
def auth_me():
    u = current()
    return jsonify(user=user_full(u, private=True) if u else None)


@app.post("/api/auth/password")
def change_password():
    u = need_user()
    data = request.get_json(silent=True) or {}
    if not check_password_hash(u["password_hash"], str(data.get("current") or "")):
        raise ApiError("Your current password is incorrect.", 400)
    new = str(data.get("new") or "")
    if len(new) < 8 or len(new) > 200:
        raise ApiError("New password must be 8–200 characters.")
    d = db()
    d.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), u["id"]))
    d.commit()
    return jsonify(ok=True)


@app.delete("/api/me")
def delete_account():
    u = need_user()
    data = request.get_json(silent=True) or {}
    if not check_password_hash(u["password_hash"], str(data.get("password") or "")):
        raise ApiError("Password is incorrect.", 400)
    d = db()
    d.execute("DELETE FROM users WHERE id = ?", (u["id"],))
    d.commit()
    session.clear()
    return jsonify(ok=True)


# --------------------------------------------------------------------------- #
# Profile settings & media
# --------------------------------------------------------------------------- #
@app.patch("/api/me")
def update_me():
    u = need_user()
    data = request.get_json(silent=True) or {}
    sets, vals = [], []

    if "display_name" in data:
        v = str(data["display_name"] or "").strip()
        if not v or len(v) > NAME_MAX:
            raise ApiError(f"Display name is required (max {NAME_MAX} characters).")
        sets.append("display_name = ?"); vals.append(v)
    if "bio" in data:
        v = str(data["bio"] or "").strip()
        if len(v) > BIO_MAX:
            raise ApiError(f"Bio must be {BIO_MAX} characters or fewer.")
        sets.append("bio = ?"); vals.append(v)
    if "location" in data:
        v = str(data["location"] or "").strip()[:30]
        sets.append("location = ?"); vals.append(v)
    if "website" in data:
        v = str(data["website"] or "").strip()
        if v and (len(v) > 100 or not URL_RE.match(v)):
            raise ApiError("Website must be a valid http(s) link.")
        sets.append("website = ?"); vals.append(v)
    if "tech" in data:
        sets.append("tech = ?"); vals.append(normalize_tech(str(data["tech"] or "")))
    if "email" in data:
        v = str(data["email"] or "").strip().lower()
        if not EMAIL_RE.match(v) or len(v) > 254:
            raise ApiError("Enter a valid email address.")
        if db().execute("SELECT id FROM users WHERE LOWER(email) = ? AND id <> ?", (v, u["id"])).fetchone():
            raise ApiError("That email is already registered.", 409)
        sets.append("email = ?"); vals.append(v)
    if "linkedin" in data:
        v = str(data["linkedin"] or "").strip()
        if v and (len(v) > 120 or not URL_RE.match(v) or "linkedin.com/" not in v.lower()):
            raise ApiError("LinkedIn must be a link to linkedin.com.")
        sets.append("linkedin = ?"); vals.append(v)
    for field in ("avatar_media_id", "banner_media_id"):
        if field in data:
            mid = data[field]
            if mid in (None, ""):
                sets.append(f"{field} = ?"); vals.append(None)
            else:
                mid = to_int(mid, "image")
                validate_media(u["id"], [mid])
                sets.append(f"{field} = ?"); vals.append(mid)

    d = db()
    if sets:
        d.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals + [u["id"]])
        d.commit()
    if "open_to_work" in data or "available_for" in data:
        set_dev_profile(
            u["id"],
            open_to_work=bool(data.get("open_to_work")) if "open_to_work" in data else None,
            available_for=str(data.get("available_for") or "").strip()[:60] if "available_for" in data else None,
        )
    g.me = d.execute("SELECT * FROM users WHERE id = ?", (u["id"],)).fetchone()
    return jsonify(user=user_full(g.me, private=True))


MAX_FILE_BYTES = 10 * 1024 * 1024
TEXT_EXTS = {
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".toml", ".log", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb",
    ".php", ".sql", ".sh", ".css", ".ini", ".xml",
}
ALLOWED_TYPES_TEXT = ("Allowed: images (PNG, JPEG, GIF, WEBP), PDF, ZIP, and common text or source files.")

# --------------------------------------------------------------------------- #
# Blob storage: rows in the database by default, or an S3-compatible bucket
# (Cloudflare R2, AWS S3, Supabase Storage, ...) when S3_BUCKET is set.
# --------------------------------------------------------------------------- #
_s3_obj = None


def _s3():
    global _s3_obj
    if _s3_obj is None:
        import boto3
        _s3_obj = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID") or None,
            aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY") or None,
            region_name=os.environ.get("S3_REGION", "auto"),
        )
    return _s3_obj


def store_blob(data: bytes, mime: str):
    """Return (bytes_for_db, storage_key). With S3 configured the bytes leave the database."""
    bucket = os.environ.get("S3_BUCKET", "").strip()
    if bucket:
        key = f"media/{secrets.token_hex(16)}"
        _s3().put_object(Bucket=bucket, Key=key, Body=data, ContentType=mime)
        return b"", key
    return data, ""


def load_blob(row) -> bytes:
    if row["storage_key"]:
        bucket = os.environ.get("S3_BUCKET", "").strip()
        return _s3().get_object(Bucket=bucket, Key=row["storage_key"])["Body"].read()
    return bytes(row["data"])


def delete_blob(storage_key: str) -> None:
    bucket = os.environ.get("S3_BUCKET", "").strip()
    if storage_key and bucket:
        try:
            _s3().delete_object(Bucket=bucket, Key=storage_key)
        except Exception:
            log.exception("Could not delete stored object %s", storage_key)


def clean_filename(raw: str) -> str:
    name = os.path.basename(str(raw or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    return name[:120] or "attachment"


def classify_upload(data: bytes, filename: str):
    """Return (mime, kind) for an accepted upload, or raise ApiError. kind: image | file."""
    if not data:
        raise ApiError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ApiError("Files must be 10 MB or smaller.", 413)
    img = sniff_image(data)
    if img:
        if len(data) > MAX_IMAGE_BYTES:
            raise ApiError("Images must be 5 MB or smaller.", 413)
        return img, "image"
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".pdf" and data[:5] == b"%PDF-":
        return "application/pdf", "file"
    if ext == ".zip" and data[:4] == b"PK\x03\x04":
        return "application/zip", "file"
    if ext in TEXT_EXTS:
        if b"\x00" in data[:8192]:
            raise ApiError("That file doesn't look like text.", 415)
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise ApiError("Text files must be UTF-8 encoded.", 415)
        return "text/plain; charset=utf-8", "file"
    raise ApiError("Unsupported file type. " + ALLOWED_TYPES_TEXT, 415)


def attachment_out(r) -> dict:
    mime = r["mime"] or ""
    return {
        "id": r["media_id"],
        "url": media_url(r["media_id"]),
        "kind": "image" if mime.startswith("image/") else "file",
        "name": r["filename"] or "attachment",
        "size": r["size"] or 0,
        "mime": mime,
    }


@app.post("/api/media")
def upload_media():
    u = need_user()
    if rate_limited(f"upload:{u['id']}", limit=60, window=600):
        raise ApiError("You're uploading too fast. Try again in a few minutes.", 429)
    f = request.files.get("file")
    if not f:
        raise ApiError("No file was uploaded.")
    filename = clean_filename(f.filename)
    data = f.read(MAX_FILE_BYTES + 1)
    mime, kind = classify_upload(data, filename)
    stored, key = store_blob(data, mime)
    d = db()
    mid = d.execute(
        "INSERT INTO media (user_id, mime, data, size, filename, storage_key, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (u["id"], mime, stored, len(data), filename, key, now_iso()),
    ).lastrowid
    d.commit()
    return jsonify(id=mid, url=media_url(mid), kind=kind, name=filename, size=len(data), mime=mime), 201


@app.get("/media/<int:mid>")
def get_media(mid):
    row = db().execute(
        "SELECT mime, data, storage_key, filename FROM media WHERE id = ?", (mid,)).fetchone()
    if not row:
        abort(404)
    resp = Response(load_blob(row), mimetype=row["mime"])
    if not row["mime"].startswith("image/"):
        # Documents and source files always download. Serving them inline could run
        # active content from our origin.
        name = row["filename"] or "attachment"
        resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(name)}"
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


# --------------------------------------------------------------------------- #
# Posts
# --------------------------------------------------------------------------- #
@app.post("/api/posts")
def create_post():
    u = need_user()
    if rate_limited(f"post:{u['id']}", limit=30, window=600):
        raise ApiError("You're posting too fast. Take a short break and try again.", 429)
    data = request.get_json(silent=True) or {}
    body = str(data.get("body") or "").strip()
    code = str(data.get("code") or "").rstrip()
    code_lang = str(data.get("code_lang") or "").strip().lower()
    media_ids = [to_int(x, "image") for x in (data.get("media_ids") or [])]
    reply_to = data.get("reply_to")
    quote_id = data.get("quote_id")

    if len(body) > POST_MAX:
        raise ApiError(f"Posts are limited to {POST_MAX} characters.")
    if len(code) > CODE_MAX:
        raise ApiError(f"Code snippets are limited to {CODE_MAX} characters.")
    if code and code_lang not in LANGS:
        code_lang = "text"
    if not code:
        code_lang = ""
    if len(media_ids) > MAX_MEDIA_PER_POST:
        raise ApiError(f"You can attach up to {MAX_MEDIA_PER_POST} images.")
    if not (body or code or media_ids or quote_id):
        raise ApiError("Your post is empty.")
    media_ids = validate_media(u["id"], media_ids)

    d = db()
    parent_author = None
    parent_id = None
    if reply_to:
        parent_id = to_int(reply_to)
        row = d.execute("SELECT user_id FROM posts WHERE id = ?", (parent_id,)).fetchone()
        if not row:
            raise ApiError("That post no longer exists.", 404)
        parent_author = row["user_id"]
    quote_author = None
    qid = None
    if quote_id:
        qid = to_int(quote_id)
        row = d.execute("SELECT user_id FROM posts WHERE id = ?", (qid,)).fetchone()
        if not row:
            raise ApiError("The quoted post no longer exists.", 404)
        quote_author = row["user_id"]

    pid = d.execute(
        "INSERT INTO posts (user_id, body, parent_id, quote_id, code, code_lang, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (u["id"], body, parent_id, qid, code, code_lang, now_iso()),
    ).lastrowid

    for pos, mid in enumerate(media_ids):
        d.execute("INSERT INTO post_media (post_id, media_id, position) VALUES (?, ?, ?)", (pid, mid, pos))

    for tag in sorted({t.lower() for t in TAG_RE.findall(body)}):
        d.execute("INSERT INTO hashtags (post_id, tag) VALUES (?, ?)", (pid, tag))

    names = sorted({m.lower() for m in MENTION_RE.findall(body)})
    if names:
        rows = d.execute(
            f"SELECT id FROM users WHERE LOWER(username) IN ({ph_of(names)})", names
        ).fetchall()
        for r in rows:
            if r["id"] not in (parent_author, quote_author):
                notify(r["id"], u["id"], "mention", pid)
    if parent_author:
        notify(parent_author, u["id"], "reply", pid)
    if quote_author:
        notify(quote_author, u["id"], "quote", pid)
    d.commit()
    return jsonify(post=load_posts([pid], u["id"])[pid]), 201


@app.get("/api/posts/<int:pid>")
def get_post(pid):
    viewer = viewer_id()
    posts = load_posts([pid], viewer)
    if pid not in posts:
        raise ApiError("This post doesn't exist (or was deleted).", 404)
    post = posts[pid]
    thread = []
    parent = post["parent_id"]
    depth = 0
    while parent and depth < 10:
        p = load_posts([parent], viewer, with_quote=False).get(parent)
        if not p:
            break
        thread.insert(0, p)
        parent = p["parent_id"]
        depth += 1
    return jsonify(post=post, thread=thread)


@app.get("/api/posts/<int:pid>/replies")
def get_replies(pid):
    viewer = viewer_id()
    d = db()
    rows = d.execute(
        "SELECT id FROM posts WHERE parent_id = ? ORDER BY id ASC LIMIT 100", (pid,)
    ).fetchall()
    posts = load_posts([r["id"] for r in rows], viewer)
    return jsonify(items=[posts[r["id"]] for r in rows if r["id"] in posts])


@app.delete("/api/posts/<int:pid>")
def delete_post(pid):
    u = need_user()
    d = db()
    row = d.execute("SELECT user_id FROM posts WHERE id = ?", (pid,)).fetchone()
    if not row:
        raise ApiError("That post doesn't exist.", 404)
    if row["user_id"] != u["id"]:
        raise ApiError("You can only delete your own posts.", 403)
    media_rows = d.execute(
        "SELECT m.id, m.storage_key FROM post_media pm JOIN media m ON m.id = pm.media_id WHERE pm.post_id = ?",
        (pid,)).fetchall()
    d.execute("DELETE FROM posts WHERE id = ?", (pid,))
    for m in media_rows:
        d.execute("DELETE FROM media WHERE id = ?", (m["id"],))
        delete_blob(m["storage_key"])
    d.commit()
    return jsonify(ok=True)


def _toggle_on(table, post_id, extra_notify=None):
    u = need_user()
    d = db()
    if not d.execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone():
        raise ApiError("That post doesn't exist.", 404)
    exists = d.execute(f"SELECT id FROM {table} WHERE user_id = ? AND post_id = ?", (u["id"], post_id)).fetchone()
    if not exists:
        d.execute(f"INSERT INTO {table} (user_id, post_id, created_at) VALUES (?, ?, ?)", (u["id"], post_id, now_iso()))
        if extra_notify:
            author = d.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,)).fetchone()["user_id"]
            notify(author, u["id"], extra_notify, post_id)
    d.commit()
    return u


def _toggle_off(table, post_id):
    u = need_user()
    d = db()
    d.execute(f"DELETE FROM {table} WHERE user_id = ? AND post_id = ?", (u["id"], post_id))
    d.commit()
    return u


@app.post("/api/posts/<int:pid>/like")
def like_post(pid):
    _toggle_on("likes", pid, "like")
    return jsonify(liked=True, like_count=_count_by(db(), "likes", [pid]).get(pid, 0))


@app.delete("/api/posts/<int:pid>/like")
def unlike_post(pid):
    _toggle_off("likes", pid)
    return jsonify(liked=False, like_count=_count_by(db(), "likes", [pid]).get(pid, 0))


@app.post("/api/posts/<int:pid>/repost")
def repost(pid):
    _toggle_on("reposts", pid, "repost")
    return jsonify(reposted=True, repost_count=_count_by(db(), "reposts", [pid]).get(pid, 0))


@app.delete("/api/posts/<int:pid>/repost")
def unrepost(pid):
    _toggle_off("reposts", pid)
    return jsonify(reposted=False, repost_count=_count_by(db(), "reposts", [pid]).get(pid, 0))


@app.post("/api/posts/<int:pid>/bookmark")
def bookmark(pid):
    _toggle_on("bookmarks", pid)
    return jsonify(bookmarked=True)


@app.delete("/api/posts/<int:pid>/bookmark")
def unbookmark(pid):
    _toggle_off("bookmarks", pid)
    return jsonify(bookmarked=False)


@app.get("/api/bookmarks")
def list_bookmarks():
    u = need_user()
    d = db()
    rows = d.execute(
        "SELECT id, post_id FROM bookmarks WHERE user_id = ? AND id < ? ORDER BY id DESC LIMIT ?",
        (u["id"], id_before(), PAGE + 1),
    ).fetchall()
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]
    posts = load_posts([r["post_id"] for r in rows], u["id"])
    items = [{"kind": "post", "post": posts[r["post_id"]], "sort_at": str(r["id"])}
             for r in rows if r["post_id"] in posts]
    return jsonify(items=items, next=str(rows[-1]["id"]) if has_more and rows else None)


# --------------------------------------------------------------------------- #
# Timelines & discovery
# --------------------------------------------------------------------------- #
@app.get("/api/timeline")
def timeline():
    u = need_user()
    d = db()
    ids = [r["followee_id"] for r in d.execute(
        "SELECT followee_id FROM follows WHERE follower_id = ?", (u["id"],)).fetchall()]
    ids.append(u["id"])
    return jsonify(feed_page("timeline", ids, ts_before(), u["id"]))


@app.get("/api/explore")
def explore():
    viewer = viewer_id()
    d = db()
    rows = d.execute(
        "SELECT id FROM posts WHERE id < ? ORDER BY id DESC LIMIT ?", (id_before(), PAGE + 1)
    ).fetchall()
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]
    posts = load_posts([r["id"] for r in rows], viewer)
    items = [{"kind": "post", "post": posts[r["id"]], "sort_at": str(r["id"])} for r in rows if r["id"] in posts]
    return jsonify(items=items, next=str(rows[-1]["id"]) if has_more and rows else None)


@app.get("/api/trends")
def trends():
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="microseconds")
    rows = db().execute(
        """SELECT h.tag, COUNT(*) AS c FROM hashtags h
           JOIN posts p ON p.id = h.post_id
           WHERE p.created_at >= ? GROUP BY h.tag ORDER BY c DESC, h.tag ASC LIMIT 10""",
        (since,),
    ).fetchall()
    return jsonify(tags=[{"tag": r["tag"], "count": r["c"]} for r in rows])


@app.get("/api/who-to-follow")
def who_to_follow():
    u = current()
    d = db()
    if u:
        rows = d.execute(
            """SELECT * FROM users WHERE id <> ? AND id NOT IN
               (SELECT followee_id FROM follows WHERE follower_id = ?)
               ORDER BY id DESC LIMIT 5""",
            (u["id"], u["id"]),
        ).fetchall()
    else:
        rows = d.execute("SELECT * FROM users ORDER BY id DESC LIMIT 5").fetchall()
    return jsonify(users=[user_lite(r) for r in rows])


@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()[:100]
    lang = request.args.get("lang", "").strip().lower()
    viewer = viewer_id()
    if not q:
        return jsonify(posts=[], people=[], tags=[], projects=[])
    d = db()
    if q.startswith("#"):
        tag = q[1:].lower()
        ids = [r["post_id"] for r in d.execute(
            "SELECT post_id FROM hashtags WHERE tag = ? ORDER BY post_id DESC LIMIT 20", (tag,)).fetchall()]
        if lang:
            ids = [r["id"] for r in d.execute(
                f"SELECT id FROM posts WHERE id IN ({ph_of(ids)}) AND code_lang = ?", [*ids, lang]).fetchall()] if ids else []
    else:
        pat = f"%{like_escape(q.lower())}%"
        sql = "SELECT id FROM posts WHERE LOWER(body) LIKE ? ESCAPE '!'"
        params = [pat]
        if lang:
            sql += " AND code_lang = ?"
            params.append(lang)
        ids = [r["id"] for r in d.execute(sql + " ORDER BY id DESC LIMIT 20", params).fetchall()]
    posts = load_posts(ids, viewer)
    pat = f"%{like_escape(q.lower().lstrip('#@'))}%"
    people = d.execute(
        """SELECT * FROM users WHERE LOWER(username) LIKE ? ESCAPE '!'
           OR LOWER(display_name) LIKE ? ESCAPE '!' ORDER BY id DESC LIMIT 20""",
        (pat, pat),
    ).fetchall()
    tags = d.execute(
        """SELECT tag, COUNT(*) AS c FROM hashtags WHERE tag LIKE ? ESCAPE '!'
           GROUP BY tag ORDER BY c DESC LIMIT 10""",
        (f"%{like_escape(q.lower().lstrip('#'))}%",),
    ).fetchall()
    projects = d.execute(
        """SELECT p.*, u.username, u.display_name, u.avatar_media_id FROM projects p
           JOIN users u ON u.id = p.user_id
           WHERE LOWER(p.title) LIKE ? ESCAPE '!' OR LOWER(p.description) LIKE ? ESCAPE '!'
              OR (',' || p.tags || ',') LIKE ? ESCAPE '!'
           ORDER BY p.id DESC LIMIT 10""",
        (pat, pat, f"%,{like_escape(q.lower().lstrip('#'))}%"),
    ).fetchall()
    return jsonify(
        posts=[posts[i] for i in ids if i in posts],
        people=[user_lite(r) for r in people],
        tags=[{"tag": r["tag"], "count": r["c"]} for r in tags],
        projects=_project_out(projects, viewer),
    )


# --------------------------------------------------------------------------- #
# Users, profiles & follows
# --------------------------------------------------------------------------- #
@app.get("/api/users/<username>")
def get_user(username):
    viewer = current()
    row = find_user(username)
    d = db()
    following = follows_you = False
    if viewer and viewer["id"] != row["id"]:
        following = bool(d.execute("SELECT id FROM follows WHERE follower_id = ? AND followee_id = ?",
                                   (viewer["id"], row["id"])).fetchone())
        follows_you = bool(d.execute("SELECT id FROM follows WHERE follower_id = ? AND followee_id = ?",
                                     (row["id"], viewer["id"])).fetchone())
    return jsonify(
        user=user_full(row),
        stats=user_stats(row["id"]),
        dev=dev_accounts_for(row["id"]),
        following=following,
        follows_you=follows_you,
        is_me=bool(viewer) and viewer["id"] == row["id"],
    )


@app.get("/api/users/<username>/posts")
def user_posts(username):
    viewer = viewer_id()
    row = find_user(username)
    tab = request.args.get("tab", "posts")
    if tab not in ("posts", "replies", "media", "likes"):
        raise ApiError("Unknown tab.", 400)
    return jsonify(feed_page(tab, [row["id"]], ts_before(), viewer))


@app.route("/api/users/<username>/follow", methods=["POST", "DELETE"])
def follow_toggle(username):
    u = need_user()
    row = find_user(username)
    if row["id"] == u["id"]:
        raise ApiError("You can't follow yourself.", 400)
    d = db()
    if request.method == "POST":
        if not d.execute("SELECT id FROM follows WHERE follower_id = ? AND followee_id = ?",
                         (u["id"], row["id"])).fetchone():
            d.execute("INSERT INTO follows (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
                      (u["id"], row["id"], now_iso()))
            notify(row["id"], u["id"], "follow")
    else:
        d.execute("DELETE FROM follows WHERE follower_id = ? AND followee_id = ?", (u["id"], row["id"]))
    d.commit()
    following = request.method == "POST"
    return jsonify(following=following, followers=user_stats(row["id"])["followers"])


@app.get("/api/users/<username>/<kind>")
def follow_list(username, kind):
    if kind not in ("followers", "following"):
        abort(404)
    viewer = viewer_id()
    row = find_user(username)
    d = db()
    if kind == "followers":
        rows = d.execute(
            """SELECT f.id AS fid, u.* FROM follows f JOIN users u ON u.id = f.follower_id
               WHERE f.followee_id = ? AND f.id < ? ORDER BY f.id DESC LIMIT ?""",
            (row["id"], id_before(), PAGE + 1),
        ).fetchall()
    else:
        rows = d.execute(
            """SELECT f.id AS fid, u.* FROM follows f JOIN users u ON u.id = f.followee_id
               WHERE f.follower_id = ? AND f.id < ? ORDER BY f.id DESC LIMIT ?""",
            (row["id"], id_before(), PAGE + 1),
        ).fetchall()
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]
    followed = set()
    if viewer and rows:
        ids = [r["id"] for r in rows]
        followed = {r["followee_id"] for r in d.execute(
            f"SELECT followee_id FROM follows WHERE follower_id = ? AND followee_id IN ({ph_of(ids)})",
            [viewer, *ids]).fetchall()}
    users = []
    for r in rows:
        item = user_lite(r)
        item["following"] = r["id"] in followed
        item["is_me"] = viewer == r["id"]
        users.append(item)
    return jsonify(users=users, next=str(rows[-1]["fid"]) if has_more and rows else None)


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
@app.get("/api/notifications")
def list_notifications():
    u = need_user()
    d = db()
    rows = d.execute(
        """SELECT n.id, n.type, n.post_id, n.link, n.is_read, n.created_at,
                  a.id AS actor_id, a.username, a.display_name, a.avatar_media_id
           FROM notifications n JOIN users a ON a.id = n.actor_id
           WHERE n.recipient_id = ? AND n.id < ? ORDER BY n.id DESC LIMIT ?""",
        (u["id"], id_before(), PAGE + 1),
    ).fetchall()
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]
    post_ids = [r["post_id"] for r in rows if r["post_id"]]
    posts = load_posts(post_ids, u["id"], with_quote=False) if post_ids else {}
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "type": r["type"],
            "link": r["link"] or None,
            "is_read": bool(r["is_read"]),
            "created_at": r["created_at"],
            "actor": {"id": r["actor_id"], "username": r["username"],
                      "display_name": r["display_name"] or r["username"],
                      "avatar_url": media_url(r["avatar_media_id"])},
            "post": posts.get(r["post_id"]) if r["post_id"] else None,
        })
    return jsonify(items=items, next=str(rows[-1]["id"]) if has_more and rows else None)


@app.post("/api/notifications/read")
def read_notifications():
    u = need_user()
    d = db()
    d.execute("UPDATE notifications SET is_read = 1 WHERE recipient_id = ? AND is_read = 0", (u["id"],))
    d.commit()
    return jsonify(ok=True)


@app.get("/api/counts")
def counts():
    u = current()
    if not u:
        return jsonify(notifications=0, messages=0)
    d = db()
    n = d.execute("SELECT COUNT(*) AS c FROM notifications WHERE recipient_id = ? AND is_read = 0",
                  (u["id"],)).fetchone()["c"]
    m = d.execute(
        """SELECT COUNT(*) AS c FROM messages m JOIN conversations c ON c.id = m.conversation_id
           WHERE (c.user_a = ? OR c.user_b = ?) AND m.sender_id <> ? AND m.is_read = 0""",
        (u["id"], u["id"], u["id"]),
    ).fetchone()["c"]
    return jsonify(notifications=n, messages=m)


# --------------------------------------------------------------------------- #
# Direct messages
# --------------------------------------------------------------------------- #
def _conversation_or_404(cid: int, uid: int):
    row = db().execute("SELECT * FROM conversations WHERE id = ? AND (user_a = ? OR user_b = ?)",
                       (cid, uid, uid)).fetchone()
    if not row:
        raise ApiError("Conversation not found.", 404)
    return row


def _other_user_id(conv, uid):
    return conv["user_b"] if conv["user_a"] == uid else conv["user_a"]


@app.get("/api/conversations")
def list_conversations():
    u = need_user()
    d = db()
    convs = d.execute(
        "SELECT * FROM conversations WHERE user_a = ? OR user_b = ? ORDER BY updated_at DESC LIMIT 100",
        (u["id"], u["id"]),
    ).fetchall()
    out = []
    for c in convs:
        other = d.execute("SELECT * FROM users WHERE id = ?", (_other_user_id(c, u["id"]),)).fetchone()
        if not other:
            continue
        last = d.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
                         (c["id"],)).fetchone()
        unread = d.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE conversation_id = ? AND sender_id <> ? AND is_read = 0",
            (c["id"], u["id"])).fetchone()["c"]
        preview = None
        if last:
            preview = {"text": last["body"] or ("📷 Image" if last["media_id"] else ""),
                       "mine": last["sender_id"] == u["id"], "created_at": last["created_at"]}
        out.append({"id": c["id"], "user": user_lite(other), "last": preview,
                    "unread": unread, "updated_at": c["updated_at"]})
    return jsonify(conversations=out)


@app.post("/api/conversations")
def open_conversation():
    u = need_user()
    data = request.get_json(silent=True) or {}
    other = find_user(str(data.get("username") or "").strip())
    if other["id"] == u["id"]:
        raise ApiError("You can't message yourself.", 400)
    a, b = sorted([u["id"], other["id"]])
    d = db()
    row = d.execute("SELECT id FROM conversations WHERE user_a = ? AND user_b = ?", (a, b)).fetchone()
    if row:
        cid = row["id"]
    else:
        ts = now_iso()
        cid = d.execute("INSERT INTO conversations (user_a, user_b, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (a, b, ts, ts)).lastrowid
        d.commit()
    return jsonify(id=cid, user=user_lite(other)), 201


@app.get("/api/conversations/<int:cid>/messages")
def list_messages(cid):
    u = need_user()
    conv = _conversation_or_404(cid, u["id"])
    d = db()
    other = d.execute("SELECT * FROM users WHERE id = ?", (_other_user_id(conv, u["id"]),)).fetchone()
    after = request.args.get("after", "")
    if after.isdigit():
        rows = d.execute(
            "SELECT msg.*, md.mime AS media_mime, md.filename AS media_name, md.size AS media_size FROM messages msg LEFT JOIN media md ON md.id = msg.media_id WHERE msg.conversation_id = ? AND msg.id > ? ORDER BY msg.id ASC LIMIT 100",
            (cid, int(after))).fetchall()
        has_more = False
    else:
        rows = d.execute(
            "SELECT msg.*, md.mime AS media_mime, md.filename AS media_name, md.size AS media_size FROM messages msg LEFT JOIN media md ON md.id = msg.media_id WHERE msg.conversation_id = ? AND msg.id < ? ORDER BY msg.id DESC LIMIT ?",
            (cid, id_before(), PAGE + 1)).fetchall()
        has_more = len(rows) > PAGE
        rows = list(reversed(rows[:PAGE]))
    d.execute("UPDATE messages SET is_read = 1 WHERE conversation_id = ? AND sender_id <> ? AND is_read = 0",
              (cid, u["id"]))
    d.execute("UPDATE notifications SET is_read = 1 WHERE recipient_id = ? AND type = 'message' AND link = ?",
              (u["id"], f"/messages/{cid}"))
    d.commit()
    return jsonify(
        messages=[serialize_message(r, u["id"]) for r in rows],
        next=str(rows[0]["id"]) if has_more and rows else None,
        user=user_lite(other),
    )


@app.post("/api/conversations/<int:cid>/messages")
def send_message(cid):
    u = need_user()
    conv = _conversation_or_404(cid, u["id"])
    data = request.get_json(silent=True) or {}
    body = str(data.get("body") or "").strip()
    media_id = data.get("media_id")
    if len(body) > DM_MAX:
        raise ApiError(f"Messages are limited to {DM_MAX} characters.")
    mid = None
    if media_id not in (None, ""):
        mid = to_int(media_id, "image")
        validate_media(u["id"], [mid])
    if not body and not mid:
        raise ApiError("Write a message or attach an image.")
    d = db()
    ts = now_iso()
    msg_id = d.execute(
        "INSERT INTO messages (conversation_id, sender_id, body, media_id, is_read, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (conv["id"], u["id"], body, mid, ts),
    ).lastrowid
    d.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conv["id"]))
    other_id = _other_user_id(conv, u["id"])
    link = f"/messages/{conv['id']}"
    if not d.execute(
        "SELECT id FROM notifications WHERE recipient_id = ? AND actor_id = ? AND type = 'message' "
        "AND is_read = 0 AND link = ?", (other_id, u["id"], link)).fetchone():
        notify(other_id, u["id"], "message", None, link=link)
    d.commit()
    row = d.execute(
        "SELECT msg.*, md.mime AS media_mime, md.filename AS media_name, md.size AS media_size "
        "FROM messages msg LEFT JOIN media md ON md.id = msg.media_id WHERE msg.id = ?", (msg_id,)).fetchone()
    return jsonify(message=serialize_message(row, u["id"])), 201


# --------------------------------------------------------------------------- #
# Developer integrations (GitHub, GitLab, DEV, npm)
# --------------------------------------------------------------------------- #
DEV_TTL = timedelta(hours=6)
LINK_TTL = timedelta(hours=24)


def _fresh(ts: str, ttl: timedelta) -> bool:
    if not ts:
        return False
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(ts) < ttl
    except ValueError:
        return False


def set_dev_profile(uid: int, open_to_work=None, available_for=None):
    d = db()
    row = d.execute("SELECT id, open_to_work, available_for FROM dev_profiles WHERE user_id = ?", (uid,)).fetchone()
    otw = int(open_to_work) if open_to_work is not None else (row["open_to_work"] if row else 0)
    avail = available_for if available_for is not None else (row["available_for"] if row else "")
    if row:
        d.execute("UPDATE dev_profiles SET open_to_work = ?, available_for = ? WHERE id = ?", (otw, avail, row["id"]))
    else:
        d.execute("INSERT INTO dev_profiles (user_id, open_to_work, available_for) VALUES (?, ?, ?)", (uid, otw, avail))
    d.commit()


def dev_accounts_for(uid: int, include_secret=False, refresh=False, network=True) -> dict:
    """Linked developer accounts for a user. Stale data is refreshed (at most once per TTL)."""
    d = db()
    accounts = {}
    for r in d.execute("SELECT * FROM dev_accounts WHERE user_id = ?", (uid,)).fetchall():
        prov = r["provider"]
        if prov not in devint.PROVIDERS:
            continue
        data = json.loads(r["data"] or "{}")
        error, fetched = r["error"], r["fetched_at"]
        if network and (refresh or not _fresh(fetched, DEV_TTL)):
            try:
                data = devint.fetch_profile(prov, r["handle"])
                error, fetched = "", now_iso()
                d.execute("UPDATE dev_accounts SET data = ?, fetched_at = ?, error = '' WHERE id = ?",
                          (json.dumps(data), fetched, r["id"]))
            except ProviderError as e:
                # keep the last good data; remember the failure and don't retry for a full TTL
                error, fetched = e.code, now_iso()
                d.execute("UPDATE dev_accounts SET error = ?, fetched_at = ? WHERE id = ?", (error, fetched, r["id"]))
            d.commit()
        acc = {
            "provider": prov,
            "label": devint.PROVIDERS[prov]["label"],
            "handle": r["handle"],
            "verified": bool(r["verified"]),
            "data": data,
            "fetched_at": fetched,
            "error": error,
        }
        if include_secret and not r["verified"] and r["verify_code"]:
            acc["verify_code"] = r["verify_code"]
        accounts[prov] = acc
    prof = d.execute("SELECT open_to_work, available_for FROM dev_profiles WHERE user_id = ?", (uid,)).fetchone()
    return {
        "accounts": accounts,
        "open_to_work": bool(prof and prof["open_to_work"]),
        "available_for": (prof["available_for"] if prof else "") or "",
    }


def _provider_or_404(provider: str):
    if provider not in devint.PROVIDERS:
        raise ApiError("Unknown platform.", 404)
    return devint.PROVIDERS[provider]


@app.get("/api/devs/providers")
def dev_providers():
    return jsonify(providers=[
        {"id": k, "label": v["label"], "verify": v["verify"], "placeholder": v["placeholder"], "hint": v["hint"]}
        for k, v in devint.PROVIDERS.items()
    ])


@app.get("/api/me/dev")
def my_dev():
    u = need_user()
    return jsonify(dev_accounts_for(u["id"], include_secret=True))


@app.post("/api/me/dev/<provider>")
def link_dev_account(provider):
    u = need_user()
    spec = _provider_or_404(provider)
    data = request.get_json(silent=True) or {}
    handle = str(data.get("handle") or "").strip().lstrip("@")
    if not devint.valid_handle(provider, handle):
        raise ApiError(f"That doesn't look like a valid {spec['label']} username.")
    d = db()
    if spec["verify"]:
        claimed = d.execute(
            "SELECT user_id FROM dev_accounts WHERE provider = ? AND LOWER(handle) = LOWER(?) AND verified = 1 AND user_id <> ?",
            (provider, handle, u["id"])).fetchone()
        if claimed:
            raise ApiError(f"That {spec['label']} account is already linked to another DevX profile.", 409)
    try:
        profile = devint.fetch_profile(provider, handle)
    except ProviderError as e:
        if e.code == "not_found":
            raise ApiError(f"No {spec['label']} account called “{handle}” was found.", 404)
        if e.code == "rate_limited":
            raise ApiError(f"{spec['label']} is rate-limiting us right now. Try again in a few minutes.", 429)
        raise ApiError(f"Couldn't reach {spec['label']}. Try again shortly.", 502)

    code = ("devx-" + secrets.token_hex(4)) if spec["verify"] else ""
    row = d.execute("SELECT id FROM dev_accounts WHERE user_id = ? AND provider = ?", (u["id"], provider)).fetchone()
    if row:
        d.execute("UPDATE dev_accounts SET handle = ?, verified = 0, verify_code = ?, data = ?, fetched_at = ?, error = '' WHERE id = ?",
                  (handle, code, json.dumps(profile), now_iso(), row["id"]))
    else:
        d.execute("INSERT INTO dev_accounts (user_id, provider, handle, verified, verify_code, data, fetched_at, error) "
                  "VALUES (?, ?, ?, 0, ?, ?, ?, '')",
                  (u["id"], provider, handle, code, json.dumps(profile), now_iso()))
    d.commit()
    return jsonify(dev_accounts_for(u["id"], include_secret=True, network=False)), 201


@app.post("/api/me/dev/<provider>/verify")
def verify_dev_account(provider):
    u = need_user()
    spec = _provider_or_404(provider)
    d = db()
    row = d.execute("SELECT * FROM dev_accounts WHERE user_id = ? AND provider = ?", (u["id"], provider)).fetchone()
    if not row:
        raise ApiError("Link the account first.", 404)
    if not spec["verify"]:
        raise ApiError(f"{spec['label']} accounts don't need verification.", 400)
    if row["verified"]:
        return jsonify(dev_accounts_for(u["id"], include_secret=True, network=False))
    try:
        bio = devint.github_bio(row["handle"])
    except ProviderError:
        raise ApiError(f"Couldn't reach {spec['label']} right now. Try again shortly.", 502)
    if not row["verify_code"] or row["verify_code"] not in bio:
        raise ApiError(f"We didn't find “{row['verify_code']}” in your {spec['label']} bio yet. "
                       "Save the bio, wait a few seconds, then try again.", 400)
    d.execute("UPDATE dev_accounts SET verified = 1, verify_code = '' WHERE id = ?", (row["id"],))
    d.commit()
    return jsonify(dev_accounts_for(u["id"], include_secret=True, network=False))


@app.post("/api/me/dev/<provider>/refresh")
def refresh_dev_account(provider):
    u = need_user()
    _provider_or_404(provider)
    return jsonify(dev_accounts_for(u["id"], include_secret=True, refresh=True))


@app.delete("/api/me/dev/<provider>")
def unlink_dev_account(provider):
    u = need_user()
    _provider_or_404(provider)
    d = db()
    d.execute("DELETE FROM dev_accounts WHERE user_id = ? AND provider = ?", (u["id"], provider))
    d.commit()
    return jsonify(dev_accounts_for(u["id"], include_secret=True, network=False))


@app.get("/api/devs")
def developer_directory():
    viewer = viewer_id()
    d = db()
    tech = request.args.get("tech", "").strip().lower()[:30]
    sql = "SELECT u.* FROM users u LEFT JOIN dev_profiles p ON p.user_id = u.id WHERE u.id < ?"
    params = [id_before()]
    if tech:
        sql += " AND (',' || REPLACE(LOWER(u.tech), ', ', ',') || ',') LIKE ? ESCAPE '!'"
        params.append(f"%,{like_escape(tech)},%")
    if request.args.get("available") == "1":
        sql += " AND p.open_to_work = 1"
    sql += " ORDER BY u.id DESC LIMIT ?"
    params.append(PAGE + 1)
    rows = d.execute(sql, params).fetchall()
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]
    following = set()
    if viewer and rows:
        ids = [r["id"] for r in rows]
        following = {x["followee_id"] for x in d.execute(
            f"SELECT followee_id FROM follows WHERE follower_id = ? AND followee_id IN ({ph_of(ids)})",
            [viewer, *ids]).fetchall()}
    users = []
    for r in rows:
        item = user_full(r)
        item["dev"] = dev_accounts_for(r["id"], network=False)
        item["is_me"] = viewer == r["id"]
        item["following"] = r["id"] in following
        users.append(item)
    return jsonify(users=users, next=str(rows[-1]["id"]) if has_more and rows else None)


@app.get("/api/link-preview")
def link_preview():
    """Preview card for GitHub repository links found in posts (cached 24h)."""
    url = request.args.get("url", "").strip()[:300]
    parsed = devint.parse_github_repo_url(url)
    if not parsed:
        return jsonify(preview=None)
    d = db()
    cached = d.execute("SELECT data, fetched_at FROM link_cache WHERE url = ?", (url,)).fetchone()
    if cached and _fresh(cached["fetched_at"], LINK_TTL):
        return jsonify(preview=json.loads(cached["data"]))
    try:
        preview = devint.github_repo(*parsed)
    except ProviderError as e:
        if e.code != "not_found":
            return jsonify(preview=json.loads(cached["data"]) if cached else None)
        preview = None  # cache the negative answer too
    payload = json.dumps(preview)
    if cached:
        d.execute("UPDATE link_cache SET data = ?, fetched_at = ? WHERE url = ?", (payload, now_iso(), url))
    else:
        d.execute("INSERT INTO link_cache (url, data, fetched_at) VALUES (?, ?, ?)", (url, payload, now_iso()))
    d.commit()
    return jsonify(preview=preview)


if not os.environ.get("DEVX_SKIP_INIT"):
    init_db()


# --------------------------------------------------------------------------- #
# Post editing
# --------------------------------------------------------------------------- #
@app.patch("/api/posts/<int:pid>")
def edit_post(pid):
    u = need_user()
    d = db()
    row = d.execute("SELECT user_id, quote_id FROM posts WHERE id = ?", (pid,)).fetchone()
    if not row:
        raise ApiError("That post doesn't exist.", 404)
    if row["user_id"] != u["id"]:
        raise ApiError("You can only edit your own posts.", 403)
    data = request.get_json(silent=True) or {}
    body = str(data.get("body") or "").strip()
    code = str(data.get("code") or "").rstrip()
    code_lang = str(data.get("code_lang") or "").strip().lower()
    if len(body) > POST_MAX:
        raise ApiError(f"Posts are limited to {POST_MAX} characters.")
    if len(code) > CODE_MAX:
        raise ApiError(f"Code snippets are limited to {CODE_MAX} characters.")
    if code and code_lang not in LANGS:
        code_lang = "text"
    if not code:
        code_lang = ""
    has_media = d.execute("SELECT 1 FROM post_media WHERE post_id = ? LIMIT 1", (pid,)).fetchone()
    if not (body or code or has_media or row["quote_id"]):
        raise ApiError("Your post is empty.")
    d.execute(
        "UPDATE posts SET body = ?, code = ?, code_lang = ?, edited_at = ? WHERE id = ?",
        (body, code, code_lang, now_iso(), pid),
    )
    d.execute("DELETE FROM hashtags WHERE post_id = ?", (pid,))
    for tag in sorted({t.lower() for t in TAG_RE.findall(body)}):
        d.execute("INSERT INTO hashtags (post_id, tag) VALUES (?, ?)", (pid, tag))
    d.commit()
    return jsonify(post=load_posts([pid], u["id"])[pid])


# --------------------------------------------------------------------------- #
# Shared helpers for projects and collaboration
# --------------------------------------------------------------------------- #
PROJECT_STATUSES = ("idea", "building", "shipped")
COLLAB_STATUSES = ("open", "closed")
TAG_ITEM_RE = re.compile(r"^[a-z0-9][a-z0-9+#._\-]{0,23}$")


def normalize_tags(raw, limit: int = 8) -> str:
    parts = raw if isinstance(raw, list) else re.split(r"[,\n]", str(raw or ""))
    seen, out = set(), []
    for part in parts:
        t = str(part).strip().lower()
        if not t:
            continue
        if not TAG_ITEM_RE.match(t):
            raise ApiError(f"Tag “{t[:30]}” may only use letters, numbers and + # . _ -.")
        if t not in seen:
            seen.add(t)
            out.append(t)
    if len(out) > limit:
        raise ApiError(f"Use at most {limit} tags.")
    return ",".join(out)


def _split_tags(raw: str) -> list:
    return [t for t in (raw or "").split(",") if t]


def validate_image(uid: int, mid: int) -> int:
    row = db().execute("SELECT mime FROM media WHERE id = ? AND user_id = ?", (mid, uid)).fetchone()
    if not row or not row["mime"].startswith("image/"):
        raise ApiError("Choose an image you uploaded.", 400)
    return mid


def _project_fields(data: dict, uid: int, partial: bool = False) -> dict:
    out = {}

    def has(key):
        return (key in data) if partial else True

    if has("title"):
        t = str(data.get("title") or "").strip()
        if not 1 <= len(t) <= 80:
            raise ApiError("Project names are 1–80 characters.")
        out["title"] = t
    if has("description"):
        t = str(data.get("description") or "").strip()
        if len(t) > 1000:
            raise ApiError("Descriptions are limited to 1000 characters.")
        out["description"] = t
    for key in ("repo_url", "live_url"):
        if has(key):
            v = str(data.get(key) or "").strip()
            if v and (len(v) > 200 or not URL_RE.match(v)):
                raise ApiError("Links must be valid http(s) URLs.")
            out[key] = v
    if has("status"):
        s = str(data.get("status") or "idea").strip().lower()
        if s not in PROJECT_STATUSES:
            raise ApiError("Status must be idea, building or shipped.")
        out["status"] = s
    if has("tags"):
        out["tags"] = normalize_tags(data.get("tags") or "")
    if has("screenshot_media_id"):
        mid = data.get("screenshot_media_id")
        out["screenshot_media_id"] = None if mid in (None, "") else validate_image(uid, to_int(mid, "image"))
    return out


def _project_rows(where: str, params: list, limit: int):
    return db().execute(
        f"""SELECT p.*, u.username, u.display_name, u.avatar_media_id FROM projects p
            JOIN users u ON u.id = p.user_id WHERE {where} ORDER BY p.id DESC LIMIT ?""",
        [*params, limit],
    ).fetchall()


def _project_out(rows, viewer) -> list:
    if not rows:
        return []
    d = db()
    ids = [r["id"] for r in rows]
    ph = ph_of(ids)
    counts = {r["project_id"]: r["c"] for r in d.execute(
        f"SELECT project_id, COUNT(*) AS c FROM project_likes WHERE project_id IN ({ph}) GROUP BY project_id",
        ids).fetchall()}
    liked = set()
    if viewer:
        liked = {r["project_id"] for r in d.execute(
            f"SELECT project_id FROM project_likes WHERE user_id = ? AND project_id IN ({ph})",
            [viewer, *ids]).fetchall()}
    return [{
        "id": r["id"],
        "title": r["title"],
        "description": r["description"],
        "repo_url": r["repo_url"],
        "live_url": r["live_url"],
        "status": r["status"],
        "tags": _split_tags(r["tags"]),
        "screenshot_url": media_url(r["screenshot_media_id"]),
        "author": user_lite(r),
        "like_count": counts.get(r["id"], 0),
        "liked": r["id"] in liked,
        "mine": viewer == r["user_id"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    } for r in rows]


def _fetch_project(pid: int):
    rows = db().execute(
        """SELECT p.*, u.username, u.display_name, u.avatar_media_id FROM projects p
           JOIN users u ON u.id = p.user_id WHERE p.id = ?""", (pid,)).fetchall()
    if not rows:
        raise ApiError("That project doesn't exist.", 404)
    return rows[0]


# --------------------------------------------------------------------------- #
# Projects & portfolios
# --------------------------------------------------------------------------- #
@app.get("/api/projects")
def list_projects():
    viewer = viewer_id()
    where, params = ["p.id < ?"], [id_before()]
    tag = request.args.get("tag", "").strip().lower()
    if tag:
        where.append("(',' || p.tags || ',') LIKE ? ESCAPE '!'")
        params.append(f"%,{like_escape(tag)},%")
    status = request.args.get("status", "").strip().lower()
    if status in PROJECT_STATUSES:
        where.append("p.status = ?")
        params.append(status)
    q = request.args.get("q", "").strip()[:100].lower()
    if q:
        pat = f"%{like_escape(q)}%"
        where.append("(LOWER(p.title) LIKE ? ESCAPE '!' OR LOWER(p.description) LIKE ? ESCAPE '!')")
        params += [pat, pat]
    rows = _project_rows(" AND ".join(where), params, PAGE + 1)
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]
    return jsonify(items=_project_out(rows, viewer), next=str(rows[-1]["id"]) if has_more and rows else None)


@app.post("/api/projects")
def create_project():
    u = need_user()
    if rate_limited(f"project:{u['id']}", limit=30, window=600):
        raise ApiError("You're creating projects too fast. Try again in a few minutes.", 429)
    data = request.get_json(silent=True) or {}
    f = _project_fields(data, u["id"])
    if "status" not in data:
        f["status"] = "idea"
    ts = now_iso()
    d = db()
    pid = d.execute(
        """INSERT INTO projects (user_id, title, description, repo_url, live_url, status, tags,
           screenshot_media_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (u["id"], f["title"], f.get("description", ""), f.get("repo_url", ""), f.get("live_url", ""),
         f["status"], f.get("tags", ""), f.get("screenshot_media_id"), ts, ts),
    ).lastrowid
    d.commit()
    return jsonify(project=_project_out([_fetch_project(pid)], u["id"])[0]), 201


@app.get("/api/projects/<int:pid>")
def get_project(pid):
    viewer = viewer_id()
    return jsonify(project=_project_out([_fetch_project(pid)], viewer)[0])


@app.patch("/api/projects/<int:pid>")
def edit_project(pid):
    u = need_user()
    row = _fetch_project(pid)
    if row["user_id"] != u["id"]:
        raise ApiError("You can only edit your own projects.", 403)
    fields = _project_fields(request.get_json(silent=True) or {}, u["id"], partial=True)
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        d = db()
        d.execute(f"UPDATE projects SET {sets}, updated_at = ? WHERE id = ?",
                  [*fields.values(), now_iso(), pid])
        d.commit()
    return jsonify(project=_project_out([_fetch_project(pid)], u["id"])[0])


@app.delete("/api/projects/<int:pid>")
def delete_project(pid):
    u = need_user()
    row = _fetch_project(pid)
    if row["user_id"] != u["id"]:
        raise ApiError("You can only delete your own projects.", 403)
    d = db()
    d.execute("DELETE FROM projects WHERE id = ?", (pid,))
    d.commit()
    return jsonify(ok=True)


@app.post("/api/projects/<int:pid>/like")
def like_project(pid):
    u = need_user()
    row = _fetch_project(pid)
    d = db()
    if not d.execute("SELECT id FROM project_likes WHERE user_id = ? AND project_id = ?", (u["id"], pid)).fetchone():
        d.execute("INSERT INTO project_likes (user_id, project_id, created_at) VALUES (?, ?, ?)",
                  (u["id"], pid, now_iso()))
        notify(row["user_id"], u["id"], "project_like", None, link=f"/projects/{pid}")
        d.commit()
    return jsonify(ok=True)


@app.delete("/api/projects/<int:pid>/like")
def unlike_project(pid):
    u = need_user()
    _fetch_project(pid)
    d = db()
    d.execute("DELETE FROM project_likes WHERE user_id = ? AND project_id = ?", (u["id"], pid))
    d.commit()
    return jsonify(ok=True)


@app.get("/api/projects/<int:pid>/collaborators")
def project_collaborators(pid):
    """Developers with other projects that share at least one tag with this one."""
    row = _fetch_project(pid)
    tags = _split_tags(row["tags"])
    if not tags:
        return jsonify(items=[])
    cond = " OR ".join(["(',' || p.tags || ',') LIKE ? ESCAPE '!'"] * len(tags))
    rows = db().execute(
        f"""SELECT p.id, p.title, p.tags, p.user_id, u.username, u.display_name, u.avatar_media_id
            FROM projects p JOIN users u ON u.id = p.user_id
            WHERE p.user_id <> ? AND p.id <> ? AND ({cond}) ORDER BY p.id DESC LIMIT 200""",
        [row["user_id"], pid, *[f"%,{like_escape(t)},%" for t in tags]],
    ).fetchall()
    people = {}
    for r in rows:
        shared = sorted(set(_split_tags(r["tags"])) & set(tags))
        entry = people.setdefault(r["user_id"], {"user": user_lite(r), "shared_tags": set(), "projects": []})
        entry["shared_tags"].update(shared)
        if len(entry["projects"]) < 3:
            entry["projects"].append({"id": r["id"], "title": r["title"]})
    items = sorted(people.values(), key=lambda e: -len(e["shared_tags"]))[:10]
    return jsonify(items=[{"user": e["user"], "shared_tags": sorted(e["shared_tags"]), "projects": e["projects"]}
                          for e in items])


@app.get("/api/users/<username>/projects")
def user_projects(username):
    viewer = viewer_id()
    owner = find_user(username)
    rows = _project_rows("p.user_id = ?", [owner["id"]], 50)
    return jsonify(items=_project_out(rows, viewer))


# --------------------------------------------------------------------------- #
# Collaboration requests
# --------------------------------------------------------------------------- #
def _collab_rows(where: str, params: list, limit: int):
    return db().execute(
        f"""SELECT c.*, u.username, u.display_name, u.avatar_media_id, pr.title AS project_title
            FROM collab_requests c JOIN users u ON u.id = c.user_id
            LEFT JOIN projects pr ON pr.id = c.project_id
            WHERE {where} ORDER BY c.id DESC LIMIT ?""",
        [*params, limit],
    ).fetchall()


def _collab_out(rows, viewer) -> list:
    if not rows:
        return []
    d = db()
    ids = [r["id"] for r in rows]
    ph = ph_of(ids)
    counts = {r["request_id"]: r["c"] for r in d.execute(
        f"SELECT request_id, COUNT(*) AS c FROM collab_interests WHERE request_id IN ({ph}) GROUP BY request_id",
        ids).fetchall()}
    mine = {}
    if viewer:
        mine = {r["request_id"]: r["status"] for r in d.execute(
            f"SELECT request_id, status FROM collab_interests WHERE user_id = ? AND request_id IN ({ph})",
            [viewer, *ids]).fetchall()}
    return [{
        "id": r["id"],
        "title": r["title"],
        "description": r["description"],
        "goals": r["goals"],
        "skills": _split_tags(r["skills"]),
        "status": r["status"],
        "project": {"id": r["project_id"], "title": r["project_title"]} if r["project_id"] else None,
        "author": user_lite(r),
        "interest_count": counts.get(r["id"], 0),
        "my_interest": mine.get(r["id"]),
        "mine": viewer == r["user_id"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    } for r in rows]


def _fetch_collab(cid: int):
    rows = db().execute(
        """SELECT c.*, u.username, u.display_name, u.avatar_media_id, pr.title AS project_title
           FROM collab_requests c JOIN users u ON u.id = c.user_id
           LEFT JOIN projects pr ON pr.id = c.project_id WHERE c.id = ?""", (cid,)).fetchall()
    if not rows:
        raise ApiError("That collaboration request doesn't exist.", 404)
    return rows[0]


def _collab_fields(data: dict, uid: int, partial: bool = False) -> dict:
    out = {}

    def has(key):
        return (key in data) if partial else True

    if has("title"):
        t = str(data.get("title") or "").strip()
        if not 1 <= len(t) <= 100:
            raise ApiError("Titles are 1–100 characters.")
        out["title"] = t
    if has("description"):
        t = str(data.get("description") or "").strip()
        if len(t) > 2000:
            raise ApiError("Descriptions are limited to 2000 characters.")
        out["description"] = t
    if has("goals"):
        t = str(data.get("goals") or "").strip()
        if len(t) > 500:
            raise ApiError("Goals are limited to 500 characters.")
        out["goals"] = t
    if has("skills"):
        out["skills"] = normalize_tags(data.get("skills") or "", limit=10)
    if "status" in data:
        s = str(data.get("status") or "").strip().lower()
        if s not in COLLAB_STATUSES:
            raise ApiError("Status must be open or closed.")
        out["status"] = s
    if has("project_id"):
        pid = data.get("project_id")
        if pid in (None, ""):
            out["project_id"] = None
        else:
            pid = to_int(pid, "project")
            row = db().execute("SELECT user_id FROM projects WHERE id = ?", (pid,)).fetchone()
            if not row or row["user_id"] != uid:
                raise ApiError("Link only one of your own projects.", 400)
            out["project_id"] = pid
    return out


@app.get("/api/collab")
def list_collab():
    viewer = viewer_id()
    where, params = ["c.id < ?"], [id_before()]
    status = request.args.get("status", "open").strip().lower()
    if status in COLLAB_STATUSES:
        where.append("c.status = ?")
        params.append(status)
    skill = request.args.get("skill", "").strip().lower()
    if skill:
        where.append("(',' || c.skills || ',') LIKE ? ESCAPE '!'")
        params.append(f"%,{like_escape(skill)},%")
    q = request.args.get("q", "").strip()[:100].lower()
    if q:
        pat = f"%{like_escape(q)}%"
        where.append("(LOWER(c.title) LIKE ? ESCAPE '!' OR LOWER(c.description) LIKE ? ESCAPE '!')")
        params += [pat, pat]
    rows = _collab_rows(" AND ".join(where), params, PAGE + 1)
    has_more = len(rows) > PAGE
    rows = rows[:PAGE]
    return jsonify(items=_collab_out(rows, viewer), next=str(rows[-1]["id"]) if has_more and rows else None)


@app.post("/api/collab")
def create_collab():
    u = need_user()
    if rate_limited(f"collab:{u['id']}", limit=20, window=600):
        raise ApiError("You're posting requests too fast. Try again in a few minutes.", 429)
    f = _collab_fields(request.get_json(silent=True) or {}, u["id"])
    if not f.get("title"):
        raise ApiError("Give the request a title.")
    ts = now_iso()
    d = db()
    cid = d.execute(
        """INSERT INTO collab_requests (user_id, project_id, title, description, goals, skills, status,
           created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
        (u["id"], f.get("project_id"), f["title"], f.get("description", ""), f.get("goals", ""),
         f.get("skills", ""), ts, ts),
    ).lastrowid
    d.commit()
    return jsonify(request=_collab_out([_fetch_collab(cid)], u["id"])[0]), 201


@app.get("/api/collab/<int:cid>")
def get_collab(cid):
    viewer = viewer_id()
    row = _fetch_collab(cid)
    out = _collab_out([row], viewer)[0]
    if viewer == row["user_id"]:
        out["interests"] = [{
            "id": r["id"],
            "message": r["message"],
            "status": r["status"],
            "created_at": r["created_at"],
            "applicant": user_lite(r),
        } for r in db().execute(
            """SELECT ci.*, u.username, u.display_name, u.avatar_media_id FROM collab_interests ci
               JOIN users u ON u.id = ci.user_id WHERE ci.request_id = ? ORDER BY ci.id ASC""", (cid,)).fetchall()]
    return jsonify(request=out)


@app.patch("/api/collab/<int:cid>")
def edit_collab(cid):
    u = need_user()
    row = _fetch_collab(cid)
    if row["user_id"] != u["id"]:
        raise ApiError("You can only edit your own requests.", 403)
    fields = _collab_fields(request.get_json(silent=True) or {}, u["id"], partial=True)
    if "title" in fields and not fields["title"]:
        raise ApiError("Give the request a title.")
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        d = db()
        d.execute(f"UPDATE collab_requests SET {sets}, updated_at = ? WHERE id = ?",
                  [*fields.values(), now_iso(), cid])
        d.commit()
    return jsonify(request=_collab_out([_fetch_collab(cid)], u["id"])[0])


@app.delete("/api/collab/<int:cid>")
def delete_collab(cid):
    u = need_user()
    row = _fetch_collab(cid)
    if row["user_id"] != u["id"]:
        raise ApiError("You can only delete your own requests.", 403)
    d = db()
    d.execute("DELETE FROM collab_requests WHERE id = ?", (cid,))
    d.commit()
    return jsonify(ok=True)


@app.post("/api/collab/<int:cid>/interest")
def express_interest(cid):
    u = need_user()
    if rate_limited(f"interest:{u['id']}", limit=30, window=600):
        raise ApiError("Too many requests. Try again in a few minutes.", 429)
    row = _fetch_collab(cid)
    if row["user_id"] == u["id"]:
        raise ApiError("That's your own request.", 400)
    if row["status"] != "open":
        raise ApiError("This request is closed.", 400)
    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    if len(message) > 500:
        raise ApiError("Messages are limited to 500 characters.")
    d = db()
    if d.execute("SELECT id FROM collab_interests WHERE request_id = ? AND user_id = ?", (cid, u["id"])).fetchone():
        raise ApiError("You've already expressed interest in this request.", 409)
    d.execute(
        "INSERT INTO collab_interests (request_id, user_id, message, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (cid, u["id"], message, now_iso()),
    )
    notify(row["user_id"], u["id"], "collab_interest", None, link=f"/collab/{cid}")
    d.commit()
    return jsonify(ok=True, status="pending"), 201


@app.delete("/api/collab/<int:cid>/interest")
def withdraw_interest(cid):
    u = need_user()
    _fetch_collab(cid)
    d = db()
    d.execute("DELETE FROM collab_interests WHERE request_id = ? AND user_id = ?", (cid, u["id"]))
    d.commit()
    return jsonify(ok=True)


@app.patch("/api/collab/<int:cid>/interests/<int:iid>")
def respond_interest(cid, iid):
    u = need_user()
    row = _fetch_collab(cid)
    if row["user_id"] != u["id"]:
        raise ApiError("Only the request owner can respond to interest.", 403)
    data = request.get_json(silent=True) or {}
    status = str(data.get("status") or "").strip().lower()
    if status not in ("accepted", "declined", "pending"):
        raise ApiError("Status must be accepted, declined or pending.")
    d = db()
    ci = d.execute("SELECT * FROM collab_interests WHERE id = ? AND request_id = ?", (iid, cid)).fetchone()
    if not ci:
        raise ApiError("That interest doesn't exist.", 404)
    d.execute("UPDATE collab_interests SET status = ? WHERE id = ?", (status, iid))
    if status != "pending":
        notify(ci["user_id"], u["id"], "collab_status", None, link=f"/collab/{cid}")
    d.commit()
    return jsonify(ok=True, status=status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
