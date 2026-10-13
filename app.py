"""DevHub — a project hub for developers.

Full-stack app: Flask + SQLite backend, vanilla HTML/CSS/JS frontend.

Highlights
----------
- Accounts: signup / login / logout, change password, delete account, export data
- Projects: full CRUD, covers, progress, pinning, views, likes, comments
- Social: profiles, follows, leaderboard, activity feed
- Extras: search, filters, sorting, pagination, RSS, docs, themes, shortcuts

Run it:
    pip install -r requirements.txt
    python app.py            # -> http://localhost:5000
    python seed.py           # optional: load fun demo data
"""

import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from flask import Flask, Response, g, jsonify, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import db as dbm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = dbm.SQLITE_PATH  # kept for seed.py compatibility
SECRET_PATH = os.path.join(BASE_DIR, ".secret_key")

STATUSES = ("idea", "in_progress", "shipped")
AVATARS = ("🧑‍💻", "👩‍💻", "👨‍💻", "🦄", "🐙", "🦊", "🐸", "🐼",
           "🦉", "🚀", "🤖", "👾", "🐍", "☕", "⚡", "🌟")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
URL_RE = re.compile(r"^https?://\S+$")

PAGE_SIZE = 12
ACTIVITY_TYPES = ("user_joined", "project_added", "project_shipped", "comment_added")


def _load_or_create_secret_key() -> str:
    """SECRET_KEY env var wins (set it in production); else a persisted file."""
    env = os.environ.get("SECRET_KEY", "").strip()
    if env:
        return env
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
    except OSError:  # read-only filesystem: sessions reset on restart
        return secrets.token_hex(32)


IS_PROD = bool(os.environ.get("RENDER") or os.environ.get("PRODUCTION"))

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(
    SECRET_KEY=_load_or_create_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PROD,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
    MAX_CONTENT_LENGTH=256 * 1024,
    JSON_SORT_KEYS=False,
)


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL DEFAULT '',
    bio           TEXT NOT NULL DEFAULT '',
    avatar        TEXT NOT NULL DEFAULT '🧑‍💻',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tech        TEXT NOT NULL DEFAULT '',
    repo_url    TEXT NOT NULL DEFAULT '',
    live_url    TEXT NOT NULL DEFAULT '',
    cover_url   TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'in_progress',
    progress    INTEGER NOT NULL DEFAULT 0,
    pinned      INTEGER NOT NULL DEFAULT 0,
    views       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);

CREATE TABLE IF NOT EXISTS likes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_likes_project ON likes(project_id);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_project ON comments(project_id);

CREATE TABLE IF NOT EXISTS follows (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    UNIQUE(follower_id, followee_id)
);

CREATE TABLE IF NOT EXISTS activities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_recent ON activities(id DESC);

CREATE TABLE IF NOT EXISTS bookmarks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, project_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    actor_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, id DESC);
"""

MIGRATIONS = (
    ("users", "avatar", "TEXT NOT NULL DEFAULT '🧑‍💻'"),
    ("projects", "cover_url", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "progress", "INTEGER NOT NULL DEFAULT 0"),
    ("projects", "pinned", "INTEGER NOT NULL DEFAULT 0"),
    ("projects", "views", "INTEGER NOT NULL DEFAULT 0"),
)


def init_db() -> None:
    """Create the schema and migrate older databases in place."""
    dbm.init_schema(SCHEMA, MIGRATIONS)


def get_db():
    if "db" not in g:
        g.db = dbm.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def public_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or row["username"],
        "bio": row["bio"],
        "avatar": row["avatar"] or "🧑‍💻",
        "created_at": row["created_at"],
    }


def project_dict(row, liked_by_me=None, bookmarked_by_me=None) -> dict:
    data = {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "description": row["description"],
        "tech": row["tech"],
        "repo_url": row["repo_url"],
        "live_url": row["live_url"],
        "cover_url": row["cover_url"],
        "status": row["status"],
        "progress": row["progress"],
        "pinned": bool(row["pinned"]),
        "views": row["views"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "likes": row["likes"] if "likes" in row.keys() else 0,
        "comments_count": row["comments_count"] if "comments_count" in row.keys() else 0,
    }
    if liked_by_me is not None:
        data["liked_by_me"] = liked_by_me
    if bookmarked_by_me is not None:
        data["bookmarked_by_me"] = bookmarked_by_me
    if "author_username" in row.keys():
        data["author"] = {
            "username": row["author_username"],
            "display_name": row["author_display"],
            "avatar": row["author_avatar"] or "🧑‍💻",
        }
    return data


PROJECT_COUNTS_SQL = """
(SELECT COUNT(*) FROM likes l WHERE l.project_id = p.id) AS likes,
(SELECT COUNT(*) FROM comments c WHERE c.project_id = p.id) AS comments_count
"""

SHOWCASE_SQL = f"""
SELECT p.*, u.username AS author_username,
       COALESCE(NULLIF(u.display_name, ''), u.username) AS author_display,
       u.avatar AS author_avatar,
       {PROJECT_COUNTS_SQL}
FROM projects p
JOIN users u ON u.id = p.user_id
ORDER BY p.created_at DESC, p.id DESC
"""

MY_PROJECTS_SQL = f"""
SELECT p.*, u.username AS author_username,
       COALESCE(NULLIF(u.display_name, ''), u.username) AS author_display,
       u.avatar AS author_avatar,
       {PROJECT_COUNTS_SQL}
FROM projects p
JOIN users u ON u.id = p.user_id
WHERE p.user_id = ?
ORDER BY p.pinned DESC, p.created_at DESC, p.id DESC
"""


def attach_liked(db, rows, viewer):
    """Add liked_by_me to a list of project dicts for the viewer."""
    liked, saved = set(), set()
    if viewer is not None:
        liked = {r["project_id"] for r in db.execute(
            "SELECT project_id FROM likes WHERE user_id = ?", (viewer["id"],))}
        saved = {r["project_id"] for r in db.execute(
            "SELECT project_id FROM bookmarks WHERE user_id = ?", (viewer["id"],))}
    return [project_dict(r, liked_by_me=r["id"] in liked, bookmarked_by_me=r["id"] in saved)
            for r in rows]


def log_activity(db, user_id, act_type, project_id=None):
    if act_type not in ACTIVITY_TYPES:
        return
    db.execute(
        "INSERT INTO activities (user_id, type, project_id, created_at) VALUES (?, ?, ?, ?)",
        (user_id, act_type, project_id, now_iso()),
    )


NOTIFY_TYPES = ("like", "comment", "follow")


def notify(db, recipient_id, actor_id, ntype, project_id=None):
    """Tell recipient something happened (never notify yourself)."""
    if recipient_id == actor_id or ntype not in NOTIFY_TYPES:
        return
    db.execute(
        "INSERT INTO notifications (user_id, actor_id, type, project_id, is_read, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (recipient_id, actor_id, ntype, project_id, now_iso()),
    )


def validate_project(payload):
    """Return (data, error_message)."""
    name = (payload.get("name") or "").strip()
    if not 1 <= len(name) <= 100:
        return None, "Project name is required (max 100 characters)."

    description = (payload.get("description") or "").strip()
    if len(description) > 2000:
        return None, "Description is too long (max 2000 characters)."

    tech = (payload.get("tech") or "").strip()
    if len(tech) > 200:
        return None, "Tech stack is too long (max 200 characters)."

    repo_url = (payload.get("repo_url") or "").strip()
    live_url = (payload.get("live_url") or "").strip()
    cover_url = (payload.get("cover_url") or "").strip()
    for url, label in ((repo_url, "Repository URL"), (live_url, "Live URL")):
        if url and not URL_RE.match(url):
            return None, f"{label} must start with http:// or https://"
    if cover_url and not (cover_url.startswith("data:image/") or URL_RE.match(cover_url)):
        return None, "Cover image URL must start with http:// or https:// (or be a data: image URI)."
    if cover_url.startswith("data:image/") and len(cover_url) > 100_000:
        return None, "Cover image is too large."

    status = payload.get("status") or "in_progress"
    if status not in STATUSES:
        return None, f"Status must be one of: {', '.join(STATUSES)}."

    try:
        progress = int(payload.get("progress", 0))
    except (TypeError, ValueError):
        return None, "Progress must be a number between 0 and 100."
    progress = max(0, min(100, progress))

    data = {
        "name": name,
        "description": description,
        "tech": tech,
        "repo_url": repo_url,
        "live_url": live_url,
        "cover_url": cover_url,
        "status": status,
        "progress": progress,
    }
    return data, ""


def json_error(message: str, code: int):
    return jsonify(error=message), code


# --------------------------------------------------------------------------- #
# Rate limiting (simple in-memory, for auth endpoints)
# --------------------------------------------------------------------------- #
AUTH_ATTEMPTS: dict[str, list[float]] = {}


def rate_limited(ip: str, limit: int = 10, window: int = 300) -> bool:
    now = time.time()
    recent = [t for t in AUTH_ATTEMPTS.get(ip, []) if now - t < window]
    limited = len(recent) >= limit
    recent.append(now)
    AUTH_ATTEMPTS[ip] = recent
    return limited


# --------------------------------------------------------------------------- #
# Security headers
# --------------------------------------------------------------------------- #
@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if IS_PROD:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith("/static/"):
        resp.headers.setdefault("Cache-Control", "public, max-age=3600")
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src * data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return resp


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.get("/u/<username>")
def profile_page(username):
    return render_template("profile.html", username=username)


@app.get("/leaderboard")
def leaderboard_page():
    return render_template("leaderboard.html")


@app.get("/activity")
def activity_page():
    return render_template("activity.html")


@app.get("/docs")
def docs_page():
    return render_template("docs.html")


@app.get("/trending")
def trending_page():
    return render_template("trending.html")


@app.get("/saved")
def saved_page():
    return render_template("saved.html")


@app.get("/notifications")
def notifications_page():
    return render_template("notifications.html")


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return json_error("Not found.", 404)
    return render_template("404.html"), 404


@app.errorhandler(405)
def bad_method(_e):
    return json_error("Method not allowed.", 405)


@app.errorhandler(413)
def too_large(_e):
    return json_error("Request is too large.", 413)


@app.errorhandler(500)
def server_error(_e):
    if request.path.startswith("/api/"):
        return json_error("Something went wrong on our side. Please retry.", 500)
    return "Something went wrong. Please retry.", 500


# --------------------------------------------------------------------------- #
# Auth API
# --------------------------------------------------------------------------- #
@app.post("/api/signup")
def signup():
    if rate_limited(request.remote_addr or "?"):
        return json_error("Too many attempts — take a short break and try again.", 429)

    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not USERNAME_RE.match(username):
        return json_error("Username must be 3-30 characters: letters, numbers, underscores.", 400)
    if len(password) < 6:
        return json_error("Password must be at least 6 characters.", 400)

    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)).fetchone():
        return json_error("That username is already taken.", 409)

    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, display_name, bio, avatar, created_at) "
            "VALUES (?, ?, ?, '', ?, ?)",
            (username, generate_password_hash(password), username, AVATARS[0], now_iso()),
        )
    except dbm.IntegrityError:
        return json_error("That username is already taken.", 409)
    db.commit()
    log_activity(db, cur.lastrowid, "user_joined")
    db.commit()
    session.permanent = True
    session["user_id"] = cur.lastrowid
    row = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(user=public_user(row)), 201


@app.post("/api/login")
def login():
    if rate_limited(request.remote_addr or "?"):
        return json_error("Too many attempts — take a short break and try again.", 429)

    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    row = get_db().execute("SELECT * FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return json_error("Wrong username or password.", 401)

    session.permanent = True
    session["user_id"] = row["id"]
    return jsonify(user=public_user(row))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
def me():
    row = current_user()
    unread = 0
    if row is not None:
        unread = get_db().execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
            (row["id"],)).fetchone()["n"]
    return jsonify(authenticated=row is not None, user=public_user(row) if row else None,
                   unread=unread)


@app.put("/api/me")
def update_me():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    payload = request.get_json(silent=True) or {}
    display_name = (payload.get("display_name") or "").strip()
    bio = (payload.get("bio") or "").strip()
    avatar = payload.get("avatar", row["avatar"]) or row["avatar"]

    if len(display_name) > 60:
        return json_error("Display name is too long (max 60 characters).", 400)
    if len(bio) > 500:
        return json_error("Bio is too long (max 500 characters).", 400)
    if avatar not in AVATARS:
        return json_error("Pick an avatar from the provided options.", 400)

    db = get_db()
    db.execute(
        "UPDATE users SET display_name = ?, bio = ?, avatar = ? WHERE id = ?",
        (display_name or row["username"], bio, avatar, row["id"]),
    )
    db.commit()
    updated = db.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    return jsonify(user=public_user(updated))


@app.put("/api/me/password")
def change_password():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    payload = request.get_json(silent=True) or {}
    current = payload.get("current_password") or ""
    new = payload.get("new_password") or ""
    if not check_password_hash(row["password_hash"], current):
        return json_error("Your current password is incorrect.", 401)
    if len(new) < 6:
        return json_error("New password must be at least 6 characters.", 400)

    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash(new), row["id"]))
    db.commit()
    return jsonify(ok=True)


@app.delete("/api/me")
def delete_account():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    payload = request.get_json(silent=True) or {}
    password = payload.get("password") or ""
    if not check_password_hash(row["password_hash"], password):
        return json_error("Password confirmation failed — account not deleted.", 401)

    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (row["id"],))
    db.commit()
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me/export")
def export_data():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    db = get_db()
    projects = db.execute(
        "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC", (row["id"],)
    ).fetchall()
    comments = db.execute(
        "SELECT c.body, c.created_at, p.name AS project_name FROM comments c "
        "JOIN projects p ON p.id = c.project_id WHERE c.user_id = ? ORDER BY c.id DESC",
        (row["id"],),
    ).fetchall()
    likes = db.execute(
        "SELECT l.created_at, p.id AS project_id, p.name AS project_name FROM likes l "
        "JOIN projects p ON p.id = l.project_id WHERE l.user_id = ? ORDER BY l.id DESC",
        (row["id"],),
    ).fetchall()

    data = {
        "exported_at": now_iso(),
        "user": public_user(row),
        "projects": [project_dict(p) for p in projects],
        "comments": [dict(c) for c in comments],
        "likes": [dict(l) for l in likes],
    }
    return Response(
        json.dumps(data, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=devhub-export.json"},
    )


@app.get("/api/me/following")
def my_following():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)
    rows = get_db().execute(
        "SELECT u.id, u.username, u.avatar, COALESCE(NULLIF(u.display_name,''), u.username) AS display_name "
        "FROM follows f JOIN users u ON u.id = f.followee_id WHERE f.follower_id = ? "
        "ORDER BY f.created_at DESC",
        (row["id"],),
    ).fetchall()
    return jsonify(following=[dict(r) for r in rows])


# --------------------------------------------------------------------------- #
# Projects API
# --------------------------------------------------------------------------- #
@app.get("/api/projects")
def list_projects():
    viewer = current_user()
    rows = get_db().execute(SHOWCASE_SQL).fetchall()
    return jsonify(projects=attach_liked(get_db(), rows, viewer))


@app.get("/api/my/projects")
def my_projects():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)
    rows = get_db().execute(MY_PROJECTS_SQL, (row["id"],)).fetchall()
    return jsonify(projects=attach_liked(get_db(), rows, row))


@app.post("/api/projects")
def create_project():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    data, err = validate_project(request.get_json(silent=True) or {})
    if err:
        return json_error(err, 400)

    db = get_db()
    cur = db.execute(
        "INSERT INTO projects (user_id, name, description, tech, repo_url, live_url, cover_url, "
        "status, progress, pinned, views, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
        (row["id"], data["name"], data["description"], data["tech"], data["repo_url"],
         data["live_url"], data["cover_url"], data["status"], data["progress"],
         now_iso(), now_iso()),
    )
    db.commit()
    log_activity(db, row["id"], "project_added", cur.lastrowid)
    db.commit()
    created = db.execute(
        "SELECT p.*, u.username AS author_username, "
        "COALESCE(NULLIF(u.display_name,''), u.username) AS author_display, u.avatar AS author_avatar, "
        f"{PROJECT_COUNTS_SQL} FROM projects p JOIN users u ON u.id = p.user_id WHERE p.id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return jsonify(project=project_dict(created, liked_by_me=False)), 201


def _owned_project_or_error(user, project_id):
    """Return (row, error_response)."""
    db = get_db()
    prow = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if prow is None:
        return None, json_error("Project not found.", 404)
    if prow["user_id"] != user["id"]:
        return None, json_error("You can only modify your own projects.", 403)
    return prow, None


@app.get("/api/projects/<int:project_id>")
def project_detail(project_id):
    db = get_db()
    prow = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if prow is None:
        return json_error("Project not found.", 404)

    db.execute("UPDATE projects SET views = views + 1 WHERE id = ?", (project_id,))
    db.commit()

    row = db.execute(
        "SELECT p.*, u.username AS author_username, "
        "COALESCE(NULLIF(u.display_name,''), u.username) AS author_display, u.avatar AS author_avatar, "
        f"{PROJECT_COUNTS_SQL} FROM projects p JOIN users u ON u.id = p.user_id WHERE p.id = ?",
        (project_id,),
    ).fetchone()
    viewer = current_user()
    liked = False
    if viewer is not None:
        liked = bool(db.execute("SELECT 1 FROM likes WHERE user_id = ? AND project_id = ?",
                                (viewer["id"], project_id)).fetchone())
    return jsonify(project=project_dict(row, liked_by_me=liked))


@app.put("/api/projects/<int:project_id>")
def update_project(project_id):
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    prow, err = _owned_project_or_error(row, project_id)
    if err:
        return err

    data, verr = validate_project(request.get_json(silent=True) or {})
    if verr:
        return json_error(verr, 400)

    db = get_db()
    db.execute(
        "UPDATE projects SET name = ?, description = ?, tech = ?, repo_url = ?, live_url = ?, "
        "cover_url = ?, status = ?, progress = ?, updated_at = ? WHERE id = ?",
        (data["name"], data["description"], data["tech"], data["repo_url"], data["live_url"],
         data["cover_url"], data["status"], data["progress"], now_iso(), project_id),
    )
    if prow["status"] != "shipped" and data["status"] == "shipped":
        log_activity(db, row["id"], "project_shipped", project_id)
    db.commit()
    updated = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return jsonify(project=project_dict(updated))


@app.delete("/api/projects/<int:project_id>")
def delete_project(project_id):
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    prow, err = _owned_project_or_error(row, project_id)
    if err:
        return err

    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()
    return jsonify(ok=True)


@app.post("/api/projects/<int:project_id>/pin")
def toggle_pin(project_id):
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    prow, err = _owned_project_or_error(row, project_id)
    if err:
        return err

    db = get_db()
    new_val = 0 if prow["pinned"] else 1
    db.execute("UPDATE projects SET pinned = ? WHERE id = ?", (new_val, project_id))
    db.commit()
    return jsonify(pinned=bool(new_val))


@app.post("/api/projects/<int:project_id>/like")
def toggle_like(project_id):
    row = current_user()
    if row is None:
        return json_error("You must be logged in to like projects.", 401)

    db = get_db()
    prow = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if prow is None:
        return json_error("Project not found.", 404)

    existing = db.execute("SELECT id FROM likes WHERE user_id = ? AND project_id = ?",
                          (row["id"], project_id)).fetchone()
    if existing:
        db.execute("DELETE FROM likes WHERE id = ?", (existing["id"],))
        liked = False
    else:
        db.execute("INSERT INTO likes (user_id, project_id, created_at) VALUES (?, ?, ?)",
                   (row["id"], project_id, now_iso()))
        owner = db.execute("SELECT user_id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if owner:
            notify(db, owner["user_id"], row["id"], "like", project_id)
        liked = True
    db.commit()
    count = db.execute("SELECT COUNT(*) AS n FROM likes WHERE project_id = ?",
                       (project_id,)).fetchone()["n"]
    return jsonify(liked=liked, likes=count)


# --------------------------------------------------------------------------- #
# Comments API
# --------------------------------------------------------------------------- #
@app.get("/api/projects/<int:project_id>/comments")
def list_comments(project_id):
    rows = get_db().execute(
        "SELECT c.id, c.body, c.created_at, c.user_id, u.username AS author_username, "
        "COALESCE(NULLIF(u.display_name,''), u.username) AS author_display, u.avatar AS author_avatar "
        "FROM comments c JOIN users u ON u.id = c.user_id "
        "WHERE c.project_id = ? ORDER BY c.id ASC",
        (project_id,),
    ).fetchall()
    viewer = current_user()
    return jsonify(comments=[
        {
            "id": r["id"],
            "body": r["body"],
            "created_at": r["created_at"],
            "mine": viewer is not None and r["user_id"] == viewer["id"],
            "author": {
                "username": r["author_username"],
                "display_name": r["author_display"],
                "avatar": r["author_avatar"] or "🧑‍💻",
            },
        }
        for r in rows
    ])


@app.post("/api/projects/<int:project_id>/comments")
def create_comment(project_id):
    row = current_user()
    if row is None:
        return json_error("You must be logged in to comment.", 401)

    payload = request.get_json(silent=True) or {}
    body = (payload.get("body") or "").strip()
    if not 1 <= len(body) <= 500:
        return json_error("Comment must be 1-500 characters.", 400)

    db = get_db()
    prow = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if prow is None:
        return json_error("Project not found.", 404)

    cur = db.execute(
        "INSERT INTO comments (user_id, project_id, body, created_at) VALUES (?, ?, ?, ?)",
        (row["id"], project_id, body, now_iso()),
    )
    log_activity(db, row["id"], "comment_added", project_id)
    owner = db.execute("SELECT user_id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if owner:
        notify(db, owner["user_id"], row["id"], "comment", project_id)
    db.commit()
    return jsonify(comment={
        "id": cur.lastrowid,
        "body": body,
        "created_at": now_iso(),
        "mine": True,
        "author": {
            "username": row["username"],
            "display_name": row["display_name"] or row["username"],
            "avatar": row["avatar"] or "🧑‍💻",
        },
    }), 201


@app.delete("/api/comments/<int:comment_id>")
def delete_comment(comment_id):
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)

    db = get_db()
    crow = db.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    if crow is None:
        return json_error("Comment not found.", 404)
    if crow["user_id"] != row["id"]:
        return json_error("You can only delete your own comments.", 403)

    db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db.commit()
    return jsonify(ok=True)


# --------------------------------------------------------------------------- #
# Users / social API
# --------------------------------------------------------------------------- #
@app.get("/api/users/<username>")
def get_user(username):
    db = get_db()
    urow = db.execute("SELECT * FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()
    if urow is None:
        return json_error("Developer not found.", 404)

    stats = db.execute(
        """
        SELECT
          COUNT(p.id) AS projects,
          CAST(COALESCE(SUM(CASE WHEN p.status = 'shipped' THEN 1 ELSE 0 END), 0) AS INTEGER) AS shipped,
          (SELECT COUNT(*) FROM likes l JOIN projects p2 ON p2.id = l.project_id
            WHERE p2.user_id = :uid) AS likes_received,
          (SELECT COUNT(*) FROM follows WHERE followee_id = :uid) AS followers,
          (SELECT COUNT(*) FROM follows WHERE follower_id = :uid) AS following
        FROM projects p WHERE p.user_id = :uid
        """,
        {"uid": urow["id"]},
    ).fetchone()

    following = False
    viewer = current_user()
    if viewer is not None:
        following = bool(db.execute(
            "SELECT 1 FROM follows WHERE follower_id = ? AND followee_id = ?",
            (viewer["id"], urow["id"])).fetchone())

    rows = db.execute(MY_PROJECTS_SQL, (urow["id"],)).fetchall()
    return jsonify(
        user=public_user(urow),
        stats={k: stats[k] for k in ("projects", "shipped", "likes_received", "followers", "following")},
        following=following,
        projects=attach_liked(db, rows, viewer),
    )


@app.post("/api/users/<username>/follow")
def toggle_follow(username):
    viewer = current_user()
    if viewer is None:
        return json_error("You must be logged in to follow developers.", 401)

    db = get_db()
    urow = db.execute("SELECT * FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()
    if urow is None:
        return json_error("Developer not found.", 404)
    if urow["id"] == viewer["id"]:
        return json_error("You cannot follow yourself. 🪞", 400)

    existing = db.execute("SELECT id FROM follows WHERE follower_id = ? AND followee_id = ?",
                          (viewer["id"], urow["id"])).fetchone()
    if existing:
        db.execute("DELETE FROM follows WHERE id = ?", (existing["id"],))
        following = False
    else:
        db.execute("INSERT INTO follows (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
                   (viewer["id"], urow["id"], now_iso()))
        notify(db, urow["id"], viewer["id"], "follow")
        following = True
    db.commit()
    followers = db.execute("SELECT COUNT(*) AS n FROM follows WHERE followee_id = ?",
                           (urow["id"],)).fetchone()["n"]
    return jsonify(following=following, followers=followers)


@app.get("/api/leaderboard")
def leaderboard():
    rows = get_db().execute(
        """
        SELECT u.username, COALESCE(NULLIF(u.display_name,''), u.username) AS display_name,
               u.avatar,
               COUNT(p.id) AS projects,
               CAST(COALESCE(SUM(CASE WHEN p.status = 'shipped' THEN 1 ELSE 0 END), 0) AS INTEGER) AS shipped,
               (SELECT COUNT(*) FROM likes l JOIN projects p2 ON p2.id = l.project_id
                 WHERE p2.user_id = u.id) AS likes_received
        FROM users u LEFT JOIN projects p ON p.user_id = u.id
        GROUP BY u.id
        ORDER BY likes_received DESC, shipped DESC, projects DESC, u.username ASC
        LIMIT 20
        """
    ).fetchall()
    return jsonify(leaders=[dict(r) for r in rows])


@app.get("/api/activity")
def activity_feed():
    rows = get_db().execute(
        """
        SELECT a.id, a.type, a.created_at, a.project_id,
               u.username AS actor_username,
               COALESCE(NULLIF(u.display_name,''), u.username) AS actor_display,
               u.avatar AS actor_avatar,
               p.name AS project_name
        FROM activities a
        JOIN users u ON u.id = a.user_id
        LEFT JOIN projects p ON p.id = a.project_id
        ORDER BY a.id DESC
        LIMIT 40
        """
    ).fetchall()
    return jsonify(activities=[dict(r) for r in rows])


@app.get("/api/stats")
def global_stats():
    db = get_db()
    def count(sql):
        return db.execute(sql).fetchone()["n"]
    return jsonify(
        developers=count("SELECT COUNT(*) AS n FROM users"),
        projects=count("SELECT COUNT(*) AS n FROM projects"),
        shipped=count("SELECT COUNT(*) AS n FROM projects WHERE status = 'shipped'"),
        likes=count("SELECT COUNT(*) AS n FROM likes"),
        comments=count("SELECT COUNT(*) AS n FROM comments"),
    )


# --------------------------------------------------------------------------- #
# RSS feed
# --------------------------------------------------------------------------- #
@app.get("/feed.xml")
def rss_feed():
    rows = get_db().execute(SHOWCASE_SQL + " LIMIT 20").fetchall()
    items = []
    for r in rows:
        title = xml_escape(f"{r['name']} — {r['author_display']}")
        desc = xml_escape(r["description"] or "No description yet.")
        link = xml_escape(request.url_root.rstrip("/") + f"/?project={r['id']}")
        date = (r["created_at"] or "").replace("T", " ").replace("Z", " GMT")
        items.append(
            f"<item><title>{title}</title>"
            f"<link>{link}</link>"
            f"<description>{desc}</description>"
            f"<pubDate>{xml_escape(date)}</pubDate>"
            f"<guid>{link}</guid></item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        f"<title>DevHub — latest projects</title>"
        f"<link>{xml_escape(request.url_root)}</link>"
        "<description>The newest projects from the DevHub community</description>"
        + "".join(items) +
        "</channel></rss>"
    )
    return Response(xml, mimetype="application/rss+xml")


# --------------------------------------------------------------------------- #
# Bookmarks, notifications, trending, tags
# --------------------------------------------------------------------------- #
def _project_by_id_sql(where: str) -> str:
    return (
        "SELECT p.*, u.username AS author_username, "
        "COALESCE(NULLIF(u.display_name,''), u.username) AS author_display, "
        "u.avatar AS author_avatar, " + PROJECT_COUNTS_SQL +
        " FROM projects p JOIN users u ON u.id = p.user_id " + where
    )


@app.post("/api/projects/<int:project_id>/bookmark")
def toggle_bookmark(project_id):
    row = current_user()
    if row is None:
        return json_error("Log in to save projects.", 401)
    db = get_db()
    if db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        return json_error("Project not found.", 404)
    existing = db.execute("SELECT id FROM bookmarks WHERE user_id = ? AND project_id = ?",
                          (row["id"], project_id)).fetchone()
    if existing:
        db.execute("DELETE FROM bookmarks WHERE id = ?", (existing["id"],))
        saved = False
    else:
        try:
            db.execute("INSERT INTO bookmarks (user_id, project_id, created_at) VALUES (?, ?, ?)",
                       (row["id"], project_id, now_iso()))
        except dbm.IntegrityError:
            pass
        saved = True
    db.commit()
    return jsonify(bookmarked=saved)


@app.get("/api/me/bookmarks")
def my_bookmarks():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)
    db = get_db()
    rows = db.execute(
        _project_by_id_sql("JOIN bookmarks b ON b.project_id = p.id WHERE b.user_id = ? "
                           "ORDER BY b.id DESC"), (row["id"],)).fetchall()
    return jsonify(projects=attach_liked(db, rows, row))


@app.get("/api/notifications")
def list_notifications():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)
    rows = get_db().execute(
        """
        SELECT n.id, n.type, n.is_read, n.created_at, n.project_id,
               u.username AS actor_username,
               COALESCE(NULLIF(u.display_name,''), u.username) AS actor_display,
               u.avatar AS actor_avatar,
               p.name AS project_name
        FROM notifications n
        JOIN users u ON u.id = n.actor_id
        LEFT JOIN projects p ON p.id = n.project_id
        WHERE n.user_id = ?
        ORDER BY n.id DESC
        LIMIT 50
        """, (row["id"],)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["is_read"] = bool(d["is_read"])
        out.append(d)
    return jsonify(notifications=out)


@app.post("/api/notifications/read")
def read_notifications():
    row = current_user()
    if row is None:
        return json_error("You must be logged in.", 401)
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (row["id"],))
    db.commit()
    return jsonify(ok=True)


@app.get("/api/trending")
def trending():
    db = get_db()
    viewer = current_user()
    rows = db.execute(_project_by_id_sql("ORDER BY p.created_at DESC LIMIT 200")).fetchall()
    scored = sorted(rows, key=lambda r: (r["likes"] * 3 + r["comments_count"] * 2 + r["views"] / 10,
                                         r["id"]), reverse=True)[:12]
    return jsonify(projects=attach_liked(db, scored, viewer))


@app.get("/api/tags")
def tags():
    counts: dict[str, int] = {}
    for r in get_db().execute("SELECT tech FROM projects WHERE tech <> ''").fetchall():
        for t in (x.strip() for x in r["tech"].split(",")):
            if t:
                counts[t] = counts.get(t, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:30]
    return jsonify(tags=[{"name": k, "count": v} for k, v in top])


@app.get("/api/users")
def search_users():
    q = (request.args.get("q") or "").strip().lower()
    sql = ("SELECT username, COALESCE(NULLIF(display_name,''), username) AS display_name, avatar "
           "FROM users ")
    params: tuple = ()
    if q:
        sql += "WHERE lower(username) LIKE ? OR lower(display_name) LIKE ? "
        like = f"%{q}%"
        params = (like, like)
    sql += "ORDER BY username LIMIT 20"
    return jsonify(users=[dict(r) for r in get_db().execute(sql, params).fetchall()])


# --------------------------------------------------------------------------- #
# Misc
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    try:
        get_db().execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify(ok=db_ok, name="DevHub", db="postgres" if dbm.IS_PG else "sqlite",
                   time=now_iso()), (200 if db_ok else 503)


@app.get("/robots.txt")
def robots():
    base = request.url_root.rstrip("/")
    return Response(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n",
                    mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip("/")
    db = get_db()
    urls = [f"{base}/", f"{base}/leaderboard", f"{base}/activity", f"{base}/trending", f"{base}/docs"]
    urls += [f"{base}/u/{r['username']}" for r in db.execute("SELECT username FROM users").fetchall()]
    urls += [f"{base}/?project={r['id']}" for r in db.execute("SELECT id FROM projects").fetchall()]
    body = "".join(f"<url><loc>{xml_escape(u)}</loc></url>" for u in urls)
    return Response('<?xml version="1.0" encoding="UTF-8"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</urlset>",
                    mimetype="application/xml")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
