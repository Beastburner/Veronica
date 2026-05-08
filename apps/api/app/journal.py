from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.db import get_db, utcnow

IST = ZoneInfo("Asia/Kolkata")


def _today_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def gather_day_data(date_str: str | None = None) -> dict[str, Any]:
    d = date_str or _today_ist()
    with get_db() as conn:
        life = conn.execute(
            "SELECT entry_type, title FROM life_log "
            "WHERE date(created_at) = ? AND entry_type != 'daily_journal' ORDER BY created_at",
            (d,),
        ).fetchall()

        tasks_done = conn.execute(
            "SELECT description, priority FROM tasks WHERE status = 'done' AND date(created_at) = ?",
            (d,),
        ).fetchall()

        habits = conn.execute(
            """
            SELECT h.name FROM habit_logs hl
            JOIN habits h ON h.id = hl.habit_id
            WHERE date(hl.logged_at) = ?
            """,
            (d,),
        ).fetchall()

        pomodoro = conn.execute(
            "SELECT label, duration_minutes, completed FROM pomodoro_sessions WHERE date(created_at) = ?",
            (d,),
        ).fetchall()

        notes = conn.execute(
            "SELECT content FROM notes WHERE date(created_at) = ?",
            (d,),
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
            parts.append(f"{len(data['notes'])} note(s) created")
        if data["life_log"]:
            events = [e["title"] for e in data["life_log"][:6]]
            parts.append("Activity: " + ", ".join(events))

        context = "\n".join(parts)

        text, _ = call_chat(
            [
                {
                    "role": "system",
                    "content": (
                        f"You are writing a short personal journal entry for {sender}. "
                        "Write in first person, casual and reflective tone. "
                        "2-4 sentences. Mention what got done, any standout moments, how the day felt overall. "
                        "No headers, no bullet points — just flowing prose."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Date: {d}\n\nToday's activity:\n{context}\n\nWrite the journal entry.",
                },
            ],
            temperature=0.78,
            max_tokens=160,
        )
        summary = (text or "A productive day worth remembering.").strip()

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
