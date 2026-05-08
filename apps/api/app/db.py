from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "veronica.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            due_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            risk TEXT NOT NULL,
            confirmed INTEGER NOT NULL DEFAULT 1,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '',
            embedding TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL UNIQUE,
            token_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS life_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_actions (
            session_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'auto',
            interaction_count INTEGER NOT NULL DEFAULT 1,
            last_seen TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts (email);
        CREATE INDEX IF NOT EXISTS idx_contacts_name  ON contacts (name COLLATE NOCASE);

        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            frequency TEXT NOT NULL DEFAULT 'daily',
            color TEXT NOT NULL DEFAULT '#22d3ee',
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL REFERENCES habits(id),
            logged_at TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rss_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clipboard_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pomodoro_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL DEFAULT 'Focus session',
            duration_minutes INTEGER NOT NULL DEFAULT 25,
            completed INTEGER NOT NULL DEFAULT 0,
            interrupted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            finished_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS behavior_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL DEFAULT '',
            intent_type TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL DEFAULT '',
            hour_of_day INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource TEXT NOT NULL,
            value REAL NOT NULL,
            threshold REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_system_alerts_created ON system_alerts (created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
        CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders (status);
        CREATE INDEX IF NOT EXISTS idx_conv_summaries_session ON conversation_summaries (session_id);
        CREATE INDEX IF NOT EXISTS idx_memories_created ON memories (created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_life_log_type ON life_log (entry_type);
        CREATE INDEX IF NOT EXISTS idx_life_log_created ON life_log (created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_behavior_hour ON behavior_events (hour_of_day);
        CREATE INDEX IF NOT EXISTS idx_behavior_created ON behavior_events (created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_habit_logs_habit ON habit_logs (habit_id);
        CREATE INDEX IF NOT EXISTS idx_habit_logs_date ON habit_logs (logged_at DESC);
        CREATE INDEX IF NOT EXISTS idx_pomodoro_created ON pomodoro_sessions (created_at DESC);
        """
    )

    # Purge stale pending actions older than 24 hours
    conn.execute(
        "DELETE FROM pending_actions WHERE created_at < datetime('now', '-24 hours')"
    )

    conn.commit()
    conn.close()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Persistent pending-action store ──────────────────────────────────────────

import json as _json


def save_pending_action(session_id: str, data: dict) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO pending_actions (session_id, data, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET data=excluded.data, created_at=excluded.created_at
            """,
            (session_id, _json.dumps(data), utcnow()),
        )


def load_pending_action(session_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT data FROM pending_actions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return _json.loads(row["data"]) if row else None


def delete_pending_action(session_id: str) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM pending_actions WHERE session_id = ?", (session_id,))
