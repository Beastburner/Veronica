from __future__ import annotations

import re
import json
import math
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.db import get_db, utcnow
from app.llm_client import get_embedding

log = logging.getLogger("veronica.storage")

APP_TZ = "Asia/Kolkata"


def current_local_time() -> datetime:
    try:
        return datetime.now(ZoneInfo(APP_TZ))
    except Exception:
        return datetime.now()


def format_due_label(due_at: str | None) -> str | None:
    if not due_at:
        return None

    if due_at.startswith("daily:"):
        _, hh, mm = due_at.split(":")
        hour = int(hh)
        minute = int(mm)
        display = datetime(2000, 1, 1, hour, minute).strftime("%I:%M %p").lstrip("0")
        return f"Daily at {display} IST"

    if due_at.startswith("once:"):
        try:
            parsed = datetime.fromisoformat(due_at[5:])
            return f"Scheduled for {parsed.strftime('%I:%M %p IST on %B %d, %Y')}".replace(" 0", " ")
        except ValueError:
            return due_at

    return due_at


def create_note(content: str) -> dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, content, created_at
            FROM notes
            WHERE lower(trim(content)) = lower(trim(?))
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (content,),
        )
        existing = cursor.fetchone()
        if existing:
            return {"id": existing["id"], "content": existing["content"], "duplicate": True}

        emb = get_embedding(content)
        emb_str = json.dumps(emb) if emb else None
        cursor.execute(
            "INSERT INTO notes (content, embedding, created_at) VALUES (?, ?, ?)",
            (content, emb_str, utcnow()),
        )
        return {"id": cursor.lastrowid, "content": content}


def list_notes(skip: int = 0, limit: int = 50) -> tuple[list[dict[str, Any]], int]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM notes")
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT id, content, created_at
            FROM notes
            ORDER BY datetime(created_at) DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip),
        )
        items = [dict(row) for row in cursor.fetchall()]
        return items, total


def create_task(description: str, priority: str = "medium") -> dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, description, priority, status, created_at
            FROM tasks
            WHERE lower(trim(description)) = lower(trim(?)) AND status = 'pending'
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (description,),
        )
        existing = cursor.fetchone()
        if existing:
            return {**dict(existing), "duplicate": True}

        cursor.execute(
            "INSERT INTO tasks (description, priority, status, created_at) VALUES (?, ?, 'pending', ?)",
            (description, priority, utcnow()),
        )
        return {
            "id": cursor.lastrowid,
            "description": description,
            "priority": priority,
            "status": "pending",
        }


def list_tasks(skip: int = 0, limit: int = 50, status: str | None = None) -> tuple[list[dict[str, Any]], int]:
    with get_db() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE status = ?", (status,))
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                """
                SELECT id, description, priority, status, created_at
                FROM tasks
                WHERE status = ?
                ORDER BY CASE priority
                    WHEN 'high' THEN 3
                    WHEN 'medium' THEN 2
                    ELSE 1
                END DESC, datetime(created_at) DESC
                LIMIT ? OFFSET ?
                """,
                (status, limit, skip),
            )
        else:
            cursor.execute("SELECT COUNT(*) AS total FROM tasks")
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                """
                SELECT id, description, priority, status, created_at
                FROM tasks
                ORDER BY CASE priority
                    WHEN 'high' THEN 3
                    WHEN 'medium' THEN 2
                    ELSE 1
                END DESC, datetime(created_at) DESC
                LIMIT ? OFFSET ?
                """,
                (limit, skip),
            )
        items = [dict(row) for row in cursor.fetchall()]
        return items, total


def update_task_status(task_id: int, status: str) -> dict[str, Any] | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        cursor.execute(
            "SELECT id, description, priority, status, created_at FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def create_reminder(content: str, due_at: str | None = None) -> dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, content, due_at, status, created_at
            FROM reminders
            WHERE lower(trim(content)) = lower(trim(?)) AND status = 'pending'
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (content,),
        )
        existing = cursor.fetchone()
        if existing:
            existing_item = dict(existing)
            existing_due = existing_item.get("due_at")
            if due_at and existing_due != due_at:
                cursor.execute(
                    "UPDATE reminders SET due_at = ? WHERE id = ?",
                    (due_at, existing_item["id"]),
                )
                cursor.execute(
                    "SELECT id, content, due_at, status, created_at FROM reminders WHERE id = ?",
                    (existing_item["id"],),
                )
                updated = dict(cursor.fetchone())
                updated["updated"] = True
                updated["due_label"] = format_due_label(updated.get("due_at"))
                return updated
            existing_item["duplicate"] = True
            existing_item["due_label"] = format_due_label(existing_item.get("due_at"))
            return existing_item

        cursor.execute(
            "INSERT INTO reminders (content, due_at, status, created_at) VALUES (?, ?, 'pending', ?)",
            (content, due_at, utcnow()),
        )
        return {
            "id": cursor.lastrowid,
            "content": content,
            "due_at": due_at,
            "due_label": format_due_label(due_at),
            "status": "pending",
        }


def list_reminders(skip: int = 0, limit: int = 50, status: str | None = None) -> tuple[list[dict[str, Any]], int]:
    with get_db() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT COUNT(*) AS total FROM reminders WHERE status = ?", (status,))
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                """
                SELECT id, content, due_at, status, created_at
                FROM reminders
                WHERE status = ?
                ORDER BY COALESCE(datetime(due_at), datetime(created_at)) ASC
                LIMIT ? OFFSET ?
                """,
                (status, limit, skip),
            )
        else:
            cursor.execute("SELECT COUNT(*) AS total FROM reminders")
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                """
                SELECT id, content, due_at, status, created_at
                FROM reminders
                ORDER BY COALESCE(datetime(due_at), datetime(created_at)) ASC
                LIMIT ? OFFSET ?
                """,
                (limit, skip),
            )
        items = [dict(row) for row in cursor.fetchall()]
        for item in items:
            item["due_label"] = format_due_label(item.get("due_at"))
        return items, total


def update_reminder_status(reminder_id: int, status: str) -> dict[str, Any] | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE reminders SET status = ? WHERE id = ?", (status, reminder_id))
        cursor.execute(
            "SELECT id, content, due_at, status, created_at FROM reminders WHERE id = ?",
            (reminder_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_note(note_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cursor.rowcount > 0


def delete_task(task_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cursor.rowcount > 0


def delete_reminder(reminder_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        return cursor.rowcount > 0


def log_action(actor: str, action: str, risk: str, confirmed: bool, result: str) -> None:
    with get_db() as conn:
        conn.cursor().execute(
            """
            INSERT INTO action_logs (actor, action, risk, confirmed, result, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (actor, action, risk, int(confirmed), result, utcnow()),
        )


def list_action_logs(skip: int = 0, limit: int = 50) -> tuple[list[dict[str, Any]], int]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM action_logs")
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT id, actor, action, risk, confirmed, result, created_at
            FROM action_logs
            ORDER BY datetime(created_at) DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip),
        )
        items = [dict(row) for row in cursor.fetchall()]
        return items, total


def save_conversation_summary(session_id: str, summary: str) -> None:
    with get_db() as conn:
        conn.cursor().execute(
            "INSERT INTO conversation_summaries (session_id, summary, created_at) VALUES (?, ?, ?)",
            (session_id, summary, utcnow()),
        )


def list_summary_sessions_with_excess(threshold: int = 5) -> list[str]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT session_id
            FROM conversation_summaries
            GROUP BY session_id
            HAVING COUNT(*) >= ?
            """,
            (threshold,),
        )
        return [row["session_id"] for row in cursor.fetchall()]


def take_session_summaries(session_id: str) -> list[dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, summary, created_at
            FROM conversation_summaries
            WHERE session_id = ?
            ORDER BY datetime(created_at) ASC
            """,
            (session_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def replace_session_summaries(session_id: str, compacted: str) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_summaries WHERE session_id = ?", (session_id,))
        cursor.execute(
            "INSERT INTO conversation_summaries (session_id, summary, created_at) VALUES (?, ?, ?)",
            (session_id, compacted, utcnow()),
        )


def get_recent_summary(session_id: str) -> str | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT summary
            FROM conversation_summaries
            WHERE session_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        return str(row["summary"]) if row else None


# ── Memories ────────────────────────────────────────────────────────────────


def create_memory(content: str, tags: str = "") -> dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        existing = cursor.execute(
            "SELECT id, content, created_at FROM memories WHERE lower(trim(content)) = lower(trim(?)) LIMIT 1",
            (content,),
        ).fetchone()
        if existing:
            return {**dict(existing), "duplicate": True}

        emb = get_embedding(content)
        embedding_str = json.dumps(emb) if emb else None
        cursor.execute(
            "INSERT INTO memories (content, tags, embedding, created_at) VALUES (?, ?, ?, ?)",
            (content, tags, embedding_str, utcnow()),
        )
        return {
            "id": cursor.lastrowid,
            "content": content,
            "tags": tags,
            "created_at": utcnow(),
        }


def list_memories(skip: int = 0, limit: int = 50) -> tuple[list[dict[str, Any]], int]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM memories")
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT id, content, tags, created_at
            FROM memories
            ORDER BY datetime(created_at) DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip),
        )
        items = [dict(row) for row in cursor.fetchall()]
        return items, total


def delete_memory(memory_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cursor.rowcount > 0


def get_recent_memories(limit: int = 10) -> list[dict[str, Any]]:
    items, _ = list_memories(limit=limit)
    return items


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 * mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def get_relevant_memories(query: str, limit: int = 10) -> list[dict[str, Any]]:
    query_emb = get_embedding(query)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, tags, embedding, created_at FROM memories")
        all_memories = [dict(row) for row in cursor.fetchall()]

    if not query_emb:
        # Fallback to recent if embeddings fail
        return sorted(all_memories, key=lambda x: x["created_at"], reverse=True)[:limit]

    scored = []
    for m in all_memories:
        emb_str = m.get("embedding")
        if not emb_str:
            continue
        try:
            emb = json.loads(emb_str)
            score = _cosine_similarity(query_emb, emb)
            scored.append((score, m))
        except (json.JSONDecodeError, ValueError):
            pass

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for score, m in scored if score > 0.3][:limit]


def get_relevant_notes(query: str, limit: int = 5) -> list[dict[str, Any]]:
    query_emb = get_embedding(query)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, content, embedding, created_at FROM notes"
        ).fetchall()
        all_notes = [dict(r) for r in rows]

    if not query_emb:
        return sorted(all_notes, key=lambda x: x["created_at"], reverse=True)[:limit]

    scored = []
    for n in all_notes:
        emb_str = n.get("embedding")
        if not emb_str:
            continue
        try:
            emb = json.loads(emb_str)
            score = _cosine_similarity(query_emb, emb)
            scored.append((score, n))
        except (json.JSONDecodeError, ValueError):
            pass

    scored.sort(key=lambda x: x[0], reverse=True)
    return [n for score, n in scored if score > 0.3][:limit]


def semantic_search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """
    Hybrid search: semantic similarity for embedded items + keyword match for
    unembedded items. Results are merged and deduplicated.
    """
    query_emb = get_embedding(query)
    kw = query.lower()

    scored: list[tuple[float, dict]] = []   # (similarity_score, item)
    kw_only: list[dict] = []                # items with no embedding but keyword match

    with get_db() as conn:
        rows_mem = conn.execute(
            "SELECT id, content, tags, embedding, created_at FROM memories"
        ).fetchall()
        rows_note = conn.execute(
            "SELECT id, content, embedding, created_at FROM notes"
        ).fetchall()

    for row, source in [(r, "memory") for r in rows_mem] + [(r, "note") for r in rows_note]:
        item = dict(row)
        emb_str = item.pop("embedding", None)
        item["source"] = source
        has_kw = kw in (item.get("content") or "").lower()

        if emb_str and query_emb:
            try:
                emb = json.loads(emb_str)
                score = _cosine_similarity(query_emb, emb)
                scored.append((score, item))
                continue
            except (json.JSONDecodeError, ValueError):
                pass

        # No usable embedding — fall back to keyword
        if has_kw:
            kw_only.append(item)

    scored.sort(key=lambda x: x[0], reverse=True)
    # Threshold 0.3 — more conservative; nomic-embed-text scores < 0.3 are usually unrelated
    top: list[dict] = [item for score, item in scored if score > 0.3][:limit]

    # Supplement with keyword-only hits that aren't already in top
    seen = {(r["source"], r["id"]) for r in top}
    for item in kw_only:
        if (item["source"], item["id"]) not in seen:
            top.append(item)
            seen.add((item["source"], item["id"]))

    # If still nothing, show the top-2 semantic results regardless of threshold
    if not top and scored:
        top = [item for _, item in scored[:2]]

    return top[:limit]


def build_daily_briefing() -> dict[str, Any]:
    pending_tasks, _ = list_tasks(limit=5, status="pending")
    pending_reminders, _ = list_reminders(limit=5, status="pending")

    high_priority = [task for task in pending_tasks if task["priority"] == "high"]
    if high_priority:
        focus_recommendation = f"Start with '{high_priority[0]['description']}' while your cognitive stack is still fresh."
    elif pending_tasks:
        focus_recommendation = f"Continue with '{pending_tasks[0]['description']}' next."
    else:
        focus_recommendation = "No pending tasks detected. A rare and suspiciously tidy moment."

    return {
        "timestamp": utcnow(),
        "top_tasks": pending_tasks,
        "reminders": pending_reminders,
        "focus_recommendation": focus_recommendation,
        "summary": f"{len(pending_tasks)} pending task(s), {len(pending_reminders)} reminder(s).",
    }


def build_assistant_context(query: str) -> list[dict[str, str]]:
    lowered = query.lower()
    context: list[dict[str, str]] = []

    # Semantic search across memories and notes
    relevant = semantic_search(query, limit=8)
    mem_hits = [r for r in relevant if r.get("source") == "memory"]
    note_hits = [r for r in relevant if r.get("source") == "note"]

    # Fallback: if no semantic hits, surface recent items
    if not mem_hits:
        mem_hits = get_recent_memories(limit=3)
    if not note_hits and any(w in lowered for w in ("note", "notes", "remember", "memorized", "know about", "think about")):
        recent, _ = list_notes(limit=3)
        note_hits = recent

    if mem_hits:
        joined = "\n".join(f"- {m['content']}" for m in mem_hits)
        context.append({"role": "system", "content": f"Long-term memories:\n{joined}"})

    if note_hits:
        joined = "\n".join(f"- {n['content']}" for n in note_hits)
        context.append({"role": "system", "content": f"Relevant notes:\n{joined}"})

    if any(word in lowered for word in ["reminder", "reminders", "remind me"]):
        reminders, _ = list_reminders(limit=5, status="pending")
        if reminders:
            joined = "\n".join(
                f"- {item['content']}" + (f" ({item['due_label']})" if item.get("due_label") else "")
                for item in reminders
            )
            context.append({"role": "system", "content": f"Pending reminders:\n{joined}"})

    if any(word in lowered for word in ["task", "tasks", "focus", "todo", "to-do"]):
        tasks, _ = list_tasks(limit=5, status="pending")
        if tasks:
            joined = "\n".join(f"- {item['description']} ({item['priority']})" for item in tasks)
            context.append({"role": "system", "content": f"Pending tasks:\n{joined}"})

    return context


def _parse_reminder_schedule(text: str) -> tuple[str, str | None]:
    cleaned = text.strip()

    daily_match = re.search(r"\bdaily at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", cleaned, re.IGNORECASE)
    if daily_match:
        hour = int(daily_match.group(1))
        minute = int(daily_match.group(2) or "0")
        meridiem = daily_match.group(3).lower()
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        due_at = f"daily:{hour:02d}:{minute:02d}"
        content = re.sub(r"\bdaily at\s+\d{1,2}(?::\d{2})?\s*(am|pm)\b", "", cleaned, flags=re.IGNORECASE).strip(" .")
        return (content or cleaned, due_at)

    time_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", cleaned, re.IGNORECASE)
    if time_match:
        now = current_local_time()
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or "0")
        meridiem = time_match.group(3).lower()
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0

        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= now:
            due = due + timedelta(days=1)

        due_at = f"once:{due.isoformat()}"
        content = re.sub(r"\bat\s+\d{1,2}(?::\d{2})?\s*(am|pm)\b", "", cleaned, flags=re.IGNORECASE).strip(" .")
        return (content or cleaned, due_at)

    return cleaned, None


# ── Action helpers used by the intent router ────────────────────────────────


def perform_create_reminder(content: str, due_at: str | None = None) -> dict[str, str]:
    content, parsed_due = _parse_reminder_schedule(content)
    item = create_reminder(content, due_at or parsed_due)
    if item.get("duplicate"):
        return {
            "kind": "reminder",
            "status": "duplicate",
            "message": f"Sir, that reminder already exists: {item['content']}.",
        }
    if item.get("updated"):
        schedule_text = f" {item['due_label']}." if item.get("due_label") else ""
        return {
            "kind": "reminder",
            "status": "updated",
            "message": f"Sir, reminder updated: {item['content']}.{schedule_text}",
        }
    label = format_due_label(item.get("due_at"))
    schedule_text = f" {label}." if label else ""
    return {
        "kind": "reminder",
        "status": "created",
        "message": f"Sir, reminder created: {item['content']}.{schedule_text}",
    }


def perform_create_task(description: str) -> dict[str, str]:
    item = create_task(description)
    if item.get("duplicate"):
        return {
            "kind": "task",
            "status": "duplicate",
            "message": f"Sir, that task is already pending: {item['description']}.",
        }
    return {
        "kind": "task",
        "status": "created",
        "message": f"Sir, task added: {item['description']}.",
    }


def perform_create_note(content: str) -> dict[str, str]:
    item = create_note(content)
    if item.get("duplicate"):
        return {
            "kind": "note",
            "status": "duplicate",
            "message": f"Sir, that note is already in memory: {item['content']}.",
        }
    return {
        "kind": "note",
        "status": "created",
        "message": f"Sir, note stored: {item['content']}.",
    }


def perform_create_memory(content: str) -> dict[str, str]:
    item = create_memory(content)
    if item.get("duplicate"):
        return {
            "kind": "memory",
            "status": "duplicate",
            "message": f"Sir, that's already in memory: {item['content']}.",
        }
    return {
        "kind": "memory",
        "status": "created",
        "message": f"Sir, committed to long-term memory: {item['content']}.",
    }
