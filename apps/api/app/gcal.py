from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger("veronica.gcal")


def _normalize_dt(dt_str: str) -> str:
    """Ensure datetime string has seconds — Google Calendar API requires HH:MM:SS."""
    t = dt_str.strip()
    if "T" in t and t.count(":") == 1:
        t += ":00"
    return t


def _parse_gdt(dt_str: str) -> datetime:
    """Parse Google's RFC3339 datetime strings, including 'Z' suffix (Python <3.11 safe)."""
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

APP_TZ = "Asia/Kolkata"
WORK_START = 9   # 9 AM
WORK_END = 18    # 6 PM


def _get_service():
    try:
        from google.oauth2.credentials import Credentials  # type: ignore[import]
        from googleapiclient.discovery import build  # type: ignore[import]
        from app.oauth_store import load_oauth_token

        token_json = load_oauth_token("google")
        if not token_json:
            return None
        creds = Credentials.from_authorized_user_info(json.loads(token_json), CALENDAR_SCOPES)
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as exc:
        log.warning("Failed to build Calendar service: %s", exc)
        return None


async def list_events(days_ahead: int = 7) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"tool": "list_events", "ok": False, "error": "Google Calendar not connected"}
    try:
        tz = ZoneInfo(APP_TZ)
        now = datetime.now(tz)
        # Start from beginning of today so earlier events are visible
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now + timedelta(days=days_ahead)
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=today_start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=20,
            )
            .execute()
        )
        events = []
        for evt in result.get("items", []):
            start = evt.get("start", {})
            end_dt = evt.get("end", {})
            events.append(
                {
                    "id": evt.get("id"),
                    "title": evt.get("summary", "Untitled"),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end_dt.get("dateTime") or end_dt.get("date"),
                    "description": evt.get("description", ""),
                    "attendees": [a.get("email") for a in evt.get("attendees", [])],
                    "location": evt.get("location", ""),
                    "meet_link": evt.get("hangoutLink", ""),
                    "all_day": "date" in start,
                }
            )
        try:
            from app.contacts import ingest_calendar_attendees
            for evt in events:
                if evt.get("attendees"):
                    ingest_calendar_attendees(
                        [{"email": e, "displayName": ""} for e in evt["attendees"]]
                    )
        except Exception:
            pass
        return {"tool": "list_events", "ok": True, "result": events}
    except Exception as exc:
        return {"tool": "list_events", "ok": False, "error": str(exc)}


async def create_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    description: str = "",
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    import uuid as _uuid
    from googleapiclient.errors import HttpError as _HttpError  # type: ignore[import]

    service = _get_service()
    if not service:
        return {"tool": "create_event", "ok": False, "error": "Google Calendar not connected"}
    try:
        start_datetime = _normalize_dt(start_datetime)
        end_datetime = _normalize_dt(end_datetime)
        # Guard: if end <= start, default to 1-hour event
        _past_warning = ""
        try:
            from datetime import datetime as _dt
            _tz = ZoneInfo(APP_TZ)
            _now = _dt.now(_tz)
            _s = _dt.fromisoformat(start_datetime.replace("Z", "+00:00"))
            _e = _dt.fromisoformat(end_datetime.replace("Z", "+00:00"))
            if _e <= _s:
                end_datetime = (_s + timedelta(hours=1)).isoformat()
                _e = _dt.fromisoformat(end_datetime.replace("Z", "+00:00"))
            if _s < _now:
                _past_warning = " (Note: this event is in the past)"
        except Exception:
            pass
        body: dict[str, Any] = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_datetime, "timeZone": APP_TZ},
            "end": {"dateTime": end_datetime, "timeZone": APP_TZ},
            "conferenceData": {
                "createRequest": {
                    "requestId": str(_uuid.uuid4()),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        if attendees:
            body["attendees"] = [{"email": a.strip()} for a in attendees if a.strip()]

        # Try with Google Meet link first; fall back without it for personal accounts
        try:
            result = (
                service.events()
                .insert(
                    calendarId="primary",
                    body=body,
                    conferenceDataVersion=1,
                    sendUpdates="all",
                )
                .execute()
            )
        except _HttpError as http_exc:
            if http_exc.resp.status == 400:
                log.warning("conferenceData rejected (likely personal account) — retrying without Meet link")
                body.pop("conferenceData", None)
                result = (
                    service.events()
                    .insert(calendarId="primary", body=body, sendUpdates="all")
                    .execute()
                )
            else:
                raise

        try:
            from app.contacts import ingest_calendar_attendees
            if attendees:
                ingest_calendar_attendees([{"email": a, "displayName": ""} for a in attendees])
        except Exception:
            pass
        return {
            "tool": "create_event",
            "ok": True,
            "past_warning": _past_warning,
            "result": {
                "id": result.get("id"),
                "title": title,
                "start": start_datetime,
                "end": end_datetime,
                "meet_link": result.get("hangoutLink", ""),
                "html_link": result.get("htmlLink", ""),
            },
        }
    except Exception as exc:
        return {"tool": "create_event", "ok": False, "error": str(exc)}


async def find_free_slot(duration_minutes: int = 60, days_ahead: int = 7) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"tool": "find_free_slot", "ok": False, "error": "Google Calendar not connected"}
    try:
        tz = ZoneInfo(APP_TZ)
        now = datetime.now(tz)
        window_end = now + timedelta(days=days_ahead)

        freebusy = (
            service.freebusy()
            .query(
                body={
                    "timeMin": now.isoformat(),
                    "timeMax": window_end.isoformat(),
                    "items": [{"id": "primary"}],
                }
            )
            .execute()
        )
        busy_slots = freebusy.get("calendars", {}).get("primary", {}).get("busy", [])

        # Walk working hours in 30-min steps
        check = now.replace(hour=WORK_START, minute=0, second=0, microsecond=0)
        if check < now:
            check += timedelta(days=1)

        free: list[dict[str, str]] = []
        iterations = 0
        while len(free) < 5 and iterations < days_ahead * 20:
            iterations += 1
            slot_end = check + timedelta(minutes=duration_minutes)

            if check.hour >= WORK_END or slot_end.hour > WORK_END:
                check = (check + timedelta(days=1)).replace(hour=WORK_START, minute=0, second=0)
                continue

            overlaps = any(
                check < _parse_gdt(b["end"])
                and slot_end > _parse_gdt(b["start"])
                for b in busy_slots
            )
            if not overlaps:
                free.append(
                    {
                        "start": check.isoformat(),
                        "end": slot_end.isoformat(),
                        "label": check.strftime("%A, %b %d at %I:%M %p IST"),
                    }
                )
            check += timedelta(minutes=30)

        return {
            "tool": "find_free_slot",
            "ok": True,
            "duration_minutes": duration_minutes,
            "result": free,
        }
    except Exception as exc:
        return {"tool": "find_free_slot", "ok": False, "error": str(exc)}
