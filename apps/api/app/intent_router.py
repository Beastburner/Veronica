from __future__ import annotations

import logging
import os
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

# Connectivity / alive-check patterns — never need the LLM
_ALIVE_RE = re.compile(
    r"(?:hello[\s,?!]+){2,}"           # "hello, hello" or "hello hello hello"
    r"|can\s+you\s+hear\s+me"
    r"|are\s+you\s+(?:there|online|working|alive|up)"
    r"|(?:test(?:ing)?[\s,?!]*){2,}"   # "testing testing"
    r"|is\s+(?:this\s+)?(?:thing\s+)?(?:on|working)"
    r"|(?:veronica|hey)\s*\?+$",
    re.IGNORECASE,
)

_SOCIAL_REPLIES = ("Hey.", "Sup.", "Hey, what's good.", "Yo.", "Hey there.")
_social_reply_index = 0


def _social_intent(message: str) -> IntentResult | None:
    global _social_reply_index
    stripped = message.strip()
    if _ALIVE_RE.search(stripped):
        return IntentResult("social", {"message": "Online. What do you need?"})
    if _SOCIAL_RE.match(stripped):
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
    is_commit = any(kw in lowered for kw in _GH_COMMIT_KW)
    if not is_email and not is_calendar and not is_commit:
        return None

    if is_commit:
        from app.config import settings as _cfg
        schema = (
            'Schema: {"action": "commit_file" | "none", "repo": string, "path": string, '
            '"content": string, "message": string, "branch": string}. '
            f'Default owner is "{_cfg.github_username}". If repo has no owner prefix add it. '
            'path is the file path inside the repo (e.g. "README.md", "notes/todo.txt"). '
            'content is the full text to write into the file. '
            'message is the git commit message. '
            'branch defaults to "main" if not stated. '
            'If any of repo, path, content, or message cannot be determined, return {"action": "none"}.'
        )
        payload = call_json(f"User message: {message!r}", schema_hint=schema, max_tokens=300)
        if not payload or payload.get("action") == "none":
            return None
        repo = (payload.get("repo") or "").strip()
        path = (payload.get("path") or "").strip()
        content = (payload.get("content") or "").strip()
        commit_msg = (payload.get("message") or "").strip()
        branch = (payload.get("branch") or "main").strip()
        if not repo or not path or not content or not commit_msg:
            return None
        if "/" not in repo:
            from app.config import settings as _cfg2
            repo = f"{_cfg2.github_username}/{repo}"
        return IntentResult("tool", {
            "tool": "github_commit_file",
            "args": {"repo": repo, "path": path, "content": content, "message": commit_msg, "branch": branch},
            "confirm_first": True,
        })

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
            'attendees is a list of attendee names or emails — use the person\'s exact name if you do not know their email. '
            'NEVER invent or guess email addresses. '
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
        # Resolve name → email if no @ present
        if to and "@" not in to:
            try:
                from app.contacts import resolve_name_to_email
                resolved = resolve_name_to_email(to)
                if resolved:
                    to = resolved
            except Exception:
                pass
        if action == "draft_email":
            return IntentResult("tool", {"tool": "gmail_draft", "args": {"to": to, "subject": subject, "body": body}})
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

        # Resolve attendee names → emails
        if attendees:
            try:
                from app.contacts import resolve_attendees
                attendees = resolve_attendees(attendees)
            except Exception:
                pass

        if not start or not end:
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
_SEARCH_RE = re.compile(r"^\s*(?:can\s+(?:you\s+)?|please\s+)?(?:search|google|look up|web\s*search|web\s*scrape|scrape)\s+(?:for\s+|about\s+)?(.+)$", re.IGNORECASE)
_RUN_RE = re.compile(r"^\s*(?:run command|exec|shell)\s+(.+)$", re.IGNORECASE)
_GH_ISSUES_RE = re.compile(
    r"\b(?:show|list|get)\s+(?:open\s+)?issues\s+(?:on|for|in)\s+([A-Za-z0-9_\.\-]+/[A-Za-z0-9_\.\-]+)",
    re.IGNORECASE,
)
_SCRAPE_RE = re.compile(
    r"(?:web\s*scrape|scrape|fetch(?:\s+content)?(?:\s+from)?|get\s+content\s+from|extract(?:\s+text)?(?:\s+from)?|"
    r"read(?:\s+(?:the\s+)?(?:page|article|website|webpage))?(?:\s+(?:at|from))?|"
    r"summarize(?:\s+(?:the\s+)?(?:page|article|website))?(?:\s+(?:at|from))?)\s+"
    r"(?:this\s+|the\s+|it\s+)?"  # allow "this/the/it" before the URL
    r"(https?://\S+)",
    re.IGNORECASE,
)
_SCRAPE_RE_POST = re.compile(
    r"(https?://\S+)\s+(?:web\s*scrape|scrape|summarize|read|fetch)",
    re.IGNORECASE,
)
# Habit patterns
_HABIT_LOG_RE = re.compile(
    r"(?:log|did|done|check\s*off|complete|mark(?:\s+done)?|finished?)\s+(?:habit\s+)?(.+)",
    re.IGNORECASE,
)
_HABIT_STATUS_RE = re.compile(
    r"(?:show|check|list|what(?:\'s|\s+are)?)\s+(?:my\s+)?habits?",
    re.IGNORECASE,
)
_HABIT_CREATE_RE = re.compile(
    r"(?:add|create|new|track)\s+(?:a\s+)?habit(?:\s+(?:called|named|for))?\s+(.+)",
    re.IGNORECASE,
)
# News — generic digest
_NEWS_RE = re.compile(
    r"(?:show|get|fetch|check|give\s+me|tell\s+me|what(?:\'s|\s+is)?)\s+(?:the\s+)?(?:news|digest|headlines?|top\s+stories?|latest\s+news)",
    re.IGNORECASE,
)
# Topic-specific news — "latest F1 news" / "news about Formula 1" → web_search
_TOPIC_NEWS_RE = re.compile(
    r"(?:latest|recent|top|current)\s+(.+?)\s+news"
    r"|(?:news|headlines?)\s+(?:about|for|on|regarding)\s+(.+)"
    r"|(?:check|get|show|fetch)\s+(?:the\s+)?(?:latest|recent)\s+news\s+(?:for|about|on)\s+(.+)",
    re.IGNORECASE,
)
# Pomodoro
_POMODORO_START_RE = re.compile(
    r"(?:start|begin|set)\s+(?:a\s+)?(?:pomodoro|focus\s+(?:timer|session)|timer)(?:\s+for\s+(.+))?",
    re.IGNORECASE,
)
_POMODORO_STOP_RE = re.compile(
    r"(?:stop|end|finish|cancel)\s+(?:the\s+)?(?:pomodoro|focus\s+timer|timer)",
    re.IGNORECASE,
)
_POMODORO_STATUS_RE = re.compile(
    r"(?:timer\s+status|how\s+(?:long\s+)?(?:is\s+)?(?:left|remaining)|pomodoro\s+status)",
    re.IGNORECASE,
)
# Planner
_PLAN_RE = re.compile(
    r"(?:plan(?:\s+for)?|break\s+(?:down|up)|decompose|help\s+me\s+(?:plan|build|create)|create\s+a\s+plan\s+for)[:\s]+(.+)",
    re.IGNORECASE,
)
# Clipboard
_CLIP_SAVE_RE = re.compile(
    r"(?:save\s+(?:to\s+)?clipboard|clip\s+this|remember\s+this\s+snippet)[:\s]+(.+)",
    re.IGNORECASE,
)
_CLIP_SEARCH_RE = re.compile(
    r"(?:find\s+(?:in\s+)?clipboard|search\s+(?:my\s+)?(?:clips?|clipboard)|get\s+(?:from\s+)?clipboard)[:\s]+(.+)",
    re.IGNORECASE,
)
# System stats
_SYSSTAT_RE = re.compile(
    r"(?:system\s+stats?|cpu\s+usage|ram\s+usage|disk\s+(?:usage|space)|resource\s+usage|how\s+(?:much\s+)?(?:cpu|ram|memory))",
    re.IGNORECASE,
)
# GitHub PRs — accepts owner/repo OR bare repo name (resolves owner from settings)
_GH_PRS_RE = re.compile(
    r"\b(?:show|list|get)\s+(?:open\s+)?(?:pull\s*requests?|prs?)"
    r"(?:\s+(?:on|for|in)\s+([A-Za-z0-9_\.\-]+(?:/[A-Za-z0-9_\.\-]+)?))?",
    re.IGNORECASE,
)
_GH_COMMITS_RE = re.compile(
    r"\b(?:show|list|get|check|fetch|latest|recent)\s+(?:the\s+)?(?:latest\s+|recent\s+)?(?:github\s+)?commits?"
    r"(?:\s+(?:on|for|in|to)\s+([A-Za-z0-9_\.\-]+(?:/[A-Za-z0-9_\.\-]+)?))?",
    re.IGNORECASE,
)
_GH_REPO_RE = re.compile(
    r"\b(?:repo\s+stats?|stats?\s+(?:for|of|on)\s+(?:repo\s+)?)([A-Za-z0-9_\.\-]+(?:/[A-Za-z0-9_\.\-]+)?)",
    re.IGNORECASE,
)
# "my github" / "my repos" / "my issues"
_GH_MY_ISSUES_RE = re.compile(
    r"\bmy\s+(?:github\s+)?(?:open\s+)?issues",
    re.IGNORECASE,
)
_GH_MY_PRS_RE = re.compile(
    r"\bmy\s+(?:github\s+)?(?:open\s+)?(?:pull\s*requests?|prs?)",
    re.IGNORECASE,
)
_GH_MY_COMMITS_RE = re.compile(
    r"\bmy\s+(?:recent\s+|latest\s+)?(?:github\s+)?commits?"
    r"|\blatest\s+(?:github\s+)?commit"
    r"|\b(?:check|show|get)\s+(?:my\s+)?(?:latest|last|recent)\s+(?:github\s+)?commits?",
    re.IGNORECASE,
)
# Spotify
_SPOTIFY_CURRENT_RE = re.compile(
    r"what(?:['']?s| is)\s+(?:playing|the\s+(?:current|playing)\s+track|on\s+spotify)|current\s+(?:song|track)",
    re.IGNORECASE,
)
_SPOTIFY_TOGGLE_RE = re.compile(
    r"(?:play|pause|resume)\s+(?:spotify|the\s+music|music|playback)",
    re.IGNORECASE,
)
_SPOTIFY_NEXT_RE = re.compile(
    r"(?:next|skip)\s+(?:song|track|spotify)?(?:\s+on\s+spotify)?",
    re.IGNORECASE,
)
_SPOTIFY_PREV_RE = re.compile(
    r"(?:previous|prev|go\s+back)\s+(?:song|track|spotify)?",
    re.IGNORECASE,
)
_SPOTIFY_VOLUME_RE = re.compile(
    r"(?:set|change)\s+(?:spotify\s+)?(?:volume|vol)\s+(?:to\s+)?(\d{1,3})",
    re.IGNORECASE,
)
_SPOTIFY_PLAY_RE = re.compile(
    r"(?:play|put\s+on)\s+(.+?)(?:\s+(?:on|in)\s+spotify)?$",
    re.IGNORECASE,
)
_SPOTIFY_PLAY_EXCLUDES = re.compile(
    r"^(?:music|spotify|the\s+music|playback|a\s+song|some\s+music|something)$",
    re.IGNORECASE,
)
# WhatsApp
_WA_STATUS_RE = re.compile(
    r"(?:whatsapp|wa)\s+(?:status|connected?|online|running)",
    re.IGNORECASE,
)
_WA_MESSAGES_RE = re.compile(
    r"(?:show|get|check|read)\s+(?:my\s+)?(?:whatsapp|wa)\s+(?:messages?|chats?|inbox)",
    re.IGNORECASE,
)
_WA_SEND_RE = re.compile(
    r"(?:send\s+(?:a\s+)?(?:whatsapp|wa)\s+(?:message\s+)?(?:to\s+)?|whatsapp\s+|message\s+(?:on\s+whatsapp\s+)?)"
    r"(\+?[\d][\d\s\-]{6,14})"   # phone number
    r"[\s:,]+(.+)",
    re.IGNORECASE,
)
# Name-based WA send — "send whatsapp to Parth Soni saying hi"
_WA_SEND_NAME_RE = re.compile(
    r"(?:send\s+(?:a\s+)?(?:whatsapp|wa)\s+(?:message\s+)?to\s+|whatsapp\s+(?:message\s+)?to\s+)"
    r"([A-Za-z][A-Za-z\s]{1,40}?)"
    r"(?:\s+saying\s+|\s+that\s+|\s*:\s*|\s+with(?:\s+message)?\s*:\s*)"
    r"(.+)",
    re.IGNORECASE,
)
_WA_SEND_KW = (
    "send whatsapp", "send a whatsapp", "whatsapp message", "send wa",
    "message on whatsapp", "text on whatsapp", "whatsapp to",
)
# GitHub issue creation
_GH_CREATE_ISSUE_RE = re.compile(
    r"(?:create|open|raise|file|new)\s+(?:a\s+)?(?:github\s+)?issue"
    r"(?:\s+(?:on|in|for)\s+([A-Za-z0-9_\.\-]+(?:/[A-Za-z0-9_\.\-]+)?))?"
    r"[\s:,]+(.+)",
    re.IGNORECASE,
)
_GH_COMMIT_KW = (
    "commit to github", "commit to repo", "commit file", "push file",
    "create file in", "update file in", "push to", "commit to",
    "make a commit", "make commit",
)
# Notion
_NOTION_SEARCH_RE = re.compile(
    r"(?:search|find|look\s+up)\s+(?:in\s+)?notion[:\s]+(.+)",
    re.IGNORECASE,
)
_NOTION_SYNC_RE = re.compile(
    r"(?:sync|push)\s+notes?\s+to\s+notion",
    re.IGNORECASE,
)
# System alerts
_SYS_ALERTS_RE = re.compile(
    r"(?:system\s+alerts?|resource\s+alerts?|threshold\s+alerts?|show\s+alerts?)",
    re.IGNORECASE,
)


def _resolve_repo(name: str | None) -> str:
    from app.config import settings
    owner = settings.github_username
    if not name:
        return f"{owner}/{settings.github_default_repo}"
    if "/" in name:
        return name
    return f"{owner}/{name}"


def _tool_intent(message: str) -> IntentResult | None:
    stripped = message.strip().rstrip(".?!")

    if _GH_MY_ISSUES_RE.search(stripped):
        from app.config import settings
        return IntentResult("tool", {"tool": "get_open_issues", "args": {"repo": f"{settings.github_username}/Veronica"}})

    if _GH_MY_PRS_RE.search(stripped):
        return IntentResult("tool", {"tool": "github_list_prs", "args": {"repo": _resolve_repo(None)}})

    if _GH_MY_COMMITS_RE.search(stripped):
        return IntentResult("tool", {"tool": "github_recent_commits", "args": {"repo": _resolve_repo(None)}})

    m = _GH_PRS_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "github_list_prs", "args": {"repo": _resolve_repo(m.group(1))}})

    m = _GH_COMMITS_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "github_recent_commits", "args": {"repo": _resolve_repo(m.group(1))}})

    m = _GH_REPO_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "github_repo_stats", "args": {"repo": _resolve_repo(m.group(1))}})

    if _SPOTIFY_CURRENT_RE.search(stripped):
        return IntentResult("tool", {"tool": "spotify_current", "args": {}})

    if _SPOTIFY_TOGGLE_RE.search(stripped):
        return IntentResult("tool", {"tool": "spotify_toggle", "args": {}})

    if _SPOTIFY_NEXT_RE.search(stripped):
        return IntentResult("tool", {"tool": "spotify_skip_next", "args": {}})

    if _SPOTIFY_PREV_RE.search(stripped):
        return IntentResult("tool", {"tool": "spotify_skip_prev", "args": {}})

    m = _SPOTIFY_VOLUME_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "spotify_volume", "args": {"volume_pct": int(m.group(1))}})

    m = _SPOTIFY_PLAY_RE.search(stripped)
    if m:
        query = m.group(1).strip()
        if not _SPOTIFY_PLAY_EXCLUDES.match(query):
            return IntentResult("tool", {"tool": "spotify_play", "args": {"query": query}})

    if _WA_STATUS_RE.search(stripped):
        return IntentResult("tool", {"tool": "whatsapp_status", "args": {}})

    if _WA_MESSAGES_RE.search(stripped):
        return IntentResult("tool", {"tool": "whatsapp_messages", "args": {}})

    m = _WA_SEND_RE.search(stripped)
    if m:
        number = re.sub(r"[\s\-]", "", m.group(1))
        text = m.group(2).strip()
        return IntentResult("tool", {
            "tool": "whatsapp_send",
            "args": {"to": number, "text": text},
            "confirm_first": True,
        })

    m = _WA_SEND_NAME_RE.search(stripped)
    if m:
        name = m.group(1).strip()
        text = m.group(2).strip()
        return IntentResult("tool", {
            "tool": "whatsapp_send",
            "args": {"to": name, "text": text},
            "confirm_first": True,
        })

    m = _GH_CREATE_ISSUE_RE.search(stripped)
    if m:
        repo = _resolve_repo(m.group(1))
        title = m.group(2).strip()
        return IntentResult("tool", {
            "tool": "create_issue",
            "args": {"repo": repo, "title": title},
            "confirm_first": True,
        })

    m = _NOTION_SEARCH_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "notion_search", "args": {"query": m.group(1).strip()}})

    if _NOTION_SYNC_RE.search(stripped):
        return IntentResult("tool", {"tool": "notion_sync_push", "args": {"database_id": os.getenv("NOTION_DATABASE_ID", "")}})

    if _SYS_ALERTS_RE.search(stripped):
        return IntentResult("tool", {"tool": "system_alerts", "args": {}})

    gh = _GH_ISSUES_RE.search(stripped)
    if gh:
        return IntentResult("tool", {"tool": "get_open_issues", "args": {"repo": gh.group(1).strip()}})

    scrape = _SCRAPE_RE.search(stripped)
    if scrape:
        return IntentResult("tool", {"tool": "web_scrape", "args": {"url": scrape.group(1).strip()}})
    
    scrape_post = _SCRAPE_RE_POST.search(stripped)
    if scrape_post:
        return IntentResult("tool", {"tool": "web_scrape", "args": {"url": scrape_post.group(1).strip()}})

    # Habits
    if _HABIT_STATUS_RE.search(stripped):
        return IntentResult("tool", {"tool": "habit_status", "args": {}})
    m = _HABIT_CREATE_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "habit_create", "args": {"name": m.group(1).strip()}})
    m = _HABIT_LOG_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "habit_log", "args": {"name": m.group(1).strip()}})

    # Topic-specific news → web_search for live results
    m = _TOPIC_NEWS_RE.search(stripped)
    if m:
        topic = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        return IntentResult("tool", {"tool": "web_search", "args": {"query": f"latest {topic} news"}})

    # Generic news digest (HN, Verge, etc.)
    if _NEWS_RE.search(stripped):
        return IntentResult("tool", {"tool": "news_digest", "args": {}})

    # Pomodoro
    if _POMODORO_STATUS_RE.search(stripped):
        return IntentResult("tool", {"tool": "pomodoro_status", "args": {}})
    if _POMODORO_STOP_RE.search(stripped):
        return IntentResult("tool", {"tool": "pomodoro_stop", "args": {}})
    m = _POMODORO_START_RE.search(stripped)
    if m:
        label = (m.group(1) or "Focus session").strip()
        return IntentResult("tool", {"tool": "pomodoro_start", "args": {"label": label}})

    # Planner
    m = _PLAN_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "plan_goal", "args": {"goal": m.group(1).strip(), "auto_create": False}})

    # Clipboard
    m = _CLIP_SAVE_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "clipboard_save", "args": {"content": m.group(1).strip()}})
    m = _CLIP_SEARCH_RE.search(stripped)
    if m:
        return IntentResult("tool", {"tool": "clipboard_search", "args": {"query": m.group(1).strip()}})

    # System stats
    if _SYSSTAT_RE.search(stripped):
        return IntentResult("tool", {"tool": "system_stats", "args": {}})

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
