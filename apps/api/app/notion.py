from __future__ import annotations

import os
from typing import Any

import httpx

NOTION_VERSION = "2022-06-28"
_BASE = "https://api.notion.com/v1"
HTTP_TIMEOUT = 10.0


def _notion_headers() -> dict[str, str]:
    api_key = os.getenv("NOTION_API_KEY", "")
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _extract_title(page: dict) -> str:
    props = page.get("properties") or {}
    for key in ("Name", "Title", "title"):
        prop = props.get(key)
        if not prop:
            continue
        rich = prop.get("title") or prop.get("rich_text") or []
        text = "".join(t.get("plain_text", "") for t in rich)
        if text:
            return text
    return "(untitled)"


def _blocks_to_text(blocks: list[dict]) -> str:
    parts: list[str] = []
    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype) or {}
        rich = content.get("rich_text") or []
        text = "".join(t.get("plain_text", "") for t in rich)
        if text:
            parts.append(text)
    return "\n".join(parts)


async def search_notion(query: str) -> dict[str, Any]:
    api_key = os.getenv("NOTION_API_KEY", "")
    if not api_key:
        return {"tool": "search_notion", "ok": False, "error": "NOTION_API_KEY not configured"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=_notion_headers()) as client:
            r = await client.post(f"{_BASE}/search", json={"query": query, "page_size": 10})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        return {"tool": "search_notion", "ok": False, "error": str(exc)}

    results = []
    for obj in data.get("results") or []:
        obj_type = obj.get("object")
        title = _extract_title(obj) if obj_type == "page" else obj.get("title") or "(untitled)"
        url = obj.get("url", "")
        last_edited = obj.get("last_edited_time", "")
        results.append({
            "id": obj.get("id"),
            "title": title,
            "url": url,
            "type": obj_type,
            "last_edited": last_edited,
        })

    return {"tool": "search_notion", "ok": True, "query": query, "result": results}


async def get_notion_page(page_id: str) -> dict[str, Any]:
    api_key = os.getenv("NOTION_API_KEY", "")
    if not api_key:
        return {"tool": "get_notion_page", "ok": False, "error": "NOTION_API_KEY not configured"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=_notion_headers()) as client:
            page_r = await client.get(f"{_BASE}/pages/{page_id}")
            page_r.raise_for_status()
            page = page_r.json()

            blocks_r = await client.get(f"{_BASE}/blocks/{page_id}/children")
            blocks_r.raise_for_status()
            blocks_data = blocks_r.json()
    except httpx.HTTPError as exc:
        return {"tool": "get_notion_page", "ok": False, "error": str(exc)}

    title = _extract_title(page)
    blocks = blocks_data.get("results") or []
    content = _blocks_to_text(blocks)

    return {
        "tool": "get_notion_page",
        "ok": True,
        "result": {
            "id": page.get("id"),
            "title": title,
            "url": page.get("url"),
            "content": content[:4000],
        },
    }


async def sync_notes_to_notion(database_id: str) -> dict[str, Any]:
    api_key = os.getenv("NOTION_API_KEY", "")
    if not api_key:
        return {"tool": "sync_notes_to_notion", "ok": False, "error": "NOTION_API_KEY not configured"}

    from app.storage import list_notes
    notes, _ = list_notes(limit=20)

    pushed = 0
    errors: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=_notion_headers()) as client:
            for note in notes:
                content = note.get("content", "")[:2000]
                title = content[:80] or "Note"
                payload = {
                    "parent": {"database_id": database_id},
                    "properties": {
                        "title": {
                            "title": [{"type": "text", "text": {"content": title}}]
                        }
                    },
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": content}}]
                            },
                        }
                    ],
                }
                try:
                    r = await client.post(f"{_BASE}/pages", json=payload)
                    r.raise_for_status()
                    pushed += 1
                except httpx.HTTPError as exc:
                    errors.append(f"note {note.get('id')}: {exc}")
    except httpx.HTTPError as exc:
        return {"tool": "sync_notes_to_notion", "ok": False, "error": str(exc)}

    return {
        "tool": "sync_notes_to_notion",
        "ok": True,
        "result": {"pushed": pushed, "errors": errors},
    }
