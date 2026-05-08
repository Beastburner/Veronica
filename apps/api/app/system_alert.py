from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.db import get_db, utcnow

log = logging.getLogger("veronica.system_alert")

DEFAULT_THRESHOLDS: dict[str, float] = {
    "cpu_percent": 90.0,
    "ram_percent": 85.0,
    "disk_percent": 90.0,
}

_thresholds: dict[str, float] = dict(DEFAULT_THRESHOLDS)
_watchdog_task: asyncio.Task | None = None


def set_thresholds(
    cpu: float | None = None,
    ram: float | None = None,
    disk: float | None = None,
) -> dict[str, float]:
    if cpu is not None:
        _thresholds["cpu_percent"] = float(cpu)
    if ram is not None:
        _thresholds["ram_percent"] = float(ram)
    if disk is not None:
        _thresholds["disk_percent"] = float(disk)
    return dict(_thresholds)


def get_thresholds() -> dict[str, float]:
    return dict(_thresholds)


def _save_alert(resource: str, value: float, threshold: float) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO system_alerts (resource, value, threshold, created_at) VALUES (?, ?, ?, ?)",
            (resource, value, threshold, utcnow()),
        )


def get_alerts(limit: int = 20) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, resource, value, threshold, created_at FROM system_alerts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


async def _watchdog_loop() -> None:
    import psutil

    while True:
        try:
            await asyncio.sleep(30)
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            checks = [
                ("cpu_percent", cpu),
                ("ram_percent", mem.percent),
                ("disk_percent", disk.percent),
            ]
            for resource, value in checks:
                threshold = _thresholds.get(resource, 100.0)
                if value >= threshold:
                    log.warning("ALERT: %s=%.1f%% exceeds threshold %.1f%%", resource, value, threshold)
                    _save_alert(resource, value, threshold)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("watchdog loop error")


def start_watchdog() -> None:
    global _watchdog_task
    if _watchdog_task is None or _watchdog_task.done():
        _watchdog_task = asyncio.ensure_future(_watchdog_loop())
        log.info("system alert watchdog started")


def stop_watchdog() -> None:
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        _watchdog_task.cancel()
        _watchdog_task = None
        log.info("system alert watchdog stopped")
