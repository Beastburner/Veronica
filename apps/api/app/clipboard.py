from __future__ import annotations

"""
clipboard.py — Smart clipboard / snippets store for Veronica AI assistant.

Table used:
    clipboard_items(id, content, tags, source, created_at)

tags: comma-separated string  e.g. "python,snippet,useful"
source: "user" | "veronica" | "web"
"""

from typing import Any

from app.db import get_db, utcnow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _normalize_tags(tags: str) -> str:
    """Lowercase, strip whitespace around each tag, deduplicate, rejoin."""
    parts = [t.strip().lower() for t in tags.split(",") if t.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return ",".join(unique)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def save_clip(
    content: str,
    tags: str = "",
    source: str = "user",
) -> dict[str, Any]:
    """
    Save a new clipboard item and return the created row as a dict.

    Args:
        content: The text content to store.
        tags:    Comma-separated tag string (e.g. "python,tip").
        source:  One of "user", "veronica", or "web".
    """
    now = utcnow()
    normalized_tags = _normalize_tags(tags)
    with get_db() as db:
        cur = db.execute(
            """
            INSERT INTO clipboard_items (content, tags, source, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (content, normalized_tags, source, now),
        )
        db.commit()
        clip_id = cur.lastrowid
        row = db.execute(
            "SELECT * FROM clipboard_items WHERE id = ?", (clip_id,)
        ).fetchone()
    return _row_to_dict(row)


def list_clips(
    limit: int = 20,
    tag_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return the most recent `limit` clipboard items.

    If tag_filter is provided, only return items whose tags column contains
    that tag (any single tag match is sufficient).
    """
    with get_db() as db:
        if tag_filter:
            tag = tag_filter.strip().lower()
            # Match as a standalone tag inside the comma-separated string.
            # We check four patterns: exact, prefix, suffix, middle.
            rows = db.execute(
                """
                SELECT * FROM clipboard_items
                WHERE lower(tags) = ?
                   OR lower(tags) LIKE ?
                   OR lower(tags) LIKE ?
                   OR lower(tags) LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (tag, f"{tag},%", f"%,{tag}", f"%,{tag},%", limit),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT * FROM clipboard_items
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def search_clips(query: str) -> list[dict[str, Any]]:
    """
    Full-text keyword search across content and tags columns.
    Returns all matching rows ordered by most recent first.
    """
    like = f"%{query}%"
    with get_db() as db:
        rows = db.execute(
            """
            SELECT * FROM clipboard_items
            WHERE content LIKE ?
               OR tags LIKE ?
            ORDER BY created_at DESC
            """,
            (like, like),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_clip(clip_id: int) -> bool:
    """Delete a clipboard item by ID. Returns True if a row was deleted."""
    with get_db() as db:
        cur = db.execute(
            "DELETE FROM clipboard_items WHERE id = ?", (clip_id,)
        )
        db.commit()
    return cur.rowcount > 0


def get_clip(clip_id: int) -> dict[str, Any] | None:
    """Fetch a single clipboard item by ID, or None if not found."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM clipboard_items WHERE id = ?", (clip_id,)
        ).fetchone()
    return _row_to_dict(row) if row is not None else None
