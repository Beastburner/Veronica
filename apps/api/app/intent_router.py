from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.llm_client import call_json
from app.storage import (
    current_local_time,
    list_notes,
    list_reminders,
    list_tasks,
    perform_create_memory,
    perform_create_note,
    perform_create_reminder,
    perform_create_task,
)

log = logging.getLogger("veronica.intent")

IntentType = Literal["write", "read", "tool", "protocol", "llm", "social"]


@dataclass
class IntentResult:
    type: IntentType
    payload: dict[str, Any] = field(default_factory=dict)


# ── Social intents (greetings / casual openers — no context injected) ────────

_SOCIAL_RE = re.compile(
    r"^(?:hey|hi|hello|sup+|yo+|howdy|hiya|heya|"
    r"w+[au]+s+[ua]*p+|what(?:\'s|s)?\s*up|"
    r"how(?:\'s|\s+are|\s+you|\s+is\s+it\s+going)?|"
    r"good\s+(?:morning|evening|afternoon|night|day))"
    r"[\s!?.,]*$",
    re.IGNORECASE,
)

_SOCIAL_REPLIES = ("Hey.", "Sup.", "Hey, what's good.", "Yo.", "Hey there.")
_social_reply_index = 0


def _social_intent(message: str) -> IntentResult | None:
    global _social_reply_index
    if _SOCIAL_RE.match(message.strip()):
        reply = _SOCIAL_REPLIES[_social_reply_index % len(_SOCIAL_REPLIES)]
        _social_reply_index += 1
        return IntentResult("social", {"message": reply})
    return None


# ── Read intents (deterministic answers) ────────────────────────────────────

_TIME_PHRASES = ("what time", "current time", "time now", "what's the time", "whats the time", "what is the time", "date today", "what day is it", "today's date")
_REMINDER_LIST_PHRASES = ("check reminder", "check reminders", "see reminders", "see the reminder", "show reminders", "what reminders", "my reminders", "pending reminders")
_TASK_LIST_PHRASES = ("what tasks", "show tasks", "check tasks", "what should i focus on", "todo", "to-do", "my tasks", "pending tasks")
_NOTE_LIST_PHRASES = ("show notes", "show memory", "what notes", "what do you remember", "check notes", "list memories", "show memories")


def _read_intent(message: str) -> IntentResult | None:
    lowered = message.lower().strip()

    if any(phrase in lowered for phrase in _TIME_PHRASES):
        now = current_local_time()
        return IntentResult(
            "read",
            {
                "kind": "time",
                "message": f"Sir, the current time is {now.strftime('%I:%M %p')} IST on {now.strftime('%B %d, %Y')}.",
            },
        )

    _creation_guard = ("create", "add", "make", "set", "new", "schedule", "remind")

    if any(phrase in lowered for phrase in _REMINDER_LIST_PHRASES) or (
        "reminder" in lowered
        and any(w in lowered for w in ("what", "show", "see", "check", "pending", "list"))
        and not any(v in lowered for v in _creation_guard)
    ):
        reminders, _ = list_reminders(limit=10, status="pending")
        if reminders:
            items = "; ".join(
                r["content"] + (f" ({r['due_label']})" if r.get("due_label") else "")
                for r in reminders
            )
            text = f"Sir, you currently have {len(reminders)} pending reminder(s): {items}."
        else:
            text = "Sir, no pending reminders are currently stored."
        return IntentResult("read", {"kind": "reminders", "message": text})

    if any(phrase in lowered for phrase in _TASK_LIST_PHRASES) or (
        "task" in lowered
        and any(w in lowered for w in ("what", "show", "check", "pending", "list"))
        and not any(v in lowered for v in _creation_guard)
    ):
        tasks, _ = list_tasks(limit=10, status="pending")
        if tasks:
            items = "; ".join(f"{t['description']} ({t['priority']})" for t in tasks)
            text = f"Sir, your pending task list: {items}."
        else:
            text = "Sir, the task queue is empty. Suspiciously efficient."
        return IntentResult("read", {"kind": "tasks", "message": text})

    if any(phrase in lowered for phrase in _NOTE_LIST_PHRASES):
        notes, _ = list_notes(limit=10)
        if notes:
            items = "; ".join(n["content"] for n in notes)
            text = f"Sir, recent stored notes: {items}."
        else:
            text = "Sir, no stored notes yet."
        return IntentResult("read", {"kind": "notes", "message": text})

    return None


# ── Write intents (regex fast paths) ────────────────────────────────────────

_REMINDER_PREFIXES = (
    "set reminder to ",
    "add reminder to ",
    "create reminder to ",
    "create reminder for ",
    "create a reminder to ",
    "create a reminder for ",
    "remind me to ",
    "remind me about ",
    "set a reminder to ",
    "set a reminder for ",
    "add a reminder to ",
    "add a reminder for ",
    "schedule a reminder to ",
    "schedule a reminder for ",
    "schedule reminder to ",
    "schedule reminder for ",
)
_TASK_PREFIXES = (
    "add task to ",
    "create task to ",
    "create task: ",
    "add a task to ",
    "set task to ",
    "create a task to ",
    "create a task: ",
    "make a task to ",
    "make a task: ",
    "make a task ",
    "make task ",
    "new task: ",
    "task: ",
    "add task: ",
    "add task ",
    "create task ",
    "new task ",
)
_NOTE_PREFIXES = (
    "save note ",
    "save a note ",
    "take note ",
    "remember that ",
    "note: ",
    "add note: ",
    "create note: ",
    "jot down ",
    "write down ",
    "note that ",
)
_MEMORY_PREFIXES = (
    "remember this: ",
    "commit to memory: ",
    "memorize: ",
    "memorize this: ",
)


def _write_intent_regex(message: str) -> IntentResult | None:
    lowered = message.lower().strip()
    normalized = " ".join(message.strip().split())

    for prefix in _REMINDER_PREFIXES:
        if lowered.startswith(prefix):
            content = normalized[len(prefix):].strip()
            if content:
                return IntentResult("write", perform_create_reminder(content))

    for prefix in _TASK_PREFIXES:
        if lowered.startswith(prefix):
            content = normalized[len(prefix):].strip()
            if content:
                return IntentResult("write", perform_create_task(content))

    for prefix in _MEMORY_PREFIXES:
        if lowered.startswith(prefix):
            content = normalized[len(prefix):].strip()
            if content:
                return IntentResult("write", perform_create_memory(content))

    for prefix in _NOTE_PREFIXES:
        if lowered.startswith(prefix):
            content = normalized[len(prefix):].strip()
            if content:
                return IntentResult("write", perform_create_note(content))

    return None


# ── Write intents (LLM-extracted, for ambiguous phrasing) ───────────────────

_WRITE_HINT_WORDS = (
    "remind", "reminder", "task", "to-do", "todo", "note", "remember",
    "memorize", "schedule", "log", "save", "store",
    "i need to", "i have to", "i must", "i should", "don't forget", "do not forget",
)


_CAPABILITY_QUESTION_PATTERNS = (
    "can you ", "could you ", "will you ", "would you ", "are you able to ",
    "do you ", "is it possible to ", "how do i ", "how can i ",
)

_STOP_WORDS = frozenset({"a", "an", "the", "to", "of", "for", "in", "on", "at", "is", "be", "i", "my", "me", "it", "this", "that", "with", "and", "or"})


def _looks_like_write(message: str) -> bool:
    lowered = message.lower()
    return any(word in lowered for word in _WRITE_HINT_WORDS)


def _is_capability_question(message: str) -> bool:
    """Return True when the message asks IF something can be done, with no actual content."""
    lowered = message.lower().strip()
    if not any(lowered.startswith(p) for p in _CAPABILITY_QUESTION_PATTERNS):
        return False
    # Capability question with real content still looks like a write: "can you add: go to gym"
    # Reject only when the message is short and contains no colon or quoted payload.
    return ":" not in lowered and '"' not in lowered and len(lowered.split()) <= 10


def _content_grounded(content: str, message: str) -> bool:
    """Ensure extracted content is actually based on the message, not hallucinated."""
    content_words = {w for w in content.lower().split() if w not in _STOP_WORDS and len(w) > 2}
    message_words = set(message.lower().split())
    # No meaningful content words → cannot be grounded
    if not content_words:
        return False
    return bool(content_words & message_words)


def _llm_write_intent(message: str) -> IntentResult | None:
    if not _looks_like_write(message):
        return None
    if _is_capability_question(message):
        return None

    schema = (
        'Schema: {"intent": "task" | "reminder" | "note" | "memory" | "none", '
        '"content": string, "time": string | null}. '
        'Use "memory" only for long-term facts the assistant must permanently know about the user (e.g., preferences, relations, birthdays, factual dates). '
        'Use "reminder" for time-bound nudges to alert the user at a specific future time. Use "task" for actionable to-dos to CREATE. '
        'Use "note" for short observations to SAVE. '
        '"time" should be a natural phrase like "tomorrow at 3pm" or null if no time is implied. '
        'CRITICAL: Only extract content that is EXPLICITLY stated in the message. '
        'Do NOT invent, infer, or hallucinate content. '
        'If the message expresses intent to create something but provides NO actual content/description, '
        'reply {"intent": "none", "content": "", "time": null}. '
        'If the user is asking to VIEW, LIST, CHECK, or SHOW existing items, '
        'reply {"intent": "none", "content": "", "time": null}. '
        'If the message is a question, capability check, or general chat, '
        'reply {"intent": "none", "content": "", "time": null}.'
    )
    payload = call_json(f"User message: {message!r}", schema_hint=schema, max_tokens=120)
    if not payload:
        return None

    intent = (payload.get("intent") or "").lower().strip()
    content = (payload.get("content") or "").strip()
    time_hint = (payload.get("time") or None) if payload.get("time") else None

    if intent == "none" or not content:
        return None
    if not _content_grounded(content, message):
        log.debug("LLM write intent rejected: content %r not grounded in %r", content, message)
        return None

    if intent == "task":
        return IntentResult("write", perform_create_task(content))
    if intent == "note":
        return IntentResult("write", perform_create_note(content))
    if intent == "memory":
        return IntentResult("write", perform_create_memory(content))
    if intent == "reminder":
        composed = content
        if time_hint:
            composed = f"{content} at {time_hint}" if "at" not in time_hint.lower() else f"{content} {time_hint}"
        return IntentResult("write", perform_create_reminder(composed))

    return None


# ── Action intents: email / calendar (LLM-extracted) ────────────────────────

_EMAIL_ACTION_KW = (
    # send variants
    "send email", "send an email", "send mail", "send a mail",
    "shoot an email", "shoot a mail",
    # email to / mail to
    "email to", "mail to",
    # compose variants (mail or email)
    "compose email", "compose an email", "compose mail", "compose a mail",
    # draft variants
    "draft email", "draft an email", "draft mail", "draft a mail",
    # write variants
    "write email", "write an email", "write mail", "write a mail",
)
_CALENDAR_ACTION_KW = (
    "schedule meeting", "schedule a meeting", "create event", "create a meeting",
    "book meeting", "book a meeting", "set up meeting", "set up a meeting",
    "setup meeting", "setup a meeting", "set a meeting", "set meeting",
    "create an event", "add meeting", "schedule call", "schedule a call",
    "book a call", "book call",
)


def _llm_action_intent(message: str) -> IntentResult | None:
    lowered = message.lower()
    is_email = any(kw in lowered for kw in _EMAIL_ACTION_KW)
    is_calendar = any(kw in lowered for kw in _CALENDAR_ACTION_KW)
    if not is_email and not is_calendar:
        return None

    now = current_local_time()

    if is_email:
        schema = (
            'Schema: {"action": "send_email" | "draft_email" | "none", '
            '"to": string, "subject": string, "body": string}. '
            'Extract the recipient (to), generate a concise subject line, '
            'and write a complete professional email body based on the user\'s intent. '
            'Use "draft_email" ONLY when the user explicitly says "draft". '
            'For "compose", "write", "send", or any other phrasing → use "send_email". '
            'If no valid email recipient is present, return {"action": "none", "to": "", "subject": "", "body": ""}.'
        )
    else:
        schema = (
            'Schema: {"action": "create_event" | "none", "title": string, '
            '"start": string, "end": string, "attendees": [string] | null, "description": string}. '
            f'Current datetime: {now.strftime("%Y-%m-%dT%H:%M:%S")} IST (Asia/Kolkata, UTC+05:30). '
            'start and end must be ISO 8601 with seconds (YYYY-MM-DDTHH:MM:SS). '
            'Default event duration is 60 minutes when not stated. '
            'attendees is a list of email addresses or null. '
            'If time cannot be determined, return {"action": "none"}.'
        )

    payload = call_json(f"User message: {message!r}", schema_hint=schema, max_tokens=280)
    if not payload or payload.get("action") == "none":
        return None

    action = (payload.get("action") or "").strip()

    if action in ("send_email", "draft_email"):
        to = (payload.get("to") or "").strip()
        subject = (payload.get("subject") or "").strip()
        body = (payload.get("body") or "").strip()
        if not subject:
            return None
        if action == "draft_email":
            return IntentResult("tool", {"tool": "gmail_draft", "args": {"to": to, "subject": subject, "body": body}})
        # "send_email" — check if user explicitly said "send" or used compose/write
        _EXPLICIT_SEND_KW = ("send email", "send an email", "send mail", "send a mail",
                             "email to", "mail to", "shoot an email", "shoot a mail")
        explicit_send = any(kw in lowered for kw in _EXPLICIT_SEND_KW)
        return IntentResult("tool", {
            "tool": "gmail_send",
            "args": {"to": to, "subject": subject, "body": body},
            "confirm_first": not explicit_send,
        })

    if action == "create_event":
        title = (payload.get("title") or "").strip()
        start = (payload.get("start") or "").strip()
        end = (payload.get("end") or "").strip()
        attendees = payload.get("attendees") or None
        description = (payload.get("description") or "").strip()

        if not title:
            return None

        if not start or not end:
            # Ask for the missing time instead of failing silently
            ask = f"When should I schedule '{title}'? Please provide a date and time."
            return IntentResult("read", {
                "kind": "calendar_need_info",
                "message": ask,
                "partial": {"title": title, "attendees": attendees, "description": description},
            })

        return IntentResult("tool", {
            "tool": "calendar_create",
            "args": {
                "title": title,
                "start_datetime": start,
                "end_datetime": end,
                "description": description,
                "attendees": attendees,
            },
            "confirm_first": True,
        })

    return None


def _complete_partial_calendar(partial: dict, message: str) -> dict | None:
    """Try to extract start/end time from a follow-up message to complete a partial calendar event."""
    now = current_local_time()
    title = partial.get("title", "")
    schema = (
        'Schema: {"action": "done" | "none", "start": string, "end": string}. '
        f'Current datetime: {now.strftime("%Y-%m-%dT%H:%M:%S")} IST (Asia/Kolkata, UTC+05:30). '
        f'Event title: "{title}". '
        'Extract start and end from the message (ISO 8601, YYYY-MM-DDTHH:MM:SS). '
        'Default duration is 60 minutes if end is not stated. '
        'If time is still unclear, return {"action": "none"}.'
    )
    payload = call_json(f"Time info: {message!r}", schema_hint=schema, max_tokens=120)
    if not payload or payload.get("action") == "none":
        return None
    start = (payload.get("start") or "").strip()
    end = (payload.get("end") or "").strip()
    if not start or not end:
        return None
    return {
        "title": title,
        "start_datetime": start,
        "end_datetime": end,
        "description": partial.get("description", ""),
        "attendees": partial.get("attendees"),
    }


# ── Protocol detection ──────────────────────────────────────────────────────


def _protocol_intent(message: str) -> IntentResult | None:
    lowered = message.lower()
    protocol: str | None = None
    if "coding mode" in lowered or "developer mode" in lowered or "generate code" in lowered or "debug" in lowered:
        protocol = "coding"
    elif "architecture" in lowered:
        protocol = "architecture"
    elif "optimization" in lowered or "simulation" in lowered:
        protocol = "optimization"
    elif "security" in lowered or "sentinel" in lowered:
        protocol = "security"
    elif "focus mode" in lowered:
        protocol = "focus"

    if protocol:
        return IntentResult("protocol", {"protocol": protocol})
    return None


# ── Tool detection (calculator, weather, search, system command) ────────────


_MATH_PATTERN = re.compile(r"^[\s\d\.\+\-\*\/\(\)\^%]+$")
_WEATHER_RE = re.compile(r"\bweather\s+(?:in|for|at)?\s*([A-Za-z][A-Za-z\s,\-]{1,40})", re.IGNORECASE)
_SEARCH_RE = re.compile(r"^\s*(?:search|google|look up|web search)\s+(?:for\s+)?(.+)$", re.IGNORECASE)
_RUN_RE = re.compile(r"^\s*(?:run command|exec|shell)\s+(.+)$", re.IGNORECASE)
_GH_ISSUES_RE = re.compile(
    r"\b(?:show|list|get)\s+(?:open\s+)?issues\s+(?:on|for|in)\s+([A-Za-z0-9_\.\-]+/[A-Za-z0-9_\.\-]+)",
    re.IGNORECASE,
)


def _tool_intent(message: str) -> IntentResult | None:
    stripped = message.strip().rstrip(".?!")

    gh = _GH_ISSUES_RE.search(stripped)
    if gh:
        return IntentResult("tool", {"tool": "get_open_issues", "args": {"repo": gh.group(1).strip()}})

    weather = _WEATHER_RE.search(stripped)
    if weather:
        city = weather.group(1).strip().rstrip(",")
        return IntentResult("tool", {"tool": "get_weather", "args": {"city": city}})

    search = _SEARCH_RE.match(stripped)
    if search:
        return IntentResult("tool", {"tool": "web_search", "args": {"query": search.group(1).strip()}})

    run = _RUN_RE.match(stripped)
    if run:
        return IntentResult("tool", {"tool": "run_system_command", "args": {"cmd": run.group(1).strip()}})

    if stripped.lower().startswith(("calc ", "calculate ", "compute ")):
        expr = stripped.split(" ", 1)[1].strip()
        return IntentResult("tool", {"tool": "calculator", "args": {"expression": expr}})

    if _MATH_PATTERN.match(stripped) and any(op in stripped for op in "+-*/^"):
        return IntentResult("tool", {"tool": "calculator", "args": {"expression": stripped}})

    return None


# ── Public API ──────────────────────────────────────────────────────────────


def classify(message: str) -> IntentResult:
    for handler in (_social_intent, _write_intent_regex, _read_intent, _tool_intent, _llm_action_intent, _protocol_intent, _llm_write_intent):
        try:
            result = handler(message)
        except Exception:
            log.exception("Intent handler %s failed", handler.__name__)
            result = None
        if result is not None:
            log.debug("Intent %s matched (%s)", result.type, handler.__name__)
            return result

    return IntentResult("llm", {})
