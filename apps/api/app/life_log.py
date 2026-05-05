from __future__ import annotations

import json
from typing import Any

from app.db import get_db, utcnow


def log_entry(
    entry_type: str,
    title: str,
    content: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta_json = json.dumps(metadata) if metadata else None
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO life_log (entry_type, title, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
            (entry_type, title[:200], content[:1000], meta_json, utcnow()),
        )
        return {
            "id": cursor.lastrowid,
            "entry_type": entry_type,
            "title": title,
            "created_at": utcnow(),
        }


def list_entries(
    skip: int = 0,
    limit: int = 20,
    entry_type: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    with get_db() as conn:
        if entry_type:
            total = conn.execute(
                "SELECT COUNT(*) FROM life_log WHERE entry_type = ?", (entry_type,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM life_log WHERE entry_type = ? ORDER BY datetime(created_at) DESC LIMIT ? OFFSET ?",
                (entry_type, limit, skip),
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM life_log").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM life_log ORDER BY datetime(created_at) DESC LIMIT ? OFFSET ?",
                (limit, skip),
            ).fetchall()
        return [dict(r) for r in rows], total
