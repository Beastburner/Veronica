from __future__ import annotations

import logging

from app.db import get_db, utcnow

log = logging.getLogger("veronica.oauth")


def save_oauth_token(service: str, token_json: str) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO oauth_tokens (service, token_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(service) DO UPDATE
              SET token_json = excluded.token_json,
                  updated_at = excluded.updated_at
            """,
            (service, token_json, utcnow()),
        )


def load_oauth_token(service: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT token_json FROM oauth_tokens WHERE service = ?", (service,)
        ).fetchone()
        return row["token_json"] if row else None


def delete_oauth_token(service: str) -> bool:
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM oauth_tokens WHERE service = ?", (service,))
        return cursor.rowcount > 0


def get_connected_services() -> list[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT service FROM oauth_tokens").fetchall()
        return [r["service"] for r in rows]
