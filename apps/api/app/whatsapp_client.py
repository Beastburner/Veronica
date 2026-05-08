from __future__ import annotations

import os
from typing import Any

import httpx

HTTP_TIMEOUT = 6.0


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
