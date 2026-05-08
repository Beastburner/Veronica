"""
Behavioral learning module — tracks interaction patterns and generates
personalized suggestions based on how and when the user uses Veronica.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.db import get_db, utcnow

# Activity completion detection — matches phrases like "I worked out", "finished reading"
_ACTIVITY_DONE_RE = re.compile(
    r"(?:^|\s)"
    r"(?:i\s+(?:just\s+)?)?(?:did|finished?|completed?|done|had|went\s+(?:for\s+(?:a\s+)?|to\s+(?:the\s+)?))"
    r"(?:\s+(?:my|a|the|some))?"
    r"\s*(?P<activity>"
    r"workout|exercise|gym|running|jogging|walk(?:ing)?|yoga|meditati(?:on|ng)|"
    r"readi(?:ng)?|coding|programming|studying|study|journal(?:ing|led)?|"
    r"swimming|cycling|stretching|pushups?|pull[\-\s]?ups?"
    r")",
    re.IGNORECASE,
)

# Normalise surface forms to canonical habit names
_ACTIVITY_ALIAS: dict[str, str] = {
    "exercise": "workout", "gym": "workout", "running": "run",
    "jogging": "run", "meditating": "meditation", "meditation": "meditation",
    "reading": "reading", "coding": "coding", "programming": "coding",
    "studying": "study", "journaling": "journal", "journalled": "journal",
    "journaled": "journal", "swimming": "swimming", "cycling": "cycling",
    "stretching": "stretching", "pushups": "pushups", "push-ups": "pushups",
    "pull-ups": "pull-ups", "pullups": "pull-ups",
}

_STOP_WORDS = frozenset({
    "a", "an", "the", "to", "of", "for", "in", "on", "at", "is", "be",
    "i", "my", "me", "it", "this", "that", "with", "and", "or", "can",
    "you", "please", "just", "can", "could", "would", "should", "will",
    "do", "did", "does", "have", "has", "had", "what", "how", "when",
    "where", "why", "who", "tell", "show", "get", "give", "make", "let",
    "want", "need", "like", "know", "think", "use", "also", "from",
    "about", "some", "any", "all", "no", "not", "but", "so", "if",
})

_WORD_RE = re.compile(r"[a-zA-Z]{4,}")


def _extract_topic(message: str) -> str:
    words = _WORD_RE.findall(message.lower())
    meaningful = [w for w in words if w not in _STOP_WORDS]
    if not meaningful:
        return ""
    freq: dict[str, int] = {}
    for w in meaningful:
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=lambda x: -freq[x])
    return " ".join(top[:3])


def record_interaction(message: str, intent_type: str, mode: str) -> None:
    now = datetime.now(timezone.utc)
    topic = _extract_topic(message)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO behavior_events (topic, intent_type, mode, hour_of_day, day_of_week, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (topic, intent_type, mode, now.hour, now.weekday(), utcnow()),
        )


def get_hourly_pattern() -> dict[int, int]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT hour_of_day, COUNT(*) as cnt
            FROM behavior_events
            WHERE created_at > datetime('now', '-30 days')
            GROUP BY hour_of_day
            """
        ).fetchall()
    return {row["hour_of_day"]: row["cnt"] for row in rows}


def get_top_topics(n: int = 5) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT topic, COUNT(*) as cnt
            FROM behavior_events
            WHERE topic != '' AND created_at > datetime('now', '-30 days')
            GROUP BY topic
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
    return [row["topic"] for row in rows]


def get_intent_breakdown() -> dict[str, int]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT intent_type, COUNT(*) as cnt
            FROM behavior_events
            WHERE created_at > datetime('now', '-30 days')
            GROUP BY intent_type
            ORDER BY cnt DESC
            """
        ).fetchall()
    return {row["intent_type"]: row["cnt"] for row in rows}


def get_personalized_suggestions(mode: str) -> list[str]:
    from app.storage import get_recent_memories
    from app.llm_client import call_json

    now = datetime.now(timezone.utc)
    hour = now.hour
    dow = now.weekday()  # 0=Monday

    hourly = get_hourly_pattern()
    top_topics = get_top_topics(3)

    # Try dynamic LLM suggestions first based on memory and behavior
    try:
        memories = get_recent_memories(limit=30)
        memory_texts = "\n".join(f"- {m['content']}" for m in memories) if memories else "No long-term memories yet."
        
        schema = 'Schema: {"suggestions": [string]}'
        prompt = f"""Generate 3 highly personalized short action suggestions for the user based on their habits and memories.
Current Mode: {mode}
Current time: Hour {hour}, Day of week: {dow} (0=Mon, 6=Sun)
Top topics: {', '.join(top_topics) if top_topics else 'none'}
Memories:
{memory_texts}

Examples:
- "You have a great idea? Send a message to [Name] to discuss." (if [Name] is in memory)
- "Time to play some Valorant with [Name]?" (if user plays Valorant)
- "Review your latest notes on [Topic] and get some resources from [Source]."
- "Draft a new message checking up on [Name]."

Respond ONLY in JSON format: {{"suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"]}}"""

        payload = call_json(prompt, schema_hint=schema, max_tokens=150)
        if payload and isinstance(payload.get("suggestions"), list) and payload["suggestions"]:
            suggestions = [str(s) for s in payload["suggestions"] if isinstance(s, str)]
            if len(suggestions) >= 1:
                return suggestions[:3]
    except Exception as e:
        import logging
        logging.getLogger("veronica.behavior").warning("Dynamic suggestions failed: %s", e)

    # Fallback to deterministic suggestions
    suggestions: list[str] = []

    # Time-based contextual hints
    if 6 <= hour <= 9:
        suggestions.append("Start the day with a daily briefing — check tasks, reminders, and calendar.")
    elif 12 <= hour <= 13:
        suggestions.append("Midday check-in: review pending tasks and reschedule anything overdue.")
    elif 14 <= hour <= 16:
        suggestions.append("Afternoon slump? Deep work block — use focus mode to power through tasks.")
    elif 19 <= hour <= 22:
        suggestions.append("End-of-day wrap: set tomorrow's reminders before you close up.")

    # Monday planning suggestion
    if dow == 0 and 9 <= hour <= 11:
        suggestions.append("It's Monday morning — plan your week now with a task prioritization session.")

    # Topic-based (surface what the user works on most)
    if top_topics:
        t = top_topics[0]
        suggestions.append(f"Continue where you left off: '{t}'")

    # Mode-specific defaults (fallback)
    mode_defaults = {
        "JARVIS": "Run a system architecture review or dependency audit.",
        "FRIDAY": "Ask FRIDAY to prioritize your task list for maximum leverage today.",
        "VERONICA": "Run a quick status report: tasks, reminders, and email inbox.",
        "SENTINEL": "Review the last 24 hours of action logs for any anomalies.",
    }
    if mode.upper() in mode_defaults and len(suggestions) < 3:
        suggestions.append(mode_defaults[mode.upper()])

    return suggestions[:3]


def get_behavior_summary() -> dict[str, Any]:
    return {
        "hourly_pattern": get_hourly_pattern(),
        "top_topics": get_top_topics(5),
        "intent_breakdown": get_intent_breakdown(),
    }
