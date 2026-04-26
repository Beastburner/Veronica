import gc
import os
from datetime import datetime, timezone
from typing import Any

import psutil


class MemoryMonitor:
    def __init__(self, warning_mb: int = 400, critical_mb: int = 800):
        self.process = psutil.Process(os.getpid())
        self.warning = warning_mb
        self.critical = critical_mb
        self.history: list[dict[str, Any]] = []

    def get_stats(self) -> dict[str, Any]:
        mem = self.process.memory_info()
        stats = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rss_mb": round(mem.rss / (1024 * 1024), 2),
            "vms_mb": round(mem.vms / (1024 * 1024), 2),
            "percent": round(self.process.memory_percent(), 2),
            "threads": self.process.num_threads(),
        }
        self.history.append(stats)
        if len(self.history) > 100:
            self.history.pop(0)
        return stats

    def check_thresholds(self) -> dict[str, Any]:
        stats = self.get_stats()
        current = stats["rss_mb"]
        if current > self.critical:
            status = "CRITICAL"
            action = "Reduce load, clear cache, or restart worker."
        elif current > self.warning:
            status = "WARNING"
            action = "Monitor closely and consider clearing cache."
        else:
            status = "OK"
            action = "Normal"

        return {
            "status": status,
            "action": action,
            "current_mb": current,
            "warning_mb": self.warning,
            "critical_mb": self.critical,
        }

    def force_gc(self) -> dict[str, Any]:
        before = self.get_stats()["rss_mb"]
        collected = gc.collect()
        after = self.get_stats()["rss_mb"]
        return {
            "collected": collected,
            "before_mb": before,
            "after_mb": after,
            "freed_mb": round(before - after, 2),
        }

    def get_trend(self) -> dict[str, Any]:
        if len(self.history) < 5:
            return {"trend": "insufficient_data"}

        values = [float(item["rss_mb"]) for item in self.history[-20:]]
        slope = values[-1] - values[0]
        if slope > 30:
            trend = "increasing_fast"
        elif slope > 5:
            trend = "increasing_slow"
        elif slope < -5:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "delta_mb": round(slope, 2),
            "min_mb": min(values),
            "max_mb": max(values),
        }
