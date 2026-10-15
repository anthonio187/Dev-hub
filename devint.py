"""Developer-platform integrations: GitHub, GitLab, Dev.to and npm.

Only public endpoints are used, so no OAuth app is required. Set GITHUB_TOKEN
(a read-only token with no scopes) on the server to raise GitHub's rate limit
from 60 to 5000 requests/hour. The token is never sent to the browser.
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 6
USER_AGENT = "DevX/1.0 (developer social network)"

PROVIDERS = {
    "github": {
        "label": "GitHub",
        "pattern": r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37})$",
        "verify": True,
        "placeholder": "octocat",
        "hint": "Your GitHub username",
    },
    "gitlab": {
        "label": "GitLab",
        "pattern": r"^[A-Za-z0-9_.-]{2,255}$",
        "verify": False,
        "placeholder": "your-gitlab-username",
        "hint": "Your GitLab username",
    },
    "devto": {
        "label": "DEV Community",
        "pattern": r"^[A-Za-z0-9_-]{2,30}$",
        "verify": False,
        "placeholder": "your-devto-username",
        "hint": "Your dev.to username",
    },
    "npm": {
        "label": "npm",
        "pattern": r"^[a-z0-9][a-z0-9._-]{0,213}$",
        "verify": False,
        "placeholder": "your-npm-username",
        "hint": "Your npm username (packages you maintain are shown)",
    },
}

GITHUB_REPO_RE = re.compile(r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")


class ProviderError(Exception):
    """code is one of: not_found, rate_limited, unreachable, bad_response."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def valid_handle(provider: str, handle: str) -> bool:
    spec = PROVIDERS.get(provider)
    return bool(spec and re.match(spec["pattern"], handle or ""))


def _get_json(url: str, headers=None):
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    req_headers.update(headers or {})
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ProviderError("not_found")
        if exc.code in (403, 429):
            raise ProviderError("rate_limited")
        raise ProviderError("unreachable")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError("unreachable")
    except ValueError:
        raise ProviderError("bad_response")


def _github_headers():
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


# ----------------------------------------------------------------- GitHub
def github_user(handle: str) -> dict:
    h = _github_headers()
    user = _get_json(f"https://api.github.com/users/{urllib.parse.quote(handle)}", h)
    repos = _get_json(
        f"https://api.github.com/users/{urllib.parse.quote(handle)}/repos?per_page=100&sort=pushed&type=owner", h)
    own = [r for r in repos if not r.get("fork")]
    langs = {}
    for r in own:
        if r.get("language"):
            langs[r["language"]] = langs.get(r["language"], 0) + 1
    top_langs = [{"name": k, "repos": v}
                 for k, v in sorted(langs.items(), key=lambda kv: (-kv[1], kv[0]))[:6]]
    top = sorted(own, key=lambda r: -(r.get("stargazers_count") or 0))[:5]
    return {
        "name": user.get("name") or user.get("login") or handle,
        "bio": user.get("bio") or "",
        "avatar_url": user.get("avatar_url"),
        "url": user.get("html_url"),
        "followers": user.get("followers", 0),
        "public_repos": user.get("public_repos", 0),
        "total_stars": sum(r.get("stargazers_count") or 0 for r in own),
        "languages": top_langs,
        "top_repos": [{
            "name": r.get("name"), "url": r.get("html_url"), "description": r.get("description") or "",
            "stars": r.get("stargazers_count") or 0, "language": r.get("language") or "",
        } for r in top],
    }


def github_bio(handle: str) -> str:
    user = _get_json(f"https://api.github.com/users/{urllib.parse.quote(handle)}", _github_headers())
    return user.get("bio") or ""


def github_repo(owner: str, name: str) -> dict:
    r = _get_json(f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}",
                  _github_headers())
    return {
        "kind": "github_repo",
        "full_name": r.get("full_name"),
        "url": r.get("html_url"),
        "description": r.get("description") or "",
        "stars": r.get("stargazers_count") or 0,
        "forks": r.get("forks_count") or 0,
        "language": r.get("language") or "",
        "owner_avatar": (r.get("owner") or {}).get("avatar_url"),
    }


# ----------------------------------------------------------------- GitLab
def gitlab_user(handle: str) -> dict:
    users = _get_json(f"https://gitlab.com/api/v4/users?username={urllib.parse.quote(handle)}")
    match = next((u for u in users if (u.get("username") or "").lower() == handle.lower()), None)
    if not match:
        raise ProviderError("not_found")
    projects = _get_json(
        f"https://gitlab.com/api/v4/users/{match['id']}/projects?visibility=public&order_by=star_count&sort=desc&per_page=5")
    return {
        "name": match.get("name") or handle,
        "bio": match.get("bio") or "",
        "avatar_url": match.get("avatar_url"),
        "url": match.get("web_url"),
        "projects": [{"name": p.get("name"), "url": p.get("web_url"), "description": p.get("description") or "",
                      "stars": p.get("star_count") or 0} for p in projects],
    }


# ----------------------------------------------------------------- DEV Community
def devto_user(handle: str) -> dict:
    user = _get_json(f"https://dev.to/api/users/by_username?url={urllib.parse.quote(handle)}")
    articles = _get_json(f"https://dev.to/api/articles?username={urllib.parse.quote(handle)}&per_page=5")
    return {
        "name": user.get("name") or handle,
        "bio": user.get("summary") or "",
        "avatar_url": user.get("profile_image"),
        "url": f"https://dev.to/{handle}",
        "articles": [{"title": a.get("title"), "url": a.get("url"), "reactions": a.get("positive_reactions_count") or 0}
                     for a in articles[:5]],
    }


# ----------------------------------------------------------------- npm
def npm_user(handle: str) -> dict:
    data = _get_json("https://registry.npmjs.org/-/v1/search?size=20&text=maintainer:" + urllib.parse.quote(handle))
    packages = []
    for obj in data.get("objects", []):
        pkg = obj.get("package") or {}
        maintainers = [(m.get("username") or "").lower() for m in pkg.get("maintainers", [])]
        if handle.lower() in maintainers:
            packages.append({
                "name": pkg.get("name"),
                "description": pkg.get("description") or "",
                "version": pkg.get("version") or "",
                "url": (pkg.get("links") or {}).get("npm") or f"https://www.npmjs.com/package/{pkg.get('name')}",
            })
    if not packages:
        raise ProviderError("not_found")
    return {
        "name": handle,
        "bio": "",
        "avatar_url": None,
        "url": f"https://www.npmjs.com/~{handle}",
        "packages": packages[:6],
    }


FETCHERS = {"github": github_user, "gitlab": gitlab_user, "devto": devto_user, "npm": npm_user}


def fetch_profile(provider: str, handle: str) -> dict:
    fn = FETCHERS.get(provider)
    if not fn:
        raise ProviderError("not_found")
    return fn(handle)


def parse_github_repo_url(url: str):
    m = GITHUB_REPO_RE.match(url or "")
    if not m:
        return None
    owner, name = m.group(1), m.group(2)
    if name in (".", ".."):
        return None
    return owner, name
