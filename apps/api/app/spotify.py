from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Any

import httpx

from app.oauth_store import load_oauth_token, save_oauth_token

SPOTIFY_SCOPES = (
    "user-read-playback-state user-modify-playback-state "
    "user-read-currently-playing streaming playlist-read-private"
)

MODE_PLAYLISTS: dict[str, str | None] = {
    "FRIDAY": "spotify:playlist:37i9dQZF1DWZZbwlv3Vmtr",
    "JARVIS": "spotify:playlist:37i9dQZF1DXdwTUxmGKrdN",
    "SENTINEL": None,
    "VERONICA": "spotify:playlist:37i9dQZF1DX4WYpdgoIcn6",
}

_BASE = "https://api.spotify.com/v1"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
HTTP_TIMEOUT = 8.0


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _load_token() -> dict | None:
    raw = load_oauth_token("spotify")
    if not raw:
        return None
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None


async def _get_access_token() -> str | None:
    token = _load_token()
    if not token:
        return None

    if time.time() >= token.get("expires_at", 0) - 60:
        client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        refresh_token = token.get("refresh_token")
        if not refresh_token or not client_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                r = await client.post(
                    _TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                r.raise_for_status()
                data = r.json()
            token["access_token"] = data["access_token"]
            token["expires_at"] = time.time() + data.get("expires_in", 3600)
            if data.get("refresh_token"):
                token["refresh_token"] = data["refresh_token"]
            save_oauth_token("spotify", json.dumps(token))
        except Exception:
            return None

    return token.get("access_token")


def _not_connected() -> dict[str, Any]:
    return {"ok": False, "error": "Spotify not connected — visit /oauth/spotify/start"}


async def get_current_track() -> dict[str, Any]:
    access_token = await _get_access_token()
    if not access_token:
        return {**_not_connected(), "tool": "get_current_track"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(
                f"{_BASE}/me/player/currently-playing",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code == 204:
                return {"tool": "get_current_track", "ok": True, "result": {"playing": False, "track": None}}
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        return {"tool": "get_current_track", "ok": False, "error": str(exc)}

    item = data.get("item") or {}
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    album = (item.get("album") or {}).get("name", "")
    return {
        "tool": "get_current_track",
        "ok": True,
        "result": {
            "playing": data.get("is_playing", False),
            "track": item.get("name"),
            "artist": artists,
            "album": album,
            "progress_ms": data.get("progress_ms"),
            "duration_ms": item.get("duration_ms"),
            "volume": (data.get("device") or {}).get("volume_percent"),
        },
    }


async def spotify_play_pause() -> dict[str, Any]:
    access_token = await _get_access_token()
    if not access_token:
        return {**_not_connected(), "tool": "spotify_play_pause"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            state_r = await client.get(f"{_BASE}/me/player", headers=headers)
            is_playing = False
            if state_r.status_code == 200:
                is_playing = (state_r.json() or {}).get("is_playing", False)

            if is_playing:
                r = await client.put(f"{_BASE}/me/player/pause", headers=headers)
            else:
                r = await client.put(
                    f"{_BASE}/me/player/play",
                    headers={**headers, "Content-Type": "application/json"},
                    content=b"{}",
                )
    except httpx.HTTPError as exc:
        return {"tool": "spotify_play_pause", "ok": False, "error": str(exc)}

    return {"tool": "spotify_play_pause", "ok": True, "result": {"action": "paused" if is_playing else "playing"}}


async def spotify_next() -> dict[str, Any]:
    access_token = await _get_access_token()
    if not access_token:
        return {**_not_connected(), "tool": "spotify_next"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(
                f"{_BASE}/me/player/next",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as exc:
        return {"tool": "spotify_next", "ok": False, "error": str(exc)}

    return {"tool": "spotify_next", "ok": True, "result": {"action": "skipped_next"}}


async def spotify_prev() -> dict[str, Any]:
    access_token = await _get_access_token()
    if not access_token:
        return {**_not_connected(), "tool": "spotify_prev"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(
                f"{_BASE}/me/player/previous",
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as exc:
        return {"tool": "spotify_prev", "ok": False, "error": str(exc)}

    return {"tool": "spotify_prev", "ok": True, "result": {"action": "skipped_prev"}}


async def spotify_set_volume(volume_pct: int) -> dict[str, Any]:
    access_token = await _get_access_token()
    if not access_token:
        return {**_not_connected(), "tool": "spotify_set_volume"}

    vol = max(0, min(100, volume_pct))
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.put(
                f"{_BASE}/me/player/volume",
                params={"volume_percent": vol},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as exc:
        return {"tool": "spotify_set_volume", "ok": False, "error": str(exc)}

    return {"tool": "spotify_set_volume", "ok": True, "result": {"volume_pct": vol}}


async def spotify_search_play(query: str) -> dict[str, Any]:
    access_token = await _get_access_token()
    if not access_token:
        return {**_not_connected(), "tool": "spotify_search_play"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            search_r = await client.get(
                f"{_BASE}/search",
                params={"q": query, "type": "track", "limit": 1},
                headers=headers,
            )
            search_r.raise_for_status()
            search_data = search_r.json()
            items = (search_data.get("tracks") or {}).get("items") or []
            if not items:
                return {"tool": "spotify_search_play", "ok": False, "error": f"No track found for: {query}"}
            uri = items[0]["uri"]
            track_name = items[0]["name"]
            artist_name = ", ".join(a["name"] for a in items[0].get("artists", []))
            play_r = await client.put(
                f"{_BASE}/me/player/play",
                json={"uris": [uri]},
                headers={**headers, "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        return {"tool": "spotify_search_play", "ok": False, "error": str(exc)}

    return {
        "tool": "spotify_search_play",
        "ok": True,
        "result": {"playing": track_name, "artist": artist_name, "uri": uri},
    }


async def spotify_mode_play(mode: str) -> dict[str, Any]:
    access_token = await _get_access_token()
    if not access_token:
        return {**_not_connected(), "tool": "spotify_mode_play"}

    mode_upper = mode.upper()
    if mode_upper not in MODE_PLAYLISTS:
        return {
            "tool": "spotify_mode_play",
            "ok": False,
            "error": f"Unknown mode '{mode}'. Valid: {list(MODE_PLAYLISTS.keys())}",
        }

    uri = MODE_PLAYLISTS[mode_upper]
    if uri is None:
        return await spotify_play_pause() | {"tool": "spotify_mode_play"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.put(
                f"{_BASE}/me/player/play",
                json={"context_uri": uri},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        return {"tool": "spotify_mode_play", "ok": False, "error": str(exc)}

    return {"tool": "spotify_mode_play", "ok": True, "result": {"mode": mode_upper, "playlist": uri}}
