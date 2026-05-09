from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.db import get_db, utcnow

IST = ZoneInfo("Asia/Kolkata")

# Life-log entry types that represent meaningful activity worth journaling.
# Excludes meta-events like note_created / task_created that pollute the summary.
_MEANINGFUL_LOG_TYPES = frozenset({
    "task_completed",
    "email_sent",
    "meeting_scheduled",
    "reminder_fired",
    "habit_logged",
    "oauth_connected",
    "life_entry",       # manual /life-log entries
})


def _today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _ist_day_utc_range(date_str: str) -> tuple[str, str]:
    """Return (start_utc_iso, end_utc_iso) covering the full IST calendar day."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    start_ist = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=IST)
    end_ist = start_ist + timedelta(days=1)
    return (
        start_ist.astimezone(timezone.utc).isoformat(),
        end_ist.astimezone(timezone.utc).isoformat(),
    )


def gather_day_data(date_str: str | None = None) -> dict[str, Any]:
    d = date_str or _today_ist()
    start_utc, end_utc = _ist_day_utc_range(d)

    with get_db() as conn:
        # Only pull meaningful life-log events — skip note_created / task_created spam
        life = conn.execute(
            "SELECT entry_type, title FROM life_log "
            "WHERE created_at >= ? AND created_at < ? "
            "AND entry_type != 'daily_journal' "
            f"AND entry_type IN ({','.join('?' * len(_MEANINGFUL_LOG_TYPES))}) "
            "ORDER BY created_at",
            (start_utc, end_utc, *_MEANINGFUL_LOG_TYPES),
        ).fetchall()

        tasks_done = conn.execute(
            "SELECT description, priority FROM tasks "
            "WHERE status = 'done' AND created_at >= ? AND created_at < ?",
            (start_utc, end_utc),
        ).fetchall()

        habits = conn.execute(
            """
            SELECT h.name FROM habit_logs hl
            JOIN habits h ON h.id = hl.habit_id
            WHERE hl.logged_at >= ? AND hl.logged_at < ?
            """,
            (start_utc, end_utc),
        ).fetchall()

        pomodoro = conn.execute(
            "SELECT label, duration_minutes, completed FROM pomodoro_sessions "
            "WHERE created_at >= ? AND created_at < ?",
            (start_utc, end_utc),
        ).fetchall()

        notes = conn.execute(
            "SELECT content FROM notes WHERE created_at >= ? AND created_at < ?",
            (start_utc, end_utc),
        ).fetchall()

    return {
        "date": d,
        "life_log": [dict(r) for r in life],
        "tasks_done": [dict(r) for r in tasks_done],
        "habits": [dict(r) for r in habits],
        "pomodoro": [dict(r) for r in pomodoro],
        "notes": [dict(r) for r in notes],
    }


def generate_journal_entry(date_str: str | None = None) -> dict[str, Any]:
    """Generate and persist a daily journal entry. Idempotent — skips if already exists."""
    d = date_str or _today_ist()

    existing = get_journal(d)
    if existing:
        return existing

    data = gather_day_data(d)

    has_data = any([
        data["life_log"], data["tasks_done"],
        data["habits"], data["pomodoro"], data["notes"],
    ])

    if not has_data:
        summary = "A quiet day — no activity was recorded."
    else:
        from app.config import settings
        from app.llm_client import call_chat

        sender = (settings.sender_name or "Parth").split()[0]
        parts: list[str] = []

        if data["habits"]:
            parts.append("Habits: " + ", ".join(h["name"] for h in data["habits"]))
        if data["tasks_done"]:
            parts.append("Tasks completed: " + ", ".join(t["description"] for t in data["tasks_done"]))
        if data["pomodoro"]:
            done = [p for p in data["pomodoro"] if p["completed"]]
            if done:
                mins = sum(p["duration_minutes"] for p in done)
                parts.append(f"Focus work: {len(done)} Pomodoro session(s), {mins} min total")
        if data["notes"]:
            # Only show note count + topics, not raw content — avoid polluting the journal
            # with test/admin notes from chat sessions
            parts.append(f"Notes saved: {len(data['notes'])} note(s)")
        if data["life_log"]:
            events = [e["title"] for e in data["life_log"][:6]]
            parts.append("Significant events: " + ", ".join(events))

        context = "\n".join(parts)

        text, _ = call_chat(
            [
                {
                    "role": "system",
                    "content": (
                        f"You are VERONICA writing a daily activity log for {sender}. "
                        "Style: sharp, factual, dry. No emotional padding. No 'how it felt'. "
                        "Focus on completed tasks, focus sessions, habits done, and significant events. "
                        "Notes saved count is metadata — do NOT speculate about note contents. "
                        "2-4 sentences max. First person. No headers, no bullets. "
                        "If only notes were saved and nothing else happened, say it was a light day. "
                        "Never invent or pad with vague reflections."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Date: {d}\n\nToday's activity:\n{context}\n\nWrite the log entry.",
                },
            ],
            temperature=0.5,
            max_tokens=160,
        )
        summary = (text or "Light day — minimal activity recorded.").strip()

    from app.life_log import log_entry
    entry = log_entry("daily_journal", f"Journal — {d}", summary, {"date": d})
    return {"date": d, "summary": summary, "id": entry["id"], "created_at": entry["created_at"]}


def get_journal(date_str: str | None = None) -> dict[str, Any] | None:
    d = date_str or _today_ist()
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, content, created_at FROM life_log "
            "WHERE entry_type = 'daily_journal' AND title = ? LIMIT 1",
            (f"Journal — {d}",),
        ).fetchone()
    if row:
        return {
            "date": d,
            "summary": row["content"],
            "id": row["id"],
            "created_at": row["created_at"],
        }
    return None


def list_journals(limit: int = 14) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, content, created_at FROM life_log "
            "WHERE entry_type = 'daily_journal' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "date": r["title"].replace("Journal — ", ""),
            "summary": r["content"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
