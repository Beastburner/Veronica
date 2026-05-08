from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("veronica.scheduler")

_scheduler = None


def _backfill_embeddings() -> None:
    """Embed any memories/notes that were saved before embeddings were wired up."""
    try:
        from app.db import get_db
        from app.llm_client import get_embedding
        import json

        with get_db() as conn:
            missing_mems = conn.execute(
                "SELECT id, content FROM memories WHERE embedding IS NULL LIMIT 50"
            ).fetchall()
            for row in missing_mems:
                emb = get_embedding(row["content"])
                if emb:
                    conn.execute(
                        "UPDATE memories SET embedding = ? WHERE id = ?",
                        (json.dumps(emb), row["id"]),
                    )

            missing_notes = conn.execute(
                "SELECT id, content FROM notes WHERE embedding IS NULL LIMIT 50"
            ).fetchall()
            for row in missing_notes:
                emb = get_embedding(row["content"])
                if emb:
                    conn.execute(
                        "UPDATE notes SET embedding = ? WHERE id = ?",
                        (json.dumps(emb), row["id"]),
                    )

        total = len(missing_mems) + len(missing_notes)
        if total:
            log.info("Backfilled embeddings for %d record(s)", total)
    except Exception:
        log.exception("embedding backfill failed")


def _auto_journal() -> None:
    try:
        from app.journal import generate_journal_entry
        result = generate_journal_entry()
        log.info("Auto-journal generated for %s", result.get("date"))
    except Exception:
        log.exception("auto_journal failed")


def _check_due_reminders() -> None:
    try:
        from app.db import get_db
        from app.life_log import log_entry

        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, content, due_at FROM reminders WHERE status = 'pending' AND due_at LIKE 'once:%'"
            ).fetchall()

            for row in rows:
                try:
                    due_dt = datetime.fromisoformat(row["due_at"][5:])
                    if now >= due_dt:
                        conn.execute(
                            "UPDATE reminders SET status = 'done' WHERE id = ?", (row["id"],)
                        )
                        log_entry(
                            "reminder_fired",
                            row["content"],
                            "Auto-fired by scheduler",
                            {"reminder_id": row["id"]},
                        )
                except (ValueError, TypeError):
                    continue
    except Exception:
        log.exception("check_due_reminders failed")


def start() -> None:
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import]

        _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        _scheduler.add_job(_check_due_reminders, "interval", minutes=1, id="reminder_check")
        _scheduler.add_job(_auto_journal, "cron", hour=22, minute=30, id="auto_journal")
        _scheduler.add_job(_backfill_embeddings, "interval", minutes=10, id="embed_backfill")
        _scheduler.start()
        # Run backfill once immediately on startup
        _scheduler.add_job(_backfill_embeddings, "date", id="embed_backfill_startup")
        log.info("APScheduler started — checking reminders every minute")
    except ImportError:
        log.warning("apscheduler not installed — background scheduler disabled")
    except Exception:
        log.exception("Failed to start scheduler")


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            log.info("APScheduler stopped")
        except Exception:
            log.exception("Failed to stop scheduler")
        _scheduler = None
