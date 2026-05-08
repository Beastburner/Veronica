from __future__ import annotations

import ast
import asyncio
import json
import logging
import operator
import os
import re
import shlex
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.storage import current_local_time

log = logging.getLogger("veronica.tools")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HTTP_TIMEOUT = 6.0


# ── Time ────────────────────────────────────────────────────────────────────


async def get_current_time() -> dict[str, Any]:
    now = current_local_time()
    return {
        "tool": "get_current_time",
        "ok": True,
        "result": {
            "iso": now.isoformat(),
            "human": now.strftime("%I:%M %p IST on %B %d, %Y"),
        },
    }


# ── Calculator (safe AST eval) ──────────────────────────────────────────────

_SAFE_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_SAFE_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_BINOPS:
        return _SAFE_BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_UNARY:
        return _SAFE_UNARY[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported expression")


async def calculator(expression: str) -> dict[str, Any]:
    expr = expression.strip().replace("^", "**")
    try:
        tree = ast.parse(expr, mode="eval")
        value = _safe_eval(tree)
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError) as exc:
        return {"tool": "calculator", "ok": False, "error": str(exc), "expression": expr}
    return {"tool": "calculator", "ok": True, "result": value, "expression": expr}


# ── Weather (wttr.in) ───────────────────────────────────────────────────────


async def get_weather(city: str) -> dict[str, Any]:
    target = city.strip()
    if not target:
        return {"tool": "get_weather", "ok": False, "error": "no city"}
    url = f"https://wttr.in/{httpx.QueryParams({'q': target})}?format=j1"
    # wttr.in supports {city}?format=j1 directly
    url = f"https://wttr.in/{target.replace(' ', '+')}?format=j1"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        log.warning("weather fetch failed: %s", exc)
        return {"tool": "get_weather", "ok": False, "error": "weather provider unreachable"}

    current = (data.get("current_condition") or [{}])[0]
    nearest = (data.get("nearest_area") or [{}])[0]
    return {
        "tool": "get_weather",
        "ok": True,
        "result": {
            "city": (nearest.get("areaName") or [{}])[0].get("value", target),
            "country": (nearest.get("country") or [{}])[0].get("value", ""),
            "temp_c": current.get("temp_C"),
            "feels_like_c": current.get("FeelsLikeC"),
            "description": (current.get("weatherDesc") or [{}])[0].get("value", ""),
            "humidity": current.get("humidity"),
            "wind_kmph": current.get("windspeedKmph"),
        },
    }


# ── Web search (DuckDuckGo Instant Answer) ─────────────────────────────────


async def _ddg_instant(client: httpx.AsyncClient, query: str) -> list[dict[str, str]]:
    params = {"q": query, "format": "json", "no_html": "1", "no_redirect": "1"}
    response = await client.get("https://api.duckduckgo.com/", params=params)
    response.raise_for_status()
    data = response.json()
    results: list[dict[str, str]] = []
    abstract = (data.get("AbstractText") or "").strip()
    if abstract:
        results.append(
            {
                "title": data.get("Heading") or query,
                "snippet": abstract,
                "url": data.get("AbstractURL") or "",
            }
        )
    for topic in (data.get("RelatedTopics") or [])[:3]:
        if not isinstance(topic, dict):
            continue
        text = (topic.get("Text") or "").strip()
        url = topic.get("FirstURL") or ""
        if text and url:
            results.append({"title": text.split(" - ")[0][:80], "snippet": text, "url": url})
    return results


_DDG_HTML_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text).replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"').strip()


async def _ddg_html(client: httpx.AsyncClient, query: str) -> list[dict[str, str]]:
    response = await client.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
    )
    if response.status_code != 200:
        return []
    body = response.text
    out: list[dict[str, str]] = []
    for match in _DDG_HTML_RESULT.finditer(body):
        url, title_html, snippet_html = match.groups()
        title = _strip_tags(title_html)
        snippet = _strip_tags(snippet_html)
        if title and snippet:
            out.append({"title": title[:140], "snippet": snippet[:280], "url": url})
        if len(out) >= 3:
            break
    return out


async def web_search(query: str) -> dict[str, Any]:
    q = query.strip()
    if not q:
        return {"tool": "web_search", "ok": False, "error": "empty query"}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            results = await _ddg_instant(client, q)
            if not results:
                results = await _ddg_html(client, q)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        log.warning("search failed: %s", exc)
        return {"tool": "web_search", "ok": False, "error": "search provider unreachable"}

    if not results:
        return {"tool": "web_search", "ok": False, "query": q, "error": f"No results found for: {q}"}

    return {
        "tool": "web_search",
        "ok": True,
        "query": q,
        "result": results[:3],
    }


async def news_topic(topic: str) -> dict[str, Any]:
    """Search RSS feeds for a topic; fall back to web_search if nothing found."""
    from app.news import fetch_all_feeds
    topic_lower = topic.lower()
    keywords = topic_lower.split()
    try:
        articles = await asyncio.to_thread(fetch_all_feeds, 10)
        matches = [
            a for a in articles
            if any(kw in (a.get("title") or "").lower() or kw in (a.get("summary") or "").lower()
                   for kw in keywords)
        ]
        if matches:
            return {
                "tool": "news_topic",
                "ok": True,
                "topic": topic,
                "result": [
                    {"title": a["title"], "link": a["link"], "feed": a.get("feed_title", ""), "published": a.get("published", "")}
                    for a in matches[:5]
                ],
            }
    except Exception as exc:
        log.warning("news_topic rss error: %s", exc)

    # RSS had nothing — try live web search
    return await web_search(f"latest {topic} news")


# ── Safe shell command (whitelist) ─────────────────────────────────────────


_SAFE_COMMANDS = {"date", "ls", "pwd", "whoami", "uptime", "uname", "hostname", "echo", "df", "free"}


async def run_system_command(cmd: str) -> dict[str, Any]:
    parts = shlex.split(cmd, posix=os.name != "nt")
    if not parts:
        return {"tool": "run_system_command", "ok": False, "error": "empty command"}

    binary = parts[0].lower().replace(".exe", "")
    if binary not in _SAFE_COMMANDS:
        return {
            "tool": "run_system_command",
            "ok": False,
            "error": f"refused: {binary!r} not in whitelist",
            "whitelist": sorted(_SAFE_COMMANDS),
        }

    try:
        proc = await asyncio.create_subprocess_exec(
            *parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=4)
    except (FileNotFoundError, asyncio.TimeoutError, OSError) as exc:
        return {"tool": "run_system_command", "ok": False, "error": str(exc)}

    return {
        "tool": "run_system_command",
        "ok": proc.returncode == 0,
        "stdout": stdout.decode(errors="replace").strip()[:1000],
        "stderr": stderr.decode(errors="replace").strip()[:400],
        "returncode": proc.returncode,
    }


# ── GitHub (Phase 5) ───────────────────────────────────────────────────────


async def get_open_issues(repo: str) -> dict[str, Any]:
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo}/issues",
                params={"state": "open", "per_page": 5},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"tool": "get_open_issues", "ok": False, "error": str(exc)}

    issues = [
        {"number": i["number"], "title": i["title"], "url": i["html_url"]}
        for i in data
        if "pull_request" not in i
    ]
    return {"tool": "get_open_issues", "ok": True, "repo": repo, "result": issues}


async def create_issue(repo: str, title: str, body: str = "") -> dict[str, Any]:  # noqa: E303
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        return {"tool": "create_issue", "ok": False, "error": "GITHUB_TOKEN not configured"}
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers) as client:
            response = await client.post(
                f"https://api.github.com/repos/{repo}/issues",
                json={"title": title, "body": body},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"tool": "create_issue", "ok": False, "error": str(exc)}

    return {
        "tool": "create_issue",
        "ok": True,
        "result": {"number": data.get("number"), "url": data.get("html_url"), "title": data.get("title")},
    }


# ── Gmail wrappers ─────────────────────────────────────────────────────────


async def gmail_inbox(max_results: int = 10) -> dict[str, Any]:
    from app.gmail import list_inbox
    return await list_inbox(max_results=max_results)


async def gmail_read(message_id: str) -> dict[str, Any]:
    from app.gmail import read_email
    return await read_email(message_id=message_id)


async def gmail_send(to: str, subject: str, body: str) -> dict[str, Any]:
    from app.gmail import send_email
    result = await send_email(to=to, subject=subject, body=body)
    if result.get("ok"):
        try:
            from app.life_log import log_entry
            log_entry("email_sent", f"Email to {to}", subject, {"to": to, "subject": subject})
        except Exception:
            pass
    return result


async def gmail_draft(to: str, subject: str, body: str) -> dict[str, Any]:
    from app.gmail import draft_email
    return await draft_email(to=to, subject=subject, body=body)


async def gmail_search(query: str) -> dict[str, Any]:
    from app.gmail import search_email
    return await search_email(query=query)


# ── Calendar wrappers ──────────────────────────────────────────────────────


async def calendar_events(days_ahead: int = 7) -> dict[str, Any]:
    from app.gcal import list_events
    return await list_events(days_ahead=days_ahead)


async def calendar_create(
    title: str,
    start_datetime: str,
    end_datetime: str,
    description: str = "",
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    from app.gcal import create_event
    result = await create_event(
        title=title,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        description=description,
        attendees=attendees,
    )
    if result.get("ok"):
        try:
            from app.life_log import log_entry
            log_entry("meeting_scheduled", title, f"Start: {start_datetime}", {"attendees": attendees or []})
        except Exception:
            pass
    return result


async def calendar_free_slots(duration_minutes: int = 60, days_ahead: int = 7) -> dict[str, Any]:
    from app.gcal import find_free_slot
    return await find_free_slot(duration_minutes=duration_minutes, days_ahead=days_ahead)


# ── Habits ─────────────────────────────────────────────────────────────────


async def habit_status() -> dict[str, Any]:
    from app.habits import get_today_status
    habits = get_today_status()
    done = sum(1 for h in habits if h.get("done_today"))
    return {"tool": "habit_status", "ok": True, "result": {"habits": habits, "done": done, "total": len(habits)}}


async def habit_log(name: str, note: str = "") -> dict[str, Any]:
    from app.habits import log_habit
    result = log_habit(name, note)
    if not result.get("ok", True) and "error" in result:
        return {"tool": "habit_log", "ok": False, "error": result["error"]}
    return {"tool": "habit_log", "ok": True, "result": result}


async def habit_create(name: str, description: str = "", frequency: str = "daily") -> dict[str, Any]:
    from app.habits import create_habit
    habit = create_habit(name, description, frequency)
    return {"tool": "habit_create", "ok": True, "result": habit}


# ── News digest ─────────────────────────────────────────────────────────────


async def news_digest(limit_per_feed: int = 3) -> dict[str, Any]:
    from app.news import get_digest
    digest = get_digest(limit_per_feed=limit_per_feed)
    return {"tool": "news_digest", "ok": True, "result": digest}


# ── Clipboard ───────────────────────────────────────────────────────────────


async def clipboard_save(content: str, tags: str = "") -> dict[str, Any]:
    from app.clipboard import save_clip
    clip = save_clip(content, tags)
    return {"tool": "clipboard_save", "ok": True, "result": clip}


async def clipboard_search(query: str) -> dict[str, Any]:
    from app.clipboard import search_clips
    clips = search_clips(query)
    return {"tool": "clipboard_search", "ok": True, "result": clips}


# ── Goal planner ────────────────────────────────────────────────────────────


async def plan_goal(goal: str, auto_create: bool = False) -> dict[str, Any]:
    from app.planner import decompose_goal
    result = decompose_goal(goal, auto_create=auto_create)
    ok = "error" not in result
    return {"tool": "plan_goal", "ok": ok, "result": result}


# ── Pomodoro timer ──────────────────────────────────────────────────────────


async def pomodoro_start(label: str = "Focus session", duration_minutes: int = 25) -> dict[str, Any]:
    from app.pomodoro import start_timer
    result = start_timer(label, duration_minutes)
    return {"tool": "pomodoro_start", "ok": True, "result": result}


async def pomodoro_stop(completed: bool = True) -> dict[str, Any]:
    from app.pomodoro import stop_timer
    result = stop_timer(completed)
    return {"tool": "pomodoro_stop", "ok": result.get("ok", False), "result": result}


async def pomodoro_status() -> dict[str, Any]:
    from app.pomodoro import get_status
    return {"tool": "pomodoro_status", "ok": True, "result": get_status()}


# ── System stats (psutil) ──────────────────────────────────────────────────


async def system_stats() -> dict[str, Any]:
    import psutil
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "tool": "system_stats",
        "ok": True,
        "result": {
            "cpu_percent": cpu,
            "ram_used_gb": round(mem.used / 1e9, 2),
            "ram_total_gb": round(mem.total / 1e9, 2),
            "ram_percent": mem.percent,
            "disk_used_gb": round(disk.used / 1e9, 2),
            "disk_total_gb": round(disk.total / 1e9, 2),
            "disk_percent": disk.percent,
        },
    }


# ── Web scraping ───────────────────────────────────────────────────────────


async def web_scrape(url: str) -> dict[str, Any]:
    """Fetch a URL and extract its readable text content."""
    if not url.startswith(("http://", "https://")):
        return {"tool": "web_scrape", "ok": False, "error": "URL must start with http:// or https://"}
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"},
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        return {"tool": "web_scrape", "ok": False, "error": str(exc), "url": url}

    content = response.text
    # Strip scripts, styles, and comments
    content = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    # Strip all remaining tags
    text = _strip_tags(content)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()

    return {
        "tool": "web_scrape",
        "ok": True,
        "url": url,
        "result": text[:5000],
        "total_chars": len(text),
    }


# ── GitHub expanded ───────────────────────────────────────────────────────


async def github_list_prs(repo: str, state: str = "open") -> dict[str, Any]:
    from app.github import list_pull_requests
    return await list_pull_requests(repo, state)


async def github_pr_review(repo: str, pr_number: int) -> dict[str, Any]:
    from app.github import get_pr_review
    return await get_pr_review(repo, pr_number)


async def github_recent_commits(repo: str, limit: int = 5) -> dict[str, Any]:
    from app.github import list_recent_commits
    return await list_recent_commits(repo, limit)


async def github_repo_stats(repo: str) -> dict[str, Any]:
    from app.github import get_repo_stats
    return await get_repo_stats(repo)


async def github_commit_file(
    repo: str, path: str, content: str, message: str, branch: str = "main"
) -> dict[str, Any]:
    from app.github import commit_file
    return await commit_file(repo, path, content, message, branch)


# ── Spotify ────────────────────────────────────────────────────────────────


async def spotify_current() -> dict[str, Any]:
    from app.spotify import get_current_track
    return await get_current_track()


async def spotify_toggle() -> dict[str, Any]:
    from app.spotify import spotify_play_pause
    return await spotify_play_pause()


async def spotify_skip_next() -> dict[str, Any]:
    from app.spotify import spotify_next
    return await spotify_next()


async def spotify_skip_prev() -> dict[str, Any]:
    from app.spotify import spotify_prev
    return await spotify_prev()


async def spotify_volume(volume_pct: int) -> dict[str, Any]:
    from app.spotify import spotify_set_volume
    return await spotify_set_volume(volume_pct)


async def spotify_play(query: str) -> dict[str, Any]:
    from app.spotify import spotify_search_play
    return await spotify_search_play(query)


async def spotify_play_for_mode(mode: str) -> dict[str, Any]:
    from app.spotify import spotify_mode_play
    return await spotify_mode_play(mode)


# ── Notion ─────────────────────────────────────────────────────────────────


async def notion_search(query: str) -> dict[str, Any]:
    from app.notion import search_notion
    return await search_notion(query)


async def notion_page(page_id: str) -> dict[str, Any]:
    from app.notion import get_notion_page
    return await get_notion_page(page_id)


async def notion_sync_push(database_id: str) -> dict[str, Any]:
    from app.notion import sync_notes_to_notion
    return await sync_notes_to_notion(database_id)


# ── WhatsApp ───────────────────────────────────────────────────────────────


async def whatsapp_status() -> dict[str, Any]:
    from app.whatsapp_client import wa_status
    return await wa_status()


async def whatsapp_messages(limit: int = 20) -> dict[str, Any]:
    from app.whatsapp_client import wa_messages
    return await wa_messages(limit)


async def whatsapp_contacts(query: str = "") -> dict[str, Any]:
    from app.whatsapp_client import wa_contacts
    return await wa_contacts(query)


async def whatsapp_search_contact(name: str) -> dict[str, Any]:
    from app.whatsapp_client import wa_search_contact
    return await wa_search_contact(name)


async def whatsapp_conversation(contact: str) -> dict[str, Any]:
    from app.whatsapp_client import wa_conversation
    return await wa_conversation(contact)


async def whatsapp_send(to: str, text: str) -> dict[str, Any]:
    from app.whatsapp_client import wa_send
    return await wa_send(to, text)


# ── System alerts ──────────────────────────────────────────────────────────


async def system_alerts(limit: int = 20) -> dict[str, Any]:
    from app.system_alert import get_alerts
    return {"tool": "system_alerts", "ok": True, "result": get_alerts(limit)}


# ── Contacts ───────────────────────────────────────────────────────────────


async def contacts_search(query: str) -> dict[str, Any]:
    from app.contacts import find_contacts
    results = find_contacts(query)
    return {"tool": "contacts_search", "ok": True, "result": results}


async def contacts_list() -> dict[str, Any]:
    from app.contacts import list_contacts
    return {"tool": "contacts_list", "ok": True, "result": list_contacts()}


async def contact_save_phone(name: str, phone: str) -> dict[str, Any]:
    from app.contacts import find_contacts, _normalize_phone
    from app.db import get_db
    matches = find_contacts(name, limit=1)
    norm = _normalize_phone(phone)
    if not norm:
        return {"tool": "contact_save_phone", "ok": False, "error": "invalid phone number"}
    if matches:
        with get_db() as conn:
            conn.execute(
                "UPDATE contacts SET phone=? WHERE lower(name) LIKE ?",
                (norm, f"%{name.lower()}%"),
            )
        return {"tool": "contact_save_phone", "ok": True, "name": matches[0]["name"], "phone": norm}
    # Create a minimal contact with just name + phone (email placeholder)
    placeholder_email = f"{name.lower().replace(' ', '.')}@whatsapp.local"
    from app.contacts import upsert_contact
    upsert_contact(name, placeholder_email, source="manual", phone=norm)
    return {"tool": "contact_save_phone", "ok": True, "name": name, "phone": norm, "created": True}


# ── Registry ────────────────────────────────────────────────────────────────

ToolFn = Callable[..., Awaitable[dict[str, Any]]]

REGISTRY: dict[str, ToolFn] = {
    "get_current_time": get_current_time,
    "calculator": calculator,
    "get_weather": get_weather,
    "web_search": web_search,
    "news_topic": news_topic,
    "run_system_command": run_system_command,
    "get_open_issues": get_open_issues,
    "create_issue": create_issue,
    # Gmail
    "gmail_inbox": gmail_inbox,
    "gmail_read": gmail_read,
    "gmail_send": gmail_send,
    "gmail_draft": gmail_draft,
    "gmail_search": gmail_search,
    # Calendar
    "calendar_events": calendar_events,
    "calendar_create": calendar_create,
    "calendar_free_slots": calendar_free_slots,
    # Web scraping
    "web_scrape": web_scrape,
    # Habits
    "habit_status": habit_status,
    "habit_log": habit_log,
    "habit_create": habit_create,
    # News
    "news_digest": news_digest,
    # Clipboard
    "clipboard_save": clipboard_save,
    "clipboard_search": clipboard_search,
    # Planner
    "plan_goal": plan_goal,
    # Pomodoro
    "pomodoro_start": pomodoro_start,
    "pomodoro_stop": pomodoro_stop,
    "pomodoro_status": pomodoro_status,
    # System
    "system_stats": system_stats,
    # GitHub expanded
    "github_list_prs": github_list_prs,
    "github_pr_review": github_pr_review,
    "github_recent_commits": github_recent_commits,
    "github_repo_stats": github_repo_stats,
    "github_commit_file": github_commit_file,
    # Spotify
    "spotify_current": spotify_current,
    "spotify_toggle": spotify_toggle,
    "spotify_skip_next": spotify_skip_next,
    "spotify_skip_prev": spotify_skip_prev,
    "spotify_volume": spotify_volume,
    "spotify_play": spotify_play,
    "spotify_play_for_mode": spotify_play_for_mode,
    # Notion
    "notion_search": notion_search,
    "notion_page": notion_page,
    "notion_sync_push": notion_sync_push,
    # WhatsApp
    "whatsapp_status": whatsapp_status,
    "whatsapp_messages": whatsapp_messages,
    "whatsapp_contacts": whatsapp_contacts,
    "whatsapp_search_contact": whatsapp_search_contact,
    "whatsapp_conversation": whatsapp_conversation,
    "whatsapp_send": whatsapp_send,
    # System alerts
    "system_alerts": system_alerts,
    # Contacts
    "contacts_search": contacts_search,
    "contacts_list": contacts_list,
    "contact_save_phone": contact_save_phone,
}


async def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = REGISTRY.get(name)
    if fn is None:
        return {"tool": name, "ok": False, "error": "unknown tool"}
    try:
        return await fn(**args)
    except TypeError as exc:
        return {"tool": name, "ok": False, "error": f"bad args: {exc}"}
    except Exception as exc:
        log.exception("tool %s crashed", name)
        return {"tool": name, "ok": False, "error": str(exc)}
