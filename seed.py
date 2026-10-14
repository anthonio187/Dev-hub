"""Load fun demo data into DevHub so the hub never looks empty.

Usage:
    python seed.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import db as dbm
from app import AVATARS
from werkzeug.security import generate_password_hash


def cover(c1: str, c2: str, letter: str) -> str:
    """Build a local gradient SVG data-URI so no network is needed."""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='320'>"
        "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
        f"<stop offset='0' stop-color='{c1}'/><stop offset='1' stop-color='{c2}'/>"
        "</linearGradient></defs>"
        f"<rect width='640' height='320' fill='url(%23g)'/>"
        f"<text x='320' y='195' font-size='110' text-anchor='middle' "
        f"fill='rgba(255,255,255,0.9)' font-family='sans-serif'>{letter}</text></svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg, safe="'/:;,=& %")


def iso(days_ago: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


USERS = [
    ("ada",      "Ada Lovelace", "🦄", "Writing the first algorithms, one punch card at a time."),
    ("grace",    "Grace Hopper", "🦉", "Compiler whisperer. Ship it, then debug it."),
    ("linus",    "Linus T.",     "🐧", "Talk is cheap. Show me the code."),
    ("margaret", "Margaret H.",  "🚀", "Apollo guidance software and other small projects."),
    ("alan",     "Alan T.",      "🤖", "Machines that think, games that play."),
    ("hedy",     "Hedy Lamarr",  "🌟", "Inventing frequency hopping between takes."),
]

# (owner, name, description, tech, status, progress, repo, live, cover, pinned, views, days_ago)
PROJECTS = [
    ("ada", "Analytical Engine Notes", "The first computer program ever written — algorithms for **Bernoulli numbers**.\n\nYes, I documented the *engine* better than anyone built it.", "Math, Punch Cards, Vision", "shipped", 100,
     "https://github.com/example/analytical-notes", "", cover("#6a5acd", "#00c2a8", "A"), 1, 214, 20),
    ("grace", "COBOL-n't", "A modern compiler that turns plain English into working code.\n\nFound the first *actual* bug — it was a real moth. 🦋", "Rust, LLVM, NLP", "in_progress", 72,
     "https://github.com/example/cobolnt", "https://example.com/cobolnt", cover("#0f6cbd", "#7ce38b", "C"), 1, 158, 14),
    ("linus", "git-but-nice", "Version control with a UI that doesn't require a PhD.\n\nJust kidding, the terminal version ships first, as always.", "C, GTK", "in_progress", 45,
     "https://github.com/example/git-but-nice", "", cover("#24292e", "#f9826c", "g"), 0, 301, 12),
    ("margaret", "Guidance Simulator", "Full mission simulator for the Apollo guidance computer — runs in your **browser**.", "JavaScript, WebAssembly", "shipped", 100,
     "https://github.com/example/apollo-sim", "https://example.com/apollo-sim", cover("#1f2937", "#60a5fa", "Moon"), 0, 412, 9),
    ("alan", "Enigma Breaker", "Machine-learning assisted cryptanalysis playground. Learn how Bletchley Park *actually* did it.", "Python, PyTorch", "shipped", 100,
     "https://github.com/example/enigma-breaker", "", cover("#312e81", "#f59e0b", "Key"), 0, 189, 7),
    ("hedy", "FreqHop", "Secure mesh messaging for phones using frequency hopping — Wi-Fi's cool grandma.", "C++, Bluetooth", "idea", 5,
     "", "", cover("#be185d", "#fb923c", "Wave"), 0, 67, 5),
    ("ada", "Poetry Engine", "Generative poetry that actually scans. Rhyme, meter and *feeling*, from a machine.", "Python, TensorFlow", "in_progress", 60,
     "https://github.com/example/poetry-engine", "https://example.com/poetry", cover("#7c3aed", "#f472b6", "Pen"), 0, 93, 4),
    ("grace", "Nanosecond Visualizer", "Explaining why processors waste time with actual wire-length demos. A nanosecond is ~30cm!", "D3.js, Physics", "shipped", 100,
     "https://github.com/example/nanosecond", "https://example.com/nanosec", cover("#065f46", "#34d399", "1ns"), 0, 176, 2),
]

# (owner_username, project_index, body, days_ago)
COMMENTS = [
    ("grace", 0, "Legend. The first program and it was better documented than most code today. ❤️", 18),
    ("linus", 0, "Not bad for punch cards. Would merge.", 17),
    ("ada", 2, "The name is… honest. Starred anyway.", 11),
    ("margaret", 2, "Terminal-first is the right call!", 10),
    ("alan", 3, "Ran the full mission in my browser. Absolutely wild.", 8),
    ("hedy", 4, "This is gorgeous work — can I embed it in my mesh project?", 6),
    ("linus", 6, "Does it rhyme in iambic pentameter or is this toy-tier?", 3),
    ("ada", 7, "The wire-length demo finally made nanoseconds *feel* real. Sharing with everyone.", 1),
]

# (username, project_index)
LIKES = [
    ("grace", 0), ("linus", 0), ("margaret", 0), ("alan", 0), ("hedy", 0),
    ("ada", 1), ("linus", 1), ("hedy", 1),
    ("ada", 2), ("grace", 2), ("alan", 2),
    ("ada", 3), ("grace", 3), ("linus", 3), ("hedy", 3), ("alan", 3),
    ("grace", 4), ("hedy", 4), ("margaret", 4),
    ("ada", 6), ("grace", 6),
    ("ada", 7), ("linus", 7), ("margaret", 7),
]

FOLLOWS = [
    ("grace", "ada"), ("linus", "ada"), ("hedy", "ada"),
    ("ada", "grace"), ("margaret", "grace"), ("hedy", "grace"),
    ("ada", "margaret"), ("grace", "margaret"),
    ("grace", "alan"), ("hedy", "alan"),
    ("ada", "hedy"), ("linus", "hedy"),
]


def main() -> None:
    if "--if-enabled" in sys.argv and os.environ.get("SEED_DEMO", "").lower() not in ("1", "true", "yes"):
        print("SEED_DEMO not enabled — skipping demo data.")
        return
    db = dbm.connect()

    if db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] > 0:
        print("Database already has users — skipping seed (wipe the database to reseed).")
        db.close()
        return

    password = generate_password_hash("password123")
    user_ids = {}
    for i, (username, display, avatar, bio) in enumerate(USERS):
        cur = db.execute(
            "INSERT INTO users (username, password_hash, display_name, bio, avatar, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, password, display, bio, avatar or AVATARS[0], iso(30 - i * 2)),
        )
        user_ids[username] = cur.lastrowid
        db.execute(
            "INSERT INTO activities (user_id, type, project_id, created_at) VALUES (?, 'user_joined', NULL, ?)",
            (user_ids[username], iso(30 - i * 2)),
        )

    project_ids = []
    for owner, name, desc, tech, status, progress, repo, live, cov, pinned, views, days in PROJECTS:
        cur = db.execute(
            "INSERT INTO projects (user_id, name, description, tech, repo_url, live_url, cover_url, "
            "status, progress, pinned, views, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_ids[owner], name, desc, tech, repo, live, cov, status, progress, pinned, views,
             iso(days), iso(days)),
        )
        project_ids.append(cur.lastrowid)
        db.execute(
            "INSERT INTO activities (user_id, type, project_id, created_at) VALUES (?, 'project_added', ?, ?)",
            (user_ids[owner], cur.lastrowid, iso(days)),
        )
        if status == "shipped":
            db.execute(
                "INSERT INTO activities (user_id, type, project_id, created_at) VALUES (?, 'project_shipped', ?, ?)",
                (user_ids[owner], cur.lastrowid, iso(max(0, days - 0.5))),
            )

    for username, idx, body, days in COMMENTS:
        cur = db.execute(
            "INSERT INTO comments (user_id, project_id, body, created_at) VALUES (?, ?, ?, ?)",
            (user_ids[username], project_ids[idx], body, iso(days)),
        )
        db.execute(
            "INSERT INTO activities (user_id, type, project_id, created_at) VALUES (?, 'comment_added', ?, ?)",
            (user_ids[username], project_ids[idx], iso(days)),
        )

    for username, idx in LIKES:
        db.execute(
            "INSERT INTO likes (user_id, project_id, created_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (user_ids[username], project_ids[idx], iso(1)),
        )

    for follower, followee in FOLLOWS:
        db.execute(
            "INSERT INTO follows (follower_id, followee_id, created_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (user_ids[follower], user_ids[followee], iso(2)),
        )

    db.commit()
    db.close()
    print(f"Seeded {len(USERS)} users, {len(PROJECTS)} projects, {len(COMMENTS)} comments, "
          f"{len(LIKES)} likes, {len(FOLLOWS)} follows.")
    print("Demo login: any username above, password 'password123' (e.g. ada / password123)")


if __name__ == "__main__":
    main()
