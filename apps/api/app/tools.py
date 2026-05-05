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

USER_AGENT = "VERONICA/0.3 (+https://localhost)"
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

    return {
        "tool": "web_search",
        "ok": True,
        "query": q,
        "result": results[:3] or [{"title": q, "snippet": "No results found.", "url": ""}],
    }


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


# ── Registry ────────────────────────────────────────────────────────────────

ToolFn = Callable[..., Awaitable[dict[str, Any]]]

REGISTRY: dict[str, ToolFn] = {
    "get_current_time": get_current_time,
    "calculator": calculator,
    "get_weather": get_weather,
    "web_search": web_search,
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
