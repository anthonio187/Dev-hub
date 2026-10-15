# DevX — the social network for developers

A full-stack social network for developers, built for developers: posts with code snippets,
replies, reposts, quote posts, likes, bookmarks, follows, a home timeline, profile tabs,
explore/trends, search, notifications, and direct messages with image uploads.

**Stack:** Python (Flask) · Postgres on Neon (SQLite for local dev) · vanilla JS SPA, no build step.

## Features

| Area | What works |
|---|---|
| Accounts | Sign up, log in, log out, change password, delete account, session cookies, rate limiting on login/signup |
| Profile | Display name, bio, location, website, **tech stack chips**, avatar + banner image uploads, followers/following lists |
| Posts | 280-character posts, **code snippets** (20+ languages, copy button), up to 4 images, hashtags, @mentions |
| Interactions | Reply (threaded view), repost / undo, quote post, like / unlike, bookmark, copy link, delete own post |
| Timeline | "For you" (everyone) and "Following" tabs, cursor pagination ("Show more" + infinite scroll) |
| Profiles | Posts, Replies, Media, Likes tabs |
| Discovery | Explore (latest), Trends (7-day hashtags), Who to follow, search for posts / people / hashtags |
| Notifications | Likes, reposts, replies, quotes, mentions, follows; unread badge; mark all read |
| Messages | Start a conversation by username, send text and **image** messages, unread counts, load older messages, live updates (polls every 3s) |
| Developer accounts | Link **GitHub** (verified by adding a code to your bio), **GitLab**, **DEV Community** and **npm** (public profiles, no OAuth app needed) |
| GitHub profile | Followers, repos, total stars, top languages, top repos (refreshed every 6h, last good data kept on failure) |
| Other platforms | GitLab top projects, DEV articles, npm packages you maintain |
| Repo previews | Posts that link a GitHub repo show a live card (stars, language, description), cached 24h |
| Availability | "Open to work" badge and "Available for…" text on your profile |
| Developers directory | `/devs`: browse developers, filter by tech stack, show only people open to work |
| UX | three-column layout, mobile bottom bar, dark/light theme, keyboard shortcuts (`n` new post, `/` search) |

Security: passwords hashed (Werkzeug), CSRF guard on all mutating API calls (requires `X-Requested-With`),
strict Content-Security-Policy, uploads validated by file signature (PNG/JPEG/GIF/WEBP only, 5 MB max),
all user text rendered as text (no `innerHTML`).

## Run locally (SQLite)

```bash
pip install -r requirements.txt
python app.py                 # http://localhost:5000
```

## Developer integrations

- Settings → **Developer accounts**: link a username per platform. GitHub links require ownership
  verification: DevX gives you a `devx-xxxxxxxx` code, you paste it into your GitHub bio, then click *Verify*.
- The code is removed after verification, and a GitHub account can only be verified by one DevX profile.
- Optional: set `GITHUB_TOKEN` (a token with **no scopes**) to raise GitHub's API limit from 60 to 5,000 requests/hour.
- Stack Overflow is not included yet; its API requires a registered app key.

## Use Neon (Postgres) — recommended for production

1. Create a project at https://neon.tech and copy the connection string.
2. Set the environment variable (don't commit it):

   ```bash
   export DATABASE_URL="postgresql://USER:PASSWORD@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require"
   export SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
   export PRODUCTION=1
   python app.py
   ```

The tables are created automatically on first start (`CREATE TABLE IF NOT EXISTS`), so no migration step is needed.

Deploy anywhere that runs a Procfile (Render, Railway, Heroku-style hosts): set the same three variables and the
start command is `gunicorn app:app -c gunicorn.conf.py` (the Procfile already does this).

## Tests

```bash
pip install pytest
pytest -q                     # 36 API + developer-integration tests (SQLite by default)
DATABASE_URL=postgresql://... pytest -q     # same suite against Postgres / Neon
```

Browser test (two users interacting, DMs with images, live updates, mobile layout):

```bash
pip install playwright && python -m playwright install chromium
python app.py &                # on a fresh database (delete devx.db first)
BASE_URL=http://localhost:5000 python tests/e2e_browser.py
```

## Project structure

```
DevX/
├── app.py              # Flask app: JSON API, media, auth, feeds, DMs, developer routes
├── devint.py           # GitHub / GitLab / DEV / npm clients (timeouts, error mapping)
├── gunicorn.conf.py    # production server settings
├── db.py               # Postgres (Neon) / SQLite layer
├── templates/index.html# SPA shell
├── static/style.css    # DevX theme (dark + light)
├── static/app.js       # Frontend: router, composer, feeds, DMs, settings
├── tests/test_api.py   # API tests
├── tests/test_dev.py   # developer-integration tests (offline, mocked)
├── tests/e2e_browser.py# Browser end-to-end test
├── requirements.txt
├── Procfile
└── .env.example
```

## API overview

All JSON. Mutating requests need the header `X-Requested-With: XMLHttpRequest`.

- `POST /api/auth/signup` · `POST /api/auth/login` · `POST /api/auth/logout` · `GET /api/auth/me`
- `PATCH /api/me` · `DELETE /api/me` · `POST /api/auth/password` · `POST /api/media` · `GET /media/<id>`
- `POST /api/posts` · `GET /api/posts/<id>` · `GET /api/posts/<id>/replies` · `DELETE /api/posts/<id>`
- `POST|DELETE /api/posts/<id>/like|repost|bookmark` · `GET /api/bookmarks`
- `GET /api/timeline` · `GET /api/explore` · `GET /api/trends` · `GET /api/who-to-follow` · `GET /api/search?q=`
- `GET /api/users/<username>` · `GET /api/users/<username>/posts?tab=` · `POST|DELETE /api/users/<username>/follow`
- `GET /api/users/<username>/followers|following`
- `GET /api/notifications` · `POST /api/notifications/read` · `GET /api/counts`
- `GET /api/conversations` · `POST /api/conversations` · `GET|POST /api/conversations/<id>/messages`

## DevHub feature additions

- **Accounts:** email required at sign-up (unique), log in with username or email, password reset by email (1-hour single-use link, `/forgot` and `/reset`), email and LinkedIn in settings.
- **Posts:** edit your own posts (marked "edited"); attach images and documents (PDF, ZIP, text and source files up to 10 MB, downloaded as attachments).
- **Messages:** send images or files; file attachments download; new-message notifications link to the conversation.
- **Projects:** create, edit, and delete portfolio projects with tags, status, repo and live links, and a screenshot. Browse and filter by tag/status, like projects, see likes notify the owner, and view possible collaborators who share a tag.
- **Collaboration:** post open requests with skills and goals (optionally linked to a project), express interest, withdraw, and let the owner accept or decline. Status is tracked on both the request and each interest. Notifications link to the request.
- **Search:** finds projects too; posts can be filtered by language (`/search?q=…&lang=rust`).
- **Storage:** set `S3_BUCKET` and the S3 variables to store uploads in R2, S3, or Supabase Storage. `boto3` is needed only then.

Tests: `pytest -q` (55 tests; `tests/test_features.py` covers the new features with a fake S3 client). Browser E2E: `BASE_URL=http://localhost:5056 python tests/e2e_browser.py` (15 steps).
