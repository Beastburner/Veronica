from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class MessageTokenEstimate:
    text: str
    estimated_tokens: int

    @staticmethod
    def estimate(text: str) -> "MessageTokenEstimate":
        return MessageTokenEstimate(text=text, estimated_tokens=max(1, len(text) // 4))


class BoundedContextWindow:
    """
    Keeps a per-session chat context bounded by both message count and
    approximate token usage so long-running conversations do not grow forever.
    """

    def __init__(self, max_tokens: int = 4000, max_messages: int = 10):
        self.max_tokens = max_tokens
        self.max_messages = max_messages
        self.messages: list[dict[str, object]] = []
        self.total_tokens = 0

    def add_message(self, role: str, content: str) -> dict[str, object]:
        estimate = MessageTokenEstimate.estimate(content)
        message = {
            "role": role,
            "content": content,
            "tokens": estimate.estimated_tokens,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.messages.append(message)
        self.total_tokens += estimate.estimated_tokens
        self._trim_to_bounds()
        return message

    def _trim_to_bounds(self) -> None:
        while len(self.messages) > self.max_messages:
            removed = self.messages.pop(0)
            self.total_tokens -= int(removed["tokens"])

        while self.total_tokens > self.max_tokens and len(self.messages) > 1:
            removed = self.messages.pop(0)
            self.total_tokens -= int(removed["tokens"])

    def compress_old_messages(self, keep_last: int = 3) -> None:
        if len(self.messages) <= keep_last:
            return

        old_messages = self.messages[:-keep_last]
        saved_tokens = sum(int(item["tokens"]) for item in old_messages)
        self.total_tokens -= saved_tokens

        summary = {
            "role": "system",
            "content": f"[Summary of {len(old_messages)} previous exchanges retained for continuity]",
            "tokens": 12,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.messages = [summary] + self.messages[-keep_last:]
        self.total_tokens += 12
        self._trim_to_bounds()

    def get_context_messages(self) -> list[dict[str, str]]:
        context: list[dict[str, str]] = []
        for item in self.messages[-self.max_messages:]:
            role = str(item["role"])
            content = str(item["content"])
            if role in {"system", "user", "assistant"}:
                context.append({"role": role, "content": content})
        return context

    def get_context(self) -> dict[str, object]:
        return {
            "messages": self.get_context_messages(),
            "token_count": self.total_tokens,
            "token_limit": self.max_tokens,
            "message_count": len(self.messages),
            "utilization_pct": round((self.total_tokens / self.max_tokens) * 100, 2),
        }
