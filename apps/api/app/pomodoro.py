from __future__ import annotations

"""
pomodoro.py — Focus timer (Pomodoro technique) for Veronica AI assistant.

Uses in-memory singleton timer state + persistent session history in DB.

Table used:
    pomodoro_sessions(id, label, duration_minutes, completed, interrupted,
                      created_at, finished_at)
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Any

from app.db import get_db, utcnow


# ---------------------------------------------------------------------------
# In-memory singleton state
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {
    "active": False,
    "label": "",
    "start_time": 0.0,       # time.monotonic() value when started / last resumed
    "duration_seconds": 0,   # total target duration
    "paused_at": None,        # time.monotonic() value when paused, or None
    "elapsed_before_pause": 0.0,  # accumulated seconds before current pause
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _elapsed_seconds() -> float:
    """Return total elapsed seconds accounting for any accumulated pause time."""
    base = _state["elapsed_before_pause"]
    if _state["paused_at"] is not None:
        # Currently paused — don't count time since pause
        return base
    if _state["active"]:
        return base + (time.monotonic() - _state["start_time"])
    return base


def _iso_from_now(seconds: float) -> str:
    """Return an ISO 8601 datetime string `seconds` from now (UTC)."""
    future = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return future.isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_timer(
    label: str = "Focus session",
    duration_minutes: int = 25,
) -> dict[str, Any]:
    """
    Start a new Pomodoro timer (replaces any currently running one without
    saving it — call stop_timer() first if you want to persist the old session).

    Returns:
        {ok, label, duration_minutes, ends_at_iso}
    """
    duration_seconds = duration_minutes * 60
    _state["active"] = True
    _state["label"] = label
    _state["start_time"] = time.monotonic()
    _state["duration_seconds"] = duration_seconds
    _state["paused_at"] = None
    _state["elapsed_before_pause"] = 0.0

    return {
        "ok": True,
        "label": label,
        "duration_minutes": duration_minutes,
        "ends_at_iso": _iso_from_now(duration_seconds),
    }


def stop_timer(completed: bool = True) -> dict[str, Any]:
    """
    Stop the current timer and persist the session to the DB.

    Args:
        completed:  True if the session ran to completion, False if interrupted.

    Returns:
        A summary dict including the saved session row.
    """
    if not _state["active"]:
        return {"ok": False, "error": "No active timer to stop."}

    elapsed = _elapsed_seconds()
    duration_minutes = _state["duration_seconds"] // 60
    label = _state["label"]
    interrupted = not completed

    now = utcnow()

    with get_db() as db:
        cur = db.execute(
            """
            INSERT INTO pomodoro_sessions
                (label, duration_minutes, completed, interrupted, created_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (label, duration_minutes, int(completed), int(interrupted), now, now),
        )
        db.commit()
        session_id = cur.lastrowid
        row = db.execute(
            "SELECT * FROM pomodoro_sessions WHERE id = ?", (session_id,)
        ).fetchone()

    # Reset state
    _state["active"] = False
    _state["label"] = ""
    _state["start_time"] = 0.0
    _state["duration_seconds"] = 0
    _state["paused_at"] = None
    _state["elapsed_before_pause"] = 0.0

    return {
        "ok": True,
        "completed": completed,
        "interrupted": interrupted,
        "elapsed_seconds": int(elapsed),
        "session": _row_to_dict(row),
    }


def get_status() -> dict[str, Any]:
    """
    Return the current timer status.

    Returns:
        {active, label, elapsed_seconds, remaining_seconds, percent_done}

    When no timer is active, elapsed_seconds and remaining_seconds are both 0
    and percent_done is 0.
    """
    if not _state["active"]:
        return {
            "active": False,
            "label": "",
            "elapsed_seconds": 0,
            "remaining_seconds": 0,
            "percent_done": 0.0,
        }

    elapsed = _elapsed_seconds()
    duration = float(_state["duration_seconds"])
    remaining = max(0.0, duration - elapsed)
    percent = round((elapsed / duration) * 100, 1) if duration > 0 else 0.0

    return {
        "active": True,
        "label": _state["label"],
        "elapsed_seconds": int(elapsed),
        "remaining_seconds": int(remaining),
        "percent_done": percent,
    }


def get_history(limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent `limit` completed/interrupted Pomodoro sessions."""
    with get_db() as db:
        rows = db.execute(
            """
            SELECT * FROM pomodoro_sessions
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
