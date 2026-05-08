from __future__ import annotations

import base64
import os
from typing import Any

import httpx

USER_AGENT = "VERONICA/0.3 (+https://localhost)"
HTTP_TIMEOUT = 6.0


def _gh_headers() -> dict[str, str]:
    from app.config import settings
    token = settings.github_token or os.getenv("GITHUB_TOKEN", "")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def list_pull_requests(repo: str, state: str = "open") -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=_gh_headers()) as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo}/pulls",
                params={"state": state, "per_page": 10},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"tool": "list_pull_requests", "ok": False, "error": str(exc)}

    prs = [
        {
            "number": pr["number"],
            "title": pr["title"],
            "user": pr["user"]["login"],
            "state": pr["state"],
            "draft": pr.get("draft", False),
            "created_at": pr["created_at"],
            "updated_at": pr["updated_at"],
            "url": pr["html_url"],
        }
        for pr in data
    ]
    return {"tool": "list_pull_requests", "ok": True, "repo": repo, "state": state, "result": prs}


async def get_pr_review(repo: str, pr_number: int) -> dict[str, Any]:
    headers = _gh_headers()
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            meta_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
            )
            meta_resp.raise_for_status()
            meta = meta_resp.json()

            diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
            diff_resp = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
                headers=diff_headers,
            )
            diff_text = diff_resp.text[:5000] if diff_resp.status_code == 200 else ""
    except httpx.HTTPError as exc:
        return {"tool": "get_pr_review", "ok": False, "error": str(exc)}

    return {
        "tool": "get_pr_review",
        "ok": True,
        "result": {
            "number": meta["number"],
            "title": meta["title"],
            "user": meta["user"]["login"],
            "state": meta["state"],
            "body": (meta.get("body") or "")[:1000],
            "base": meta["base"]["ref"],
            "head": meta["head"]["ref"],
            "url": meta["html_url"],
            "additions": meta.get("additions"),
            "deletions": meta.get("deletions"),
            "changed_files": meta.get("changed_files"),
            "diff": diff_text,
        },
    }


async def list_recent_commits(repo: str, limit: int = 5) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=_gh_headers()) as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo}/commits",
                params={"per_page": min(limit, 30)},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"tool": "list_recent_commits", "ok": False, "error": str(exc)}

    commits = [
        {
            "sha": c["sha"][:7],
            "message": (c["commit"]["message"].split("\n")[0])[:120],
            "author": c["commit"]["author"]["name"],
            "date": c["commit"]["author"]["date"],
            "url": c["html_url"],
        }
        for c in data
    ]
    return {"tool": "list_recent_commits", "ok": True, "repo": repo, "result": commits}


async def list_user_repos(username: str, limit: int = 30) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=_gh_headers()) as client:
            response = await client.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": min(limit, 100), "sort": "updated", "type": "all"},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"tool": "list_user_repos", "ok": False, "error": str(exc)}

    repos = [
        {
            "name": r["name"],
            "full_name": r["full_name"],
            "description": r.get("description"),
            "language": r.get("language"),
            "private": r.get("private", False),
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "open_issues": r.get("open_issues_count", 0),
            "default_branch": r.get("default_branch", "main"),
            "url": r["html_url"],
            "updated_at": r.get("updated_at"),
        }
        for r in data
    ]
    return {"tool": "list_user_repos", "ok": True, "username": username, "result": repos}


async def get_repo_stats(repo: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=_gh_headers()) as client:
            response = await client.get(f"https://api.github.com/repos/{repo}")
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"tool": "get_repo_stats", "ok": False, "error": str(exc)}

    return {
        "tool": "get_repo_stats",
        "ok": True,
        "result": {
            "name": data.get("full_name"),
            "description": data.get("description"),
            "language": data.get("language"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "open_issues": data.get("open_issues_count"),
            "url": data.get("html_url"),
            "default_branch": data.get("default_branch"),
            "updated_at": data.get("updated_at"),
        },
    }


async def commit_file(
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
) -> dict[str, Any]:
    """Create or update a single file in a repo via the GitHub Contents API."""
    from app.config import settings
    token = settings.github_token or os.getenv("GITHUB_TOKEN", "")
    if not token:
        return {"tool": "commit_file", "ok": False, "error": "GITHUB_TOKEN not configured"}

    headers = {**_gh_headers(), "Authorization": f"Bearer {token}"}
    url = f"https://api.github.com/repos/{repo}/contents/{path.lstrip('/')}"
    encoded = base64.b64encode(content.encode()).decode()

    body: dict[str, Any] = {"message": message, "content": encoded, "branch": branch}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            # Check if file already exists — if so, include its SHA for update
            existing = await client.get(url, params={"ref": branch})
            if existing.status_code == 200:
                body["sha"] = existing.json().get("sha", "")

            resp = await client.put(url, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return {"tool": "commit_file", "ok": False, "error": str(exc)}

    commit = data.get("commit", {})
    file_url = (data.get("content") or {}).get("html_url", "")
    return {
        "tool": "commit_file",
        "ok": True,
        "result": {
            "sha": commit.get("sha", "")[:7],
            "message": commit.get("message", ""),
            "url": commit.get("html_url", ""),
            "file_url": file_url,
            "repo": repo,
            "path": path,
            "branch": branch,
        },
    }
