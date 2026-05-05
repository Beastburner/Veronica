from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger("veronica.scheduler")

_scheduler = None


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
        _scheduler.start()
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
