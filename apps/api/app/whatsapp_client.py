from __future__ import annotations

import os
import re
from typing import Any

import httpx

_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"
    "\U00002300-\U000023FF"
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(s: str) -> str:
    return _EMOJI_RE.sub("", s).strip()

HTTP_TIMEOUT = 6.0
HTTP_TIMEOUT_CONVERSATION = 20.0  # live WhatsApp fetch (getChats + fetchMessages) can take 10-15s


def _wa_base() -> str:
    return os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:3001")


def _unreachable_error() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "WhatsApp service not running — start apps/whatsapp with: node index.js",
    }


async def wa_status() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(f"{_wa_base()}/status")
            return r.json()
    except (httpx.ConnectError, OSError, Exception):
        return _unreachable_error()


async def wa_qr() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(f"{_wa_base()}/qr")
            return r.json()
    except (httpx.ConnectError, OSError, Exception):
        return _unreachable_error()


async def wa_messages(limit: int = 20) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(f"{_wa_base()}/messages", params={"limit": limit})
            return r.json()
    except (httpx.ConnectError, OSError, Exception):
        return _unreachable_error()


async def wa_contacts(query: str = "") -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            params = {"q": query} if query else {}
            r = await client.get(f"{_wa_base()}/contacts", params=params)
            return r.json()
    except (httpx.ConnectError, OSError, Exception):
        return _unreachable_error()


def _score_contact(contact_name: str, query_words: list[str]) -> int:
    """Score a contact name against query words (case-insensitive word overlap)."""
    cn = _strip_emoji(contact_name).lower()
    cn_words = cn.split()
    score = 0
    for qw in query_words:
        if qw in cn_words:        # exact word match
            score += 3
        elif any(cw.startswith(qw) for cw in cn_words):  # prefix match
            score += 2
        elif qw in cn:            # substring match
            score += 1
    return score


async def wa_search_contact(name: str) -> dict[str, Any]:
    """
    Search WhatsApp contacts by name with fuzzy word-level matching.
    Tries: full name → first word → each word → best scored result.
    """
    query_words = [w for w in _strip_emoji(name).lower().split() if len(w) > 1]

    # Collect candidates via progressively looser queries
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    async def _fetch(q: str) -> None:
        r = await wa_contacts(query=q)
        if not r.get("ok"):
            return
        for c in r.get("contacts") or []:
            cid = c.get("id", c.get("name", ""))
            if cid not in seen_ids:
                seen_ids.add(cid)
                candidates.append(c)

    # 1. Full name
    await _fetch(name)
    # 2. First word only (if multi-word and nothing found yet)
    if not candidates and len(query_words) > 1:
        await _fetch(query_words[0])
    # 3. Each remaining word
    if not candidates:
        for w in query_words[1:]:
            await _fetch(w)
            if candidates:
                break

    if not candidates:
        # Try group chats as fallback
        gr = await wa_groups(query=name)
        if gr.get("ok") and gr.get("groups"):
            words = [w for w in name.lower().split() if len(w) > 1]
            best = sorted(
                gr["groups"],
                key=lambda g: sum(1 for w in words if w in (g.get("name") or "").lower()),
                reverse=True,
            )
            if best:
                g = best[0]
                return {"ok": True, "contact": {
                    "name": g["name"], "number": "", "id": g["id"], "isGroup": True,
                }}
        return {"ok": False, "error": f'No WhatsApp contact or group found for "{name}"'}

    # Score all candidates and return the best with a number
    scored = sorted(
        ((c, _score_contact(c.get("name", ""), query_words)) for c in candidates),
        key=lambda x: x[1],
        reverse=True,
    )
    # Pick the highest-scoring contact that has a number
    for contact, _ in scored:
        if (contact.get("number") or "").strip():
            return {"ok": True, "contact": contact}

    # No candidate has a number — return best match anyway, caller handles it
    return {"ok": True, "contact": scored[0][0]}


async def wa_groups(query: str = "") -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            params = {"q": query} if query else {}
            r = await client.get(f"{_wa_base()}/groups", params=params)
            return r.json()
    except (httpx.ConnectError, OSError, Exception):
        return _unreachable_error()


async def wa_conversation(contact: str) -> dict[str, Any]:
    """Fetch messages to/from a specific contact (by name or number fragment)."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_CONVERSATION) as client:
            r = await client.get(f"{_wa_base()}/conversation", params={"q": contact})
            data = r.json()
            data.setdefault("ok", True)
            return data
    except (httpx.ConnectError, OSError, Exception):
        return _unreachable_error()


async def wa_send(to: str, text: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(f"{_wa_base()}/send", json={"to": to, "text": text})
            data = r.json()
            data.setdefault("ok", r.is_success)
            data["to"] = to
            return data
    except (httpx.ConnectError, OSError, Exception):
        return _unreachable_error()
