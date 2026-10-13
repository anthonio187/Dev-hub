# ⌨️ DevHub — a project hub for developers

DevHub is a full-stack web app where developers create an account, add the
projects they're building, follow each other, and showcase everything in a
public community feed.

**Stack:** Python (Flask) · Postgres (SQLite for local dev) · vanilla HTML/CSS/JS — no build step.

## ✨ Features (40+)

**Accounts**
1. 🔐 Sign up / log in / log out (hashed passwords, session cookies)
2. 🔑 Change password
3. 🗑️ Delete account (password-confirmed, cascades all data)
4. 💾 Export all your data as JSON
5. 😀 Emoji avatar picker

**Projects**
6. 📁 Full project CRUD from your dashboard
7. 🖼️ Cover images per project
8. 📊 Progress tracker (0–100% slider + progress bars)
9. 💡🚧🚀 Status badges (Idea / In progress / Shipped)
10. 📌 Pin projects to the top of your list
11. ✍️ Markdown-lite descriptions (**bold**, *italic*, `code`, links)
12. 🏷️ Tech-stack chips
13. 👁️ View counters
14. 🕒 "Time ago" timestamps + edited markers

**Social**
15. ❤️ Like / unlike projects (one per user, live counts)
16. 💬 Comments with delete-your-own
17. 🧑‍🤝‍🧑 Follow developers + "Following only" feed filter
18. 👤 Public profile pages (`/u/<username>`) with stats
19. 🏆 Leaderboard (`/leaderboard`) — top devs by likes
20. 📰 Activity feed (`/activity`) — everything happening on the hub
21. 🌍 Global community stats strip

**Discovery & UX**
22. 🔍 Live search (projects, tech, developers)
23. 🎛️ Status filter + sortable feed (newest / oldest / most liked / most viewed / A–Z)
24. 🏷️ Click any tech chip to filter the showcase by it
25. 🔍 Project detail modal — deep-linkable (`/?project=<id>`)
26. 🔗 Share buttons that copy links
27. 📄 Load-more pagination
28. 🌗 Dark/light theme toggle (remembered)
29. ⌨️ Keyboard shortcuts: `/` search · `N` new project · `?` help · `Esc` close
30. 📊 Dashboard stats (totals, views, likes received)

**New**
- 🔖 Bookmark projects + `/saved` page
- 🔔 Notifications (likes, comments, follows) with unread badge + `/notifications`
- 🔥 Trending page (`/trending`) and `/api/tags`, `/api/users?q=`
- 🗺️ `sitemap.xml` + `robots.txt`, DB-aware health check

**Under the hood**
31. 📡 RSS feed of newest projects (`/feed.xml`)
32. 📚 Built-in API docs page (`/docs`)
33. 🚫 Custom 404 page (JSON errors for API routes)
34. 🛡️ Rate limiting on login/signup
35. 🔒 Security headers + Content-Security-Policy
36. 🌱 Demo data seeder (`python seed.py`)

## Quick start

```bash
git clone https://github.com/anthonio187/Dev-hub.git
cd Dev-hub
pip install -r requirements.txt
python app.py          # -> http://localhost:5000
python seed.py         # optional: load demo users & projects
```

The SQLite database (`devhub.db`) is created (and old versions migrated)
automatically. Demo login after seeding: `ada` / `password123`.

## Project structure

```
Dev-hub/
├── app.py               # Flask app: pages + JSON API
├── db.py                # SQLite/Postgres layer
├── render.yaml          # Render blueprint
├── Procfile
├── seed.py              # Optional demo data loader
├── requirements.txt     # pip dependencies (Flask only)
├── templates/           # Landing, dashboard, profile, leaderboard, activity, docs, 404
├── static/
│   ├── style.css        # Dark neon theme + light mode
│   └── app.js           # Frontend logic (all pages)
└── .gitignore
```

Runtime files created automatically (not shipped): `devhub.db`, `.secret_key`.

## API reference

Full interactive reference lives at **`/docs`** in the running app. Auth uses
the session cookie set by signup/login. All endpoints return JSON.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/health` | — | Health check |
| GET | `/api/stats` | — | Global stats |
| POST | `/api/signup` | — | Create account |
| POST | `/api/login` | — | Log in |
| POST | `/api/logout` | ✓ | Log out |
| GET/PUT | `/api/me` | ✓ for PUT | Profile; PUT updates name/bio/avatar |
| PUT | `/api/me/password` | ✓ | Change password |
| DELETE | `/api/me` | ✓ | Delete account (password confirm) |
| GET | `/api/me/export` | ✓ | Download your data |
| GET | `/api/me/following` | ✓ | Who you follow |
| GET | `/api/projects` | — | Showcase feed |
| GET | `/api/my/projects` | ✓ | Your projects |
| POST | `/api/projects` | ✓ | Create project |
| GET | `/api/projects/<id>` | — | Detail (+1 view) |
| PUT/DELETE | `/api/projects/<id>` | ✓ | Update / delete yours |
| POST | `/api/projects/<id>/like` | ✓ | Toggle like |
| POST | `/api/projects/<id>/pin` | ✓ | Toggle pin |
| GET/POST | `/api/projects/<id>/comments` | ✓ for POST | Comments |
| DELETE | `/api/comments/<id>` | ✓ | Delete your comment |
| GET | `/api/users/<username>` | — | Public profile |
| POST | `/api/users/<username>/follow` | ✓ | Toggle follow |
| GET | `/api/leaderboard` | — | Top developers |
| GET | `/api/activity` | — | Activity feed |
| GET | `/feed.xml` | — | RSS of new projects |

Example:

```bash
curl -c cookies.txt -X POST http://localhost:5000/api/signup \
  -H "Content-Type: application/json" \
  -d '{"username": "dev_queen", "password": "secret123"}'

curl -b cookies.txt -X POST http://localhost:5000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "DevHub", "tech": "Python, Flask", "status": "shipped", "progress": 100}'
```

## Deploying on Render

1. Push this folder to GitHub.
2. Render → **New → Blueprint** → select the repo. `render.yaml` creates the
   web service + a free Postgres database and wires `DATABASE_URL`,
   `SECRET_KEY` automatically.
3. Deploy. Demo data loads on first start (`SEED_DEMO=true`; set to `false` to disable).
   Demo login: `ada` / `password123`.

Manual setup instead: create a Postgres DB, then a Web Service with
build `pip install -r requirements.txt`, start
`gunicorn app:app --workers 2 --threads 4 --bind 0.0.0.0:$PORT`, and env vars
`DATABASE_URL` (internal URL), `SECRET_KEY` (random string).

Notes: free Render Postgres expires after 30 days — upgrade or export
data (`/api/me/export`) before then. Without `DATABASE_URL` the app uses
local SQLite (`devhub.db`), which Render wipes on redeploy.

## Troubleshooting

- **Images from the internet don't load in an in-app preview?** Sandboxed
  previews may block network requests; the app is fine in a real browser.
  Demo covers are embedded SVGs, so they always work.
- **"That username is already taken"** — usernames are unique (case-insensitive).
- **Too many attempts error** — rate limiting kicked in; wait a few minutes.
- **Reset everything** — stop the server and delete `devhub.db`.
