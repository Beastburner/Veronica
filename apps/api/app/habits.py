from __future__ import annotations

"""
habits.py — Full habit tracker module for Veronica AI assistant.

Tables used:
    habits(id, name, description, frequency, color, archived, created_at)
    habit_logs(id, habit_id, logged_at, note, created_at)

frequency: "daily" | "weekly"
color: hex string like "#22d3ee"
archived: 0 or 1
"""

from datetime import date, timedelta
from typing import Any

from app.db import get_db, utcnow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_habit(
    name: str,
    description: str = "",
    frequency: str = "daily",
    color: str = "#22d3ee",
) -> dict[str, Any]:
    """Create a new habit and return the created row as a dict."""
    now = utcnow()
    with get_db() as db:
        cur = db.execute(
            """
            INSERT INTO habits (name, description, frequency, color, archived, created_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (name, description, frequency, color, now),
        )
        db.commit()
        habit_id = cur.lastrowid
        row = db.execute("SELECT * FROM habits WHERE id = ?", (habit_id,)).fetchone()
    return _row_to_dict(row)


def list_habits(include_archived: bool = False) -> list[dict[str, Any]]:
    """Return all habits. Excludes archived ones unless include_archived=True."""
    with get_db() as db:
        if include_archived:
            rows = db.execute("SELECT * FROM habits ORDER BY created_at ASC").fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM habits WHERE archived = 0 ORDER BY created_at ASC"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def archive_habit(habit_id: int) -> bool:
    """Mark a habit as archived. Returns True if a row was updated."""
    with get_db() as db:
        cur = db.execute(
            "UPDATE habits SET archived = 1 WHERE id = ?", (habit_id,)
        )
        db.commit()
    return cur.rowcount > 0


def log_habit(habit_id_or_name: int | str, note: str = "") -> dict[str, Any]:
    """
    Log a habit completion by ID (int) or partial name match (str).
    Returns the created log row dict, or {ok: False, error: str} on failure.
    """
    with get_db() as db:
        # Resolve habit
        if isinstance(habit_id_or_name, int):
            habit = db.execute(
                "SELECT * FROM habits WHERE id = ?", (habit_id_or_name,)
            ).fetchone()
        else:
            habit = db.execute(
                "SELECT * FROM habits WHERE lower(name) LIKE lower(?)",
                (f"%{habit_id_or_name}%",),
            ).fetchone()

        if habit is None:
            return {"ok": False, "error": f"Habit not found: {habit_id_or_name!r}"}

        habit_id = habit["id"]
        now = utcnow()
        # logged_at stores the date portion so streak calculation works
        logged_at = _today_str()

        cur = db.execute(
            """
            INSERT INTO habit_logs (habit_id, logged_at, note, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (habit_id, logged_at, note, now),
        )
        db.commit()
        log_id = cur.lastrowid
        row = db.execute(
            "SELECT * FROM habit_logs WHERE id = ?", (log_id,)
        ).fetchone()
    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------

def get_streak(habit_id: int) -> int:
    """
    Count consecutive calendar days (backwards from today) that have at least
    one log entry. Stops at the first missing day.
    """
    with get_db() as db:
        rows = db.execute(
            """
            SELECT DISTINCT logged_at
            FROM habit_logs
            WHERE habit_id = ?
            ORDER BY logged_at DESC
            """,
            (habit_id,),
        ).fetchall()

    logged_dates: set[str] = {r["logged_at"] for r in rows}

    streak = 0
    current = date.today()
    while current.isoformat() in logged_dates:
        streak += 1
        current -= timedelta(days=1)
    return streak


# ---------------------------------------------------------------------------
# Today's status
# ---------------------------------------------------------------------------

def get_today_status() -> list[dict[str, Any]]:
    """
    Return all active habits with two extra fields:
      done_today (bool): True if at least one log exists for today
      streak (int): current consecutive-day streak
    """
    today = _today_str()
    with get_db() as db:
        habits = db.execute(
            "SELECT * FROM habits WHERE archived = 0 ORDER BY created_at ASC"
        ).fetchall()

        # Fetch all of today's habit_ids in one query
        logged_today = {
            r["habit_id"]
            for r in db.execute(
                "SELECT DISTINCT habit_id FROM habit_logs WHERE logged_at = ?",
                (today,),
            ).fetchall()
        }

    result: list[dict[str, Any]] = []
    for habit in habits:
        d = _row_to_dict(habit)
        d["done_today"] = habit["id"] in logged_today
        d["streak"] = get_streak(habit["id"])
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def get_habit_logs(habit_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """Return the most recent `limit` log entries for a habit."""
    with get_db() as db:
        rows = db.execute(
            """
            SELECT * FROM habit_logs
            WHERE habit_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (habit_id, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
