import sys
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any


class HotMemoryCache:
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)

    def _is_expired(self, entry: dict[str, Any]) -> bool:
        return datetime.now(timezone.utc) > entry["expires_at"]

    async def get(self, key: str) -> Any | None:
        if key not in self.cache:
            return None

        entry = self.cache[key]
        if self._is_expired(entry):
            del self.cache[key]
            return None

        self.cache.move_to_end(key)
        return entry["value"]

    async def set(self, key: str, value: Any) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        elif len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)

        self.cache[key] = {
            "value": value,
            "expires_at": datetime.now(timezone.utc) + self.ttl,
        }

    async def invalidate_pattern(self, pattern: str) -> None:
        keys = [key for key in self.cache if pattern in key]
        for key in keys:
            del self.cache[key]

    def clear(self) -> None:
        self.cache.clear()

    def stats(self) -> dict[str, float | int]:
        size_bytes = sum(sys.getsizeof(value) for value in self.cache.values())
        return {
            "entries": len(self.cache),
            "max_size": self.max_size,
            "size_kb": round(size_bytes / 1024, 2),
        }


hot_cache = HotMemoryCache()
