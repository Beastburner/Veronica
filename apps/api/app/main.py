import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse

from app.agent import generate_response, model_health, stream_response, summarize_turns
from app.bootstrap import ensure_ollama
from app.config import settings
from app.context.manager import BoundedContextWindow
from app.db import delete_pending_action, init_db, load_pending_action, save_pending_action
from app.intent_router import classify
from app.life_log import list_entries as list_log_entries, log_entry
from app.memory.hot_memory import hot_cache
from app.models import (
    ChatRequest,
    ChatResponse,
    NoteCreateRequest,
    ProtocolRequest,
    ReminderCreateRequest,
    ReminderUpdateRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
)
from app.monitoring.memory_monitor import MemoryMonitor
from app.oauth_store import (
    delete_oauth_token,
    get_connected_services,
    load_oauth_token,
    save_oauth_token,
)
from app.storage import (
    build_assistant_context,
    build_daily_briefing,
    create_memory,
    create_note,
    create_reminder,
    create_task,
    delete_memory,
    delete_note,
    delete_reminder,
    delete_task,
    get_recent_summary,
    list_action_logs,
    list_memories,
    list_notes,
    list_reminders,
    list_summary_sessions_with_excess,
    list_tasks,
    log_action,
    replace_session_summaries,
    save_conversation_summary,
    take_session_summaries,
    update_reminder_status,
    update_task_status,
)
from app.system_alert import start_watchdog, stop_watchdog
from app.tools import REGISTRY as TOOL_REGISTRY
from app.tools import execute_tool
from app.transcribe import transcribe_bytes
from app.transcribe import warm_up as warm_up_whisper

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("veronica")


async def _compose_wa_reply(messages: list[dict], contact_name: str) -> str:
    """Auto-compose a contextual WhatsApp reply based on recent conversation."""
    sender = (settings.sender_name or "Parth").split()[0]

    # messages come newest-first from Node.js
    last_msg = next(
        ((m.get("body") or "").strip() for m in messages if not m.get("fromMe")),
        "",
    )
    if not last_msg:
        return ""

    context_lines = []
    for m in reversed(messages[:8]):
        who = "You" if m.get("fromMe") else contact_name
        body = (m.get("body") or "").strip()
        if body:
            context_lines.append(f"{who}: {body}")
    conversation = "\n".join(context_lines)

    from app.llm_client import call_chat
    system = (
        f"You are {sender}, writing a WhatsApp reply to {contact_name}. "
        "Output ONLY the reply message — no labels, no quotes, no explanation. "
        "Casual and natural, 1-3 sentences, first person. Match the tone of the conversation. "
        "NEVER mention Veronica, AI, or any automated system. "
        "CRITICAL: Only use facts that are EXPLICITLY visible in the conversation. "
        "Do NOT invent or assume any actions, states, or context about the sender "
        "(e.g. do not say 'I already did X' or 'I'm on Y' unless the conversation proves it). "
        "If the last message needs a simple acknowledgement or follow-up question, do that — "
        "don't pad with invented context."
    )
    user_prompt = (
        f"Conversation:\n{conversation}\n\n"
        f"Reply to their last message: \"{last_msg}\""
    )
    text, status = await asyncio.to_thread(
        call_chat,
        [{"role": "system", "content": system}, {"role": "user", "content": user_prompt}],
        temperature=0.8,
        max_tokens=120,
    )
    return (text or "").strip()


async def _resolve_wa_recipient(to: str) -> tuple[str, str, bool]:
    """
    Resolve a WhatsApp recipient to (display_label, value_to_send, number_verified).
    number_verified=False means we couldn't confirm the number — caller should warn but still allow.
    value_to_send is always set: a confirmed +number, or the original name for Node.js to resolve.
    """
    import re as _re
    is_number = bool(_re.match(r"^\+?[\d\s\-\(\)]+$", to.strip()) and
                     len(_re.sub(r"\D", "", to)) >= 7)
    if is_number:
        digits = _re.sub(r"[\s\-\(\)]", "", to).lstrip("+")
        return (f"+{digits}", f"+{digits}", True)

    # Try WhatsApp contacts API (live)
    try:
        from app.whatsapp_client import wa_search_contact
        result = await wa_search_contact(to)
        if result.get("ok"):
            contact = result["contact"]
            name = contact.get("name", to)
            number = (contact.get("number") or "").strip().lstrip("+")
            if number:
                # Persist to local DB so future lookups work even when WhatsApp is offline
                try:
                    from app.contacts import upsert_contact
                    placeholder = f"{name.lower().replace(' ', '.')}@whatsapp.local"
                    upsert_contact(name, placeholder, source="whatsapp", phone=f"+{number}")
                except Exception:
                    pass
                return (f"{name} (+{number})", f"+{number}", True)
            # Group or contact found by name — use the WhatsApp chat ID directly
            chat_id = (contact.get("id") or "").strip()
            if chat_id:
                label = f"{name} (group)" if contact.get("isGroup") else name
                return (label, chat_id, True)
    except Exception:
        pass

    # Fallback: local contacts DB phone field
    try:
        from app.contacts import resolve_name_to_phone
        phone = resolve_name_to_phone(to)
        if phone:
            return (f"{to} ({phone})", phone, True)
    except Exception:
        pass

    # Could not verify number — pass name through to Node.js and warn user
    return (to, to, False)


def _compact_old_summaries(threshold: int = 5) -> int:
    sessions = list_summary_sessions_with_excess(threshold)
    compacted = 0
    for sid in sessions:
        rows = take_session_summaries(sid)
        if len(rows) < threshold:
            continue
        joined = "\n".join(r["summary"] for r in rows)
        condensed = summarize_turns(
            [{"role": "system", "content": joined}],
            mode="JARVIS",
        )
        if condensed:
            replace_session_summaries(sid, condensed)
            compacted += 1
    return compacted


# state -> code_verifier (PKCE)
_oauth_states: dict[str, str] = {}


_whatsapp_proc: subprocess.Popen | None = None
# session_id → (display_name, resolved_value) of last successfully sent WA contact
_last_wa_contact: dict[str, tuple[str, str]] = {}


def _whatsapp_already_running() -> bool:
    import httpx as _httpx
    try:
        r = _httpx.get("http://localhost:3001/status", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False


def _find_node() -> str | None:
    """Find the node binary — handles nvm/fnm/system installs on Windows."""
    import shutil
    # Direct PATH lookup first
    node = shutil.which("node")
    if node:
        return node
    # Common Windows install locations when PATH is not inherited
    candidates = [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
        Path.home() / "AppData" / "Roaming" / "nvm" / "current" / "node.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return str(c)
    return None


def _launch_whatsapp() -> None:
    global _whatsapp_proc
    if _whatsapp_already_running():
        log.info("WhatsApp service already running on port 3001 — reusing session")
        return
    wa_dir = Path(__file__).resolve().parent.parent.parent / "whatsapp"
    if not (wa_dir / "index.js").exists():
        log.warning("WhatsApp service not found at %s — skipping auto-start", wa_dir)
        return
    if not (wa_dir / "node_modules").exists():
        log.warning("WhatsApp service deps missing — run: cd apps/whatsapp && npm install")
        return
    node = _find_node()
    if not node:
        log.warning("node not found in PATH or common install dirs — WhatsApp service not started")
        return
    try:
        _whatsapp_proc = subprocess.Popen(
            [node, "index.js"],
            cwd=str(wa_dir),
            stdout=None,
            stderr=None,
        )
        log.info("WhatsApp service started (pid %d) via %s", _whatsapp_proc.pid, node)
    except Exception:
        log.exception("failed to start WhatsApp service")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if not settings.groq_api_key:
        status = await asyncio.to_thread(ensure_ollama)
        log.info("ollama bootstrap: %s", status)
    else:
        log.info("Groq configured — skipping Ollama auto-start (kept as offline fallback only)")
    asyncio.create_task(asyncio.to_thread(warm_up_whisper))
    asyncio.create_task(asyncio.to_thread(_run_compaction))
    asyncio.create_task(asyncio.to_thread(_launch_whatsapp))
    from app import scheduler as _sched
    await asyncio.to_thread(_sched.start)
    start_watchdog()
    yield
    stop_watchdog()
    await asyncio.to_thread(_sched.stop)


def _run_compaction() -> None:
    try:
        n = _compact_old_summaries()
        if n:
            log.info("compacted summary rows for %d session(s)", n)
    except Exception:
        log.exception("summary compaction failed")


app = FastAPI(title="VERONICA API", version="0.4.0", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info("%s %s -> %s in %.1fms", request.method, request.url.path, response.status_code, elapsed_ms)
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.exception("%s %s crashed in %.1fms", request.method, request.url.path, elapsed_ms)
        raise


CONTEXT_WINDOWS: OrderedDict[str, BoundedContextWindow] = OrderedDict()
MAX_SESSIONS = 200
MONITOR = MemoryMonitor(warning_mb=400, critical_mb=800)

_CONFIRM_RE = re.compile(
    r"^\s*(yes|yep|yeah|sure|ok|okay|go\s*ahead|send\s*it|send\s*this|"
    r"send|confirm|do\s*it|proceed|absolutely)\s*[.!?,]*\s*$",
    re.IGNORECASE,
)
_CANCEL_RE = re.compile(
    r"^\s*(no|nope|cancel|don'?t\s+send|do\s+not\s+send|abort|"
    r"stop|never\s*mind|discard|skip)\s*[.!?,]*\s*$",
    re.IGNORECASE,
)


async def _handle_pending_confirmation(
    session_id: str, message: str
) -> tuple[str, str] | None:
    """
    Handle pending email/calendar confirmations and partial calendar completions.
    Returns (response_text, provider_status) or None if not applicable.
    """
    pending = load_pending_action(session_id)
    if not pending:
        return None

    ptype = pending.get("type", "email_confirm")
    msg = message.strip()

    # ── Partial calendar: user is providing missing time info ────────────────
    if ptype == "calendar_partial":
        if _CANCEL_RE.match(msg):
            delete_pending_action(session_id)
            return ("Meeting cancelled.", "cancelled")
        from app.intent_router import _complete_partial_calendar
        completed = _complete_partial_calendar(pending["partial"], message)
        if completed:
            save_pending_action(session_id, {
                "type": "calendar_confirm",
                "tool": "calendar_create",
                "args": completed,
            })
            title = completed["title"]
            start = completed["start_datetime"]
            attendees = completed.get("attendees") or []
            with_str = f"\nAttendees: {', '.join(attendees)}" if attendees else ""
            preview = f"Title: {title}\nTime: {start}{with_str}"
            return (f"Here's the meeting, sir:\n\n{preview}\n\nSchedule this?", "calendar_preview")
        title = pending["partial"].get("title", "the meeting")
        return (f"Still unclear — when exactly should I schedule '{title}'? Give me a date and time.", "calendar_clarification")

    # ── Confirm / cancel for email or calendar ───────────────────────────────
    if _CONFIRM_RE.match(msg):
        delete_pending_action(session_id)
        tool_args = dict(pending["args"])
        # Strip metadata fields that aren't tool parameters
        tool_args.pop("display_name", None)
        # For calendar: resolve attendee names → emails, drop still-unresolved ones
        if ptype == "calendar_confirm" and tool_args.get("attendees"):
            from app.contacts import resolve_name_to_email
            resolved = []
            for a in tool_args["attendees"]:
                if "@" in a:
                    resolved.append(a)
                else:
                    email = resolve_name_to_email(a)
                    if email:
                        resolved.append(email)
            tool_args["attendees"] = resolved or None
        result = await execute_tool(pending["tool"], tool_args)
        if result.get("ok"):
            if ptype == "calendar_confirm":
                title = pending["args"].get("title", "Meeting")
                start = pending["args"].get("start_datetime", "")
                detail = result.get("result", {})
                meet = detail.get("meet_link", "")
                cal_url = detail.get("html_link", "")
                past_warn = result.get("past_warning", "")
                extra = f"\nMeet: {meet}" if meet else "\n(No Meet link — personal Gmail account)"
                extra += f"\nCalendar: {cal_url}" if cal_url else ""
                extra += past_warn
                return (f"Meeting '{title}' scheduled for {start}.{extra}", "meeting_scheduled")
            if ptype == "wa_confirm":
                to = pending["args"].get("to", "")
                display_name = pending["args"].get("display_name", to)
                _last_wa_contact[session_id] = (display_name, to)
                return (f"WhatsApp message sent to {display_name}, sir.", "wa_sent")
            if ptype == "gh_issue_confirm":
                r = result.get("result") or {}
                num = r.get("number", "")
                url = r.get("url", "")
                title = r.get("title", "")
                return (f"Issue #{num} '{title}' created, sir. {url}", "gh_issue_created")
            if ptype == "gh_commit_confirm":
                r = result.get("result") or {}
                sha = r.get("sha", "")
                path = r.get("path", "")
                url = r.get("url", "")
                return (f"Committed — {sha} · {path}. {url}", "gh_committed")
            to = pending["args"].get("to", "")
            subj = pending["args"].get("subject", "")
            return (f"Email sent to {to} — \"{subj}\".", "email_sent")
        return (f"Failed: {result.get('error', 'unknown error')}", "action_failed")

    if _CANCEL_RE.match(msg):
        delete_pending_action(session_id)
        _cancel_msgs = {
            "calendar_confirm": "Meeting cancelled.",
            "wa_confirm": "WhatsApp message discarded.",
            "gh_issue_confirm": "Issue creation cancelled.",
            "gh_commit_confirm": "Commit cancelled.",
        }
        return (_cancel_msgs.get(ptype, "Draft discarded."), "cancelled")

    return None


def _build_search_context(intent) -> dict | None:
    """
    When the intent is a semantic search, return a system context message so the LLM
    can synthesize an answer using both its own knowledge and the user's stored notes.
    Notes are presented as user-authored content, not verified facts.
    """
    if intent.type != "llm":
        return None
    results = intent.payload.get("search_results")
    topic = intent.payload.get("search_topic")
    if results is None or topic is None:
        return None
    if results:
        lines = "\n".join(f"- [{r['source']}] {r['content']}" for r in results)
        content = (
            f"The user asked about \"{topic}\". "
            f"Here are their stored notes/memories on this topic (user-authored, not verified facts — "
            f"cross-check against your own knowledge and flag anything incorrect):\n{lines}\n\n"
            f"Synthesize a complete answer combining what you know and what is stored. "
            f"If a stored note is factually wrong, say so directly."
        )
    else:
        content = (
            f"The user asked about \"{topic}\". "
            f"No stored notes found on this topic. Answer from your own knowledge."
        )
    return {"role": "system", "content": content}


def get_or_create_window(session_id: str) -> BoundedContextWindow:
    if session_id in CONTEXT_WINDOWS:
        CONTEXT_WINDOWS.move_to_end(session_id)
        return CONTEXT_WINDOWS[session_id]
    window = BoundedContextWindow(max_tokens=4000, max_messages=10)
    CONTEXT_WINDOWS[session_id] = window
    if len(CONTEXT_WINDOWS) > MAX_SESSIONS:
        CONTEXT_WINDOWS.popitem(last=False)
    return window


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "online", "system": "VERONICA"}


@app.get("/health/model")
async def health_model() -> dict[str, str | bool]:
    return model_health()


@app.get("/system/memory")
async def memory_status() -> dict[str, object]:
    return {
        "stats": MONITOR.get_stats(),
        "thresholds": MONITOR.check_thresholds(),
        "trend": MONITOR.get_trend(),
        "cache": hot_cache.stats(),
        "active_sessions": len(CONTEXT_WINDOWS),
    }


@app.post("/system/memory/collect")
async def force_collection() -> dict[str, object]:
    return MONITOR.force_gc()


@app.post("/system/memory/clear_cache")
async def clear_hot_cache() -> dict[str, object]:
    hot_cache.clear()
    return {"status": "cleared", "cache": hot_cache.stats()}


def _tool_direct_reply(tool: str, result: dict) -> str | None:
    """Return a canned VERONICA reply for tools that don't need LLM formatting."""
    if not result.get("ok"):
        err = result.get("error", "unknown error")
        if tool == "whatsapp_send":
            return f"WhatsApp failed: {err}"
        if tool in ("web_search", "news_topic"):
            q = result.get("query") or result.get("topic") or "that query"
            return f"No results found for '{q}', sir."
        labels = {
            "spotify_play": "Spotify", "spotify_toggle": "Spotify",
            "spotify_skip_next": "Spotify", "spotify_skip_prev": "Spotify",
            "spotify_volume": "Spotify", "spotify_current": "Spotify",
            "whatsapp_status": "WhatsApp", "whatsapp_messages": "WhatsApp",
            "system_stats": "System", "system_alerts": "System",
            "pomodoro_start": "Pomodoro", "pomodoro_stop": "Pomodoro", "pomodoro_status": "Pomodoro",
        }
        label = labels.get(tool)
        if label:
            return f"Sir, {label} returned an error: {err}"
        return None

    r = result.get("result") or {}

    if tool == "spotify_play":
        track = r.get("playing", "")
        artist = r.get("artist", "")
        return f"Playing '{track}' by {artist}, sir." if artist else f"Playing '{track}', sir."

    if tool == "spotify_toggle":
        action = r.get("action", "toggled")
        return "Paused, sir." if action == "paused" else "Resuming playback, sir."

    if tool == "spotify_skip_next":
        return "Skipping to next track, sir."

    if tool == "spotify_skip_prev":
        return "Going back to previous track, sir."

    if tool == "spotify_volume":
        vol = r.get("volume_pct", "?")
        return f"Volume set to {vol}%, sir."

    if tool == "spotify_current":
        if not r.get("playing"):
            return "Nothing playing on Spotify right now, sir."
        track = r.get("track", "Unknown")
        artist = r.get("artist", "")
        vol = r.get("volume")
        vol_str = f" — volume {vol}%" if vol is not None else ""
        return f"Currently playing '{track}' by {artist}{vol_str}, sir."

    if tool == "whatsapp_send":
        if not result.get("ok"):
            err = result.get("error", "unknown error")
            return f"WhatsApp send failed: {err}"
        contact = result.get("to") or result.get("contact", "")
        return f"WhatsApp message sent{f' to {contact}' if contact else ''}, sir."

    if tool == "whatsapp_status":
        ready = result.get("ready", False)
        return "WhatsApp is connected and ready, sir." if ready else "WhatsApp is not connected, sir."

    if tool == "whatsapp_search_contact":
        contact = result.get("contact", {})
        name = contact.get("name", "")
        number = contact.get("number", "")
        return f"Found: {name} — +{number}, sir." if number else f"Contact '{result.get('error', 'not found')}', sir."

    if tool == "whatsapp_conversation":
        msgs = result.get("messages") or []
        if not msgs:
            contact = result.get("contact", "them")
            return f"No messages found with {contact}, sir."
        lines = []
        for m in msgs[:10]:
            who = "You" if m.get("fromMe") else (m.get("fromName") or m.get("from") or "Them")
            body = (m.get("body") or "").strip()
            if body:
                lines.append(f"{who}: {body}")
        return "\n".join(lines) if lines else "No messages found, sir."

    if tool == "whatsapp_contacts":
        contacts = result.get("contacts") or []
        if not contacts:
            return "No WhatsApp contacts found, sir."
        lines = ", ".join(f"{c['name']} (+{c['number']})" for c in contacts[:5] if c.get("number"))
        total = result.get("total", len(contacts))
        suffix = f" (+{total - 5} more)" if total > 5 else ""
        return f"WhatsApp contacts: {lines}{suffix}, sir."

    if tool == "create_issue":
        r2 = result.get("result") or {}
        num = r2.get("number", "")
        url = r2.get("url", "")
        title = r2.get("title", "")
        return f"Issue #{num} '{title}' created, sir. {url}"

    if tool == "pomodoro_start":
        label = r.get("label", "Focus session")
        dur = r.get("duration_minutes", 25)
        return f"Pomodoro started: '{label}' for {dur} minutes, sir."

    if tool == "pomodoro_stop":
        return "Pomodoro session ended, sir."

    if tool == "pomodoro_status":
        if not r.get("active"):
            return "No active Pomodoro session, sir."
        label = r.get("label", "Session")
        remaining = r.get("remaining_minutes")
        return f"'{label}' — {remaining} minute(s) remaining, sir." if remaining else f"'{label}' is running, sir."

    if tool == "system_stats":
        cpu = r.get("cpu_percent", "?")
        ram = r.get("ram_percent", "?")
        disk = r.get("disk_percent", "?")
        return f"System status — CPU: {cpu}%, RAM: {ram}%, Disk: {disk}%, sir."

    if tool == "system_alerts":
        alerts = result.get("result") or []
        if not alerts:
            return "No system alerts triggered, sir."
        summary = "; ".join(f"{a['resource']} at {a['value']:.0f}%" for a in alerts[:3])
        return f"Sir, {len(alerts)} alert(s): {summary}."

    if tool == "contact_save_phone":
        name = result.get("name", "")
        phone = result.get("phone", "")
        created = result.get("created", False)
        action = "saved new contact" if created else "updated contact"
        return f"{action.capitalize()} — {name}: {phone}, sir."

    return None


def _direct_response(
    *,
    mode,
    text: str,
    provider_status: str,
    suggested: list[str],
) -> ChatResponse:
    return ChatResponse(
        mode=mode,
        response=text,
        protocol=None,
        provider_status=provider_status,
        memory_updates=[],
        suggested_actions=suggested,
        tool_plan=[],
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> ChatResponse:
    if not session_id:
        session_id = str(uuid.uuid4())
    window = get_or_create_window(session_id)

    window.add_message("user", request.message)
    if float(window.get_context()["utilization_pct"]) > 90:
        window.compress_old_messages(keep_last=3)

    # ── Pending email/calendar confirmation — must run BEFORE intent routing ──
    pending_outcome = await _handle_pending_confirmation(session_id, request.message)
    if pending_outcome is not None:
        text, pstatus = pending_outcome
        response = _direct_response(mode=request.mode, text=text, provider_status=pstatus, suggested=[])
        window.add_message("assistant", text)
        log_action("VERONICA", f"chat:{request.mode.value}:{pstatus}", "low", True, text[:240])
        return response

    intent = classify(request.message)

    try:
        from app.behavior import record_interaction
        record_interaction(request.message, intent.type, request.mode.value)
    except Exception:
        pass

    if intent.type == "write":
        kind = intent.payload.get("kind", "item")
        message_text = intent.payload.get("message", "")
        await hot_cache.invalidate_pattern(f"{kind}s:")
        response = _direct_response(
            mode=request.mode,
            text=message_text,
            provider_status=f"direct_write:{kind}",
            suggested=[
                "Review the relevant panel to confirm the new entry.",
                "Ask VERONICA to list stored items if you want a quick check.",
            ],
        )
        window.add_message("assistant", message_text)
        log_action("VERONICA", f"chat:{request.mode.value}:write:{kind}", "low", True, message_text[:240])
        return response

    if intent.type in ("read", "social"):
        message_text = intent.payload.get("message", "")
        # Store partial calendar so the follow-up time message can complete it
        if intent.payload.get("kind") == "calendar_need_info" and intent.payload.get("partial"):
            save_pending_action(session_id, {
                "type": "calendar_partial",
                "partial": intent.payload["partial"],
            })
        response = _direct_response(
            mode=request.mode,
            text=message_text,
            provider_status="direct_data",
            suggested=[
                "Add or update tasks and reminders from the dashboard panels.",
                "Use the daily briefing to review current priorities.",
            ],
        )
        window.add_message("assistant", message_text)
        log_action("VERONICA", f"chat:{request.mode.value}:{intent.type}", "low", True, message_text[:240])
        return response

    tool_results: list[dict] = []
    if intent.type == "tool":
        tool_name = intent.payload.get("tool")
        args = intent.payload.get("args") or {}

        # ── Confirm-before-act flow (email + calendar + whatsapp + github issue) ─
        if intent.payload.get("confirm_first"):
            # Resolve __last__ sentinel before confirm preview
            if tool_name == "whatsapp_send" and args.get("to") == "__last__":
                last = _last_wa_contact.get(session_id)
                if last:
                    args = {**args, "to": last[1]}
                else:
                    text = "Who should I reply to? I don't have a recent WhatsApp contact on record."
                    return _direct_response(mode=request.mode, text=text, provider_status="wa_no_context", suggested=[])
            if tool_name == "gmail_send":
                to = args.get("to", "")
                subj = args.get("subject", "")
                body = args.get("body", "")
                preview = f"To: {to}\nSubject: {subj}\n\n{body}"
                save_pending_action(session_id, {"type": "email_confirm", "tool": "gmail_send", "args": args})
                text = f"Here's the draft, sir:\n\n{preview}\n\nSend this?"
                pstatus = "draft_preview"
            elif tool_name == "calendar_create":
                title = args.get("title", "")
                start = args.get("start_datetime", "")
                attendees = args.get("attendees") or []
                _fake_domains = {"example.com", "example.org", "test.com", "fake.com"}
                display_attendees = []
                for a in attendees:
                    if "@" in a and a.split("@")[1].lower() in _fake_domains:
                        display_attendees.append(a.split("@")[0].replace(".", " ").title())
                    else:
                        display_attendees.append(a)
                with_str = f"\nAttendees: {', '.join(display_attendees)}" if display_attendees else ""
                preview = f"Title: {title}\nTime: {start}{with_str}"
                clean_args = dict(args)
                clean_args["attendees"] = display_attendees or None
                save_pending_action(session_id, {"type": "calendar_confirm", "tool": "calendar_create", "args": clean_args})
                text = f"Here's the meeting, sir:\n\n{preview}\n\nSchedule this?"
                pstatus = "calendar_preview"
            elif tool_name == "whatsapp_send":
                raw_to = args.get("to", "")
                msg = args.get("text", "")
                display, resolved, resolved_ok = await _resolve_wa_recipient(raw_to)
                resolved_args = {**args, "to": resolved, "display_name": display}
                save_pending_action(session_id, {"type": "wa_confirm", "tool": "whatsapp_send", "args": resolved_args})
                if resolved_ok:
                    text = f"Send this WhatsApp message, sir?\n\nTo: {display}\n\n{msg}"
                else:
                    text = (f"Send this WhatsApp message, sir?\n\n"
                            f"To: {display} (number not verified — double-check this is the right person)\n\n{msg}")
                pstatus = "wa_preview"
            elif tool_name == "create_issue":
                repo = args.get("repo", "")
                title = args.get("title", "")
                save_pending_action(session_id, {"type": "gh_issue_confirm", "tool": "create_issue", "args": args})
                text = f"Create this GitHub issue, sir?\n\nRepo: {repo}\nTitle: {title}"
                pstatus = "gh_issue_preview"
            elif tool_name == "github_commit_file":
                repo = args.get("repo", "")
                path = args.get("path", "")
                message = args.get("message", "")
                branch = args.get("branch", "main")
                content_preview = (args.get("content") or "")[:120]
                if len(args.get("content", "")) > 120:
                    content_preview += "…"
                save_pending_action(session_id, {"type": "gh_commit_confirm", "tool": "github_commit_file", "args": args})
                text = f"Commit this to GitHub, sir?\n\nRepo: {repo}\nFile: {path}\nBranch: {branch}\nMessage: {message}\n\n{content_preview}"
                pstatus = "gh_commit_preview"
            else:
                text = None
                pstatus = "preview"
            if text:
                response = _direct_response(mode=request.mode, text=text, provider_status=pstatus,
                                            suggested=["Yes, commit it", "Cancel"])
                window.add_message("assistant", text)
                log_action("VERONICA", f"chat:{request.mode.value}:{pstatus}", "low", True, text[:240])
                return response

        # Resolve __last__ for conversation fetch too
        if tool_name == "whatsapp_conversation" and args.get("contact") == "__last__":
            last = _last_wa_contact.get(session_id)
            if last:
                args = {**args, "contact": last[0]}
            else:
                text = "Who do you want to check messages with? I don't have a recent contact on record."
                return _direct_response(mode=request.mode, text=text, provider_status="wa_no_context", suggested=[])

        # Strip reply_context flag before executing (not a real tool parameter)
        _reply_ctx = False
        if tool_name == "whatsapp_conversation":
            _reply_ctx = args.pop("reply_context", False)

        if tool_name in TOOL_REGISTRY:
            result = await execute_tool(tool_name, args)
            tool_results.append(result)
            if tool_name == "gmail_draft" and result.get("ok"):
                save_pending_action(session_id, {"type": "email_confirm", "tool": "gmail_send", "args": args})

            # reply_context: auto-compose WA reply regardless of direct_text
            if _reply_ctx:
                contact = args.get("contact", "")
                if contact and contact != "__last__":
                    _last_wa_contact[session_id] = (contact, contact)
                msgs = result.get("messages") or []
                if msgs:
                    composed = await _compose_wa_reply(msgs, contact)
                    if composed:
                        display, resolved, resolved_ok = await _resolve_wa_recipient(contact)
                        resolved_args = {"to": resolved, "text": composed, "display_name": display}
                        save_pending_action(session_id, {"type": "wa_confirm", "tool": "whatsapp_send", "args": resolved_args})
                        last_msg = next((m.get("body", "") for m in msgs if not m.get("fromMe")), "")
                        convo_line = f"Last from {contact}: \"{last_msg}\"\n\n" if last_msg else ""
                        num_tag = "" if resolved_ok else " (number not verified)"
                        reply_preview = f"{convo_line}Suggested reply to {display}{num_tag}:\n\n{composed}\n\nSend this?"
                        window.add_message("assistant", reply_preview)
                        log_action("VERONICA", f"chat:{request.mode.value}:wa_reply_preview", "low", True, reply_preview[:240])
                        return _direct_response(mode=request.mode, text=reply_preview, provider_status="wa_preview", suggested=["Yes, send it", "Cancel"])
                    fallback = f"Got the conversation with {contact} but couldn't compose a reply. What would you like to say?"
                else:
                    fallback = f"No messages found with {contact}, sir. What would you like to say to them?"
                window.add_message("assistant", fallback)
                log_action("VERONICA", f"chat:{request.mode.value}:wa_reply_fallback", "low", True, fallback[:240])
                return _direct_response(mode=request.mode, text=fallback, provider_status="wa_reply_fallback", suggested=[])

            # Short-circuit: tools with canned replies bypass the LLM entirely
            direct_text = _tool_direct_reply(tool_name, result)
            if direct_text:
                window.add_message("assistant", direct_text)
                log_action("VERONICA", f"chat:{request.mode.value}:tool_direct:{tool_name}", "low", True, direct_text[:240])
                return _direct_response(mode=request.mode, text=direct_text, provider_status="tool_direct", suggested=[])

    forced_protocol = intent.payload.get("protocol") if intent.type == "protocol" else None

    history = window.get_context_messages()
    recent_summary = get_recent_summary(session_id)
    if recent_summary:
        history = [{"role": "system", "content": f"Session summary: {recent_summary}"}] + history

    storage_context = build_assistant_context(request.message)

    # Semantic search intent: inject retrieved notes as context for the LLM to synthesize
    search_ctx = _build_search_context(intent)
    if search_ctx:
        storage_context = [search_ctx] + storage_context

    enriched = request.model_copy(update={"history": storage_context + history})

    response = await generate_response(enriched, forced_protocol=forced_protocol, tool_results=tool_results)
    window.add_message("assistant", response.response)

    log_action("VERONICA", f"chat:{request.mode.value}", "low", True, response.response[:240])

    if len(window.messages) >= 8:
        turns = window.get_context_messages()[-6:]
        summary = await asyncio.to_thread(summarize_turns, turns, request.mode.value)
        if summary:
            save_conversation_summary(session_id=session_id, summary=summary)
    return response


@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    session_id: str | None = Header(default=None, alias="X-Session-ID"),
):
    if not session_id:
        session_id = str(uuid.uuid4())
    window = get_or_create_window(session_id)

    window.add_message("user", request.message)
    if float(window.get_context()["utilization_pct"]) > 90:
        window.compress_old_messages(keep_last=3)

    async def emit_single(text: str, provider_status: str) -> "StreamingResponse":
        async def gen():
            yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done",
                        "mode": request.mode.value,
                        "response": text,
                        "protocol": None,
                        "provider_status": provider_status,
                    }
                )
                + "\n\n"
            )

        return StreamingResponse(gen(), media_type="text/event-stream")

    # ── Pending confirmation FIRST — before any intent routing ───────────────
    pending_outcome = await _handle_pending_confirmation(session_id, request.message)
    if pending_outcome is not None:
        text, pstatus = pending_outcome
        window.add_message("assistant", text)
        log_action("VERONICA", f"chat:{request.mode.value}:{pstatus}", "low", True, text[:240])
        return await emit_single(text, pstatus)

    intent = classify(request.message)

    try:
        from app.behavior import record_interaction
        record_interaction(request.message, intent.type, request.mode.value)
    except Exception:
        pass

    if intent.type == "write":
        kind = intent.payload.get("kind", "item")
        message_text = intent.payload.get("message", "")
        await hot_cache.invalidate_pattern(f"{kind}s:")
        window.add_message("assistant", message_text)
        log_action("VERONICA", f"chat:{request.mode.value}:write:{kind}", "low", True, message_text[:240])
        return await emit_single(message_text, f"direct_write:{kind}")

    if intent.type in ("read", "social"):
        message_text = intent.payload.get("message", "")
        if intent.payload.get("kind") == "calendar_need_info" and intent.payload.get("partial"):
            save_pending_action(session_id, {
                "type": "calendar_partial",
                "partial": intent.payload["partial"],
            })
        window.add_message("assistant", message_text)
        log_action("VERONICA", f"chat:{request.mode.value}:{intent.type}", "low", True, message_text[:240])
        return await emit_single(message_text, "direct_data")

    tool_results: list[dict] = []
    if intent.type == "tool":
        tool_name = intent.payload.get("tool")
        args = intent.payload.get("args") or {}

        # ── Confirm-before-act flow (email + calendar + whatsapp + github issue, stream) ─
        if intent.payload.get("confirm_first"):
            if tool_name == "whatsapp_send" and args.get("to") == "__last__":
                last = _last_wa_contact.get(session_id)
                if last:
                    args = {**args, "to": last[1]}
                else:
                    text = "Who should I reply to? I don't have a recent WhatsApp contact on record."
                    return await emit_single(text, "wa_no_context")
            if tool_name == "gmail_send":
                to = args.get("to", "")
                subj = args.get("subject", "")
                body = args.get("body", "")
                preview = f"To: {to}\nSubject: {subj}\n\n{body}"
                save_pending_action(session_id, {"type": "email_confirm", "tool": "gmail_send", "args": args})
                text = f"Here's the draft, sir:\n\n{preview}\n\nSend this?"
                pstatus = "draft_preview"
            elif tool_name == "calendar_create":
                title = args.get("title", "")
                start = args.get("start_datetime", "")
                attendees = args.get("attendees") or []
                _fake_domains = {"example.com", "example.org", "test.com", "fake.com"}
                display_attendees = []
                for a in attendees:
                    if "@" in a and a.split("@")[1].lower() in _fake_domains:
                        display_attendees.append(a.split("@")[0].replace(".", " ").title())
                    else:
                        display_attendees.append(a)
                with_str = f"\nAttendees: {', '.join(display_attendees)}" if display_attendees else ""
                preview = f"Title: {title}\nTime: {start}{with_str}"
                clean_args = dict(args)
                clean_args["attendees"] = display_attendees or None
                save_pending_action(session_id, {"type": "calendar_confirm", "tool": "calendar_create", "args": clean_args})
                text = f"Here's the meeting, sir:\n\n{preview}\n\nSchedule this?"
                pstatus = "calendar_preview"
            elif tool_name == "whatsapp_send":
                raw_to = args.get("to", "")
                msg = args.get("text", "")
                display, resolved, resolved_ok = await _resolve_wa_recipient(raw_to)
                resolved_args = {**args, "to": resolved, "display_name": display}
                save_pending_action(session_id, {"type": "wa_confirm", "tool": "whatsapp_send", "args": resolved_args})
                if resolved_ok:
                    text = f"Send this WhatsApp message, sir?\n\nTo: {display}\n\n{msg}"
                else:
                    text = (f"Send this WhatsApp message, sir?\n\n"
                            f"To: {display} (number not verified — double-check this is the right person)\n\n{msg}")
                pstatus = "wa_preview"
            elif tool_name == "create_issue":
                repo = args.get("repo", "")
                title = args.get("title", "")
                save_pending_action(session_id, {"type": "gh_issue_confirm", "tool": "create_issue", "args": args})
                text = f"Create this GitHub issue, sir?\n\nRepo: {repo}\nTitle: {title}"
                pstatus = "gh_issue_preview"
            elif tool_name == "github_commit_file":
                repo = args.get("repo", "")
                path = args.get("path", "")
                message = args.get("message", "")
                branch = args.get("branch", "main")
                content_preview = (args.get("content") or "")[:120]
                if len(args.get("content", "")) > 120:
                    content_preview += "…"
                save_pending_action(session_id, {"type": "gh_commit_confirm", "tool": "github_commit_file", "args": args})
                text = f"Commit this to GitHub, sir?\n\nRepo: {repo}\nFile: {path}\nBranch: {branch}\nMessage: {message}\n\n{content_preview}"
                pstatus = "gh_commit_preview"
            else:
                text = None
                pstatus = "preview"
            if text:
                window.add_message("assistant", text)
                log_action("VERONICA", f"chat:{request.mode.value}:{pstatus}", "low", True, text[:240])
                return await emit_single(text, pstatus)

        # Resolve __last__ for conversation fetch
        if tool_name == "whatsapp_conversation" and args.get("contact") == "__last__":
            last = _last_wa_contact.get(session_id)
            if last:
                args = {**args, "contact": last[0]}
            else:
                text = "Who do you want to check messages with? I don't have a recent contact on record."
                return await emit_single(text, "wa_no_context")

        # Strip reply_context flag before executing
        _reply_ctx = False
        if tool_name == "whatsapp_conversation":
            _reply_ctx = args.pop("reply_context", False)

        if tool_name in TOOL_REGISTRY:
            result = await execute_tool(tool_name, args)
            tool_results.append(result)
            if tool_name == "gmail_draft" and result.get("ok"):
                save_pending_action(session_id, {"type": "email_confirm", "tool": "gmail_send", "args": args})

            # reply_context: auto-compose WA reply regardless of direct_text
            if _reply_ctx:
                contact = args.get("contact", "")
                if contact and contact != "__last__":
                    _last_wa_contact[session_id] = (contact, contact)
                msgs = result.get("messages") or []
                if msgs:
                    composed = await _compose_wa_reply(msgs, contact)
                    if composed:
                        display, resolved, resolved_ok = await _resolve_wa_recipient(contact)
                        resolved_args = {"to": resolved, "text": composed, "display_name": display}
                        save_pending_action(session_id, {"type": "wa_confirm", "tool": "whatsapp_send", "args": resolved_args})
                        last_msg = next((m.get("body", "") for m in msgs if not m.get("fromMe")), "")
                        convo_line = f"Last from {contact}: \"{last_msg}\"\n\n" if last_msg else ""
                        num_tag = "" if resolved_ok else " (number not verified)"
                        reply_preview = f"{convo_line}Suggested reply to {display}{num_tag}:\n\n{composed}\n\nSend this?"
                        window.add_message("assistant", reply_preview)
                        log_action("VERONICA", f"chat:{request.mode.value}:wa_reply_preview", "low", True, reply_preview[:240])
                        return await emit_single(reply_preview, "wa_preview")
                    fallback = f"Got the conversation with {contact} but couldn't compose a reply. What would you like to say?"
                else:
                    fallback = f"No messages found with {contact}, sir. What would you like to say to them?"
                window.add_message("assistant", fallback)
                return await emit_single(fallback, "wa_reply_fallback")

            # Short-circuit: tools with canned replies bypass the LLM entirely
            direct_text = _tool_direct_reply(tool_name, result)
            if direct_text:
                window.add_message("assistant", direct_text)
                log_action("VERONICA", f"chat:{request.mode.value}:tool_direct:{tool_name}", "low", True, direct_text[:240])
                return await emit_single(direct_text, "tool_direct")

    forced_protocol = intent.payload.get("protocol") if intent.type == "protocol" else None

    history = window.get_context_messages()
    recent_summary = get_recent_summary(session_id)
    if recent_summary:
        history = [{"role": "system", "content": f"Session summary: {recent_summary}"}] + history

    storage_context = build_assistant_context(request.message)

    # Semantic search intent: inject retrieved notes as context for the LLM to synthesize
    search_ctx = _build_search_context(intent)
    if search_ctx:
        storage_context = [search_ctx] + storage_context

    enriched = request.model_copy(update={"history": storage_context + history})

    async def event_stream():
        full_text = ""
        meta_payload: dict | None = None
        async for kind, payload in stream_response(
            enriched, forced_protocol=forced_protocol, tool_results=tool_results
        ):
            if kind == "token":
                full_text += payload
                yield f"data: {json.dumps({'type': 'token', 'content': payload})}\n\n"
            elif kind == "meta":
                meta_payload = payload
        if meta_payload is None:
            meta_payload = {
                "type": "done",
                "mode": request.mode.value,
                "response": full_text,
                "protocol": forced_protocol,
                "provider_status": "ok",
            }
        else:
            meta_payload = {**meta_payload, "type": "done"}
        window.add_message("assistant", full_text)
        log_action("VERONICA", f"chat:{request.mode.value}:stream", "low", True, full_text[:240])

        yield f"data: {json.dumps(meta_payload)}\n\n"

        if len(window.messages) >= 8:
            turns = window.get_context_messages()[-6:]
            summary = await asyncio.to_thread(summarize_turns, turns, request.mode.value)
            if summary:
                save_conversation_summary(session_id=session_id, summary=summary)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/protocols/deploy", response_model=ChatResponse)
async def deploy_protocol(
    request: ProtocolRequest,
    session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> ChatResponse:
    return await chat(
        ChatRequest(message=f"deploy protocol {request.command}", mode=request.mode),
        session_id=session_id,
    )


@app.get("/memory")
async def memory(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, object]:
    items, total = list_memories(skip=skip, limit=limit)
    return {
        "items": items,
        "pagination": {"skip": skip, "limit": limit, "total": total, "has_more": skip + limit < total},
    }


@app.post("/memory")
async def add_memory(payload: dict) -> dict[str, object]:
    content = (payload or {}).get("content", "").strip()
    tags = (payload or {}).get("tags", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    return {"status": "created", "item": create_memory(content, tags)}


@app.delete("/memory/{memory_id}")
async def remove_memory(memory_id: int) -> dict[str, object]:
    if not delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted"}


@app.get("/actions")
async def actions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
) -> dict[str, object]:
    items, total = list_action_logs(skip=skip, limit=limit)
    return {
        "items": items,
        "pagination": {"skip": skip, "limit": limit, "total": total, "has_more": skip + limit < total},
    }


@app.post("/notes")
async def add_note(request: NoteCreateRequest) -> dict[str, object]:
    note = create_note(request.content)
    await hot_cache.invalidate_pattern("notes:")
    if not note.get("duplicate"):
        log_entry("note_created", request.content[:80], request.content)
    return {"status": "duplicate" if note.get("duplicate") else "created", "item": note}


@app.get("/notes")
async def notes(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, object]:
    cache_key = f"notes:{skip}:{limit}"
    cached = await hot_cache.get(cache_key)
    if cached:
        return cached

    items, total = list_notes(skip=skip, limit=limit)
    payload = {
        "items": items,
        "pagination": {"skip": skip, "limit": limit, "total": total, "has_more": skip + limit < total},
    }
    await hot_cache.set(cache_key, payload)
    return payload


@app.post("/tasks")
async def add_task(request: TaskCreateRequest) -> dict[str, object]:
    task = create_task(request.description, request.priority)
    await hot_cache.invalidate_pattern("tasks:")
    if not task.get("duplicate"):
        log_entry("task_created", request.description, "", {"priority": request.priority})
    return {"status": "duplicate" if task.get("duplicate") else "created", "item": task}


@app.get("/tasks")
async def tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    cache_key = f"tasks:{skip}:{limit}:{status or 'all'}"
    cached = await hot_cache.get(cache_key)
    if cached:
        return cached

    items, total = list_tasks(skip=skip, limit=limit, status=status)
    payload = {
        "items": items,
        "pagination": {"skip": skip, "limit": limit, "total": total, "has_more": skip + limit < total},
    }
    await hot_cache.set(cache_key, payload)
    return payload


@app.patch("/tasks/{task_id}")
async def patch_task(task_id: int, request: TaskUpdateRequest) -> dict[str, object]:
    item = update_task_status(task_id, request.status)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await hot_cache.invalidate_pattern("tasks:")
    if request.status == "done" and item:
        log_entry("task_completed", item.get("description", "Task"), "", {"task_id": task_id})
    return {"status": "updated", "item": item}


@app.delete("/tasks/{task_id}")
async def remove_task(task_id: int) -> dict[str, object]:
    if not delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    await hot_cache.invalidate_pattern("tasks:")
    return {"status": "deleted"}


@app.post("/reminders")
async def add_reminder(request: ReminderCreateRequest) -> dict[str, object]:
    reminder = create_reminder(request.content, request.due_at)
    await hot_cache.invalidate_pattern("reminders:")
    return {"status": "duplicate" if reminder.get("duplicate") else "created", "item": reminder}


@app.get("/reminders")
async def reminders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    cache_key = f"reminders:{skip}:{limit}:{status or 'all'}"
    cached = await hot_cache.get(cache_key)
    if cached:
        return cached

    items, total = list_reminders(skip=skip, limit=limit, status=status)
    payload = {
        "items": items,
        "pagination": {"skip": skip, "limit": limit, "total": total, "has_more": skip + limit < total},
    }
    await hot_cache.set(cache_key, payload)
    return payload


@app.patch("/reminders/{reminder_id}")
async def patch_reminder(reminder_id: int, request: ReminderUpdateRequest) -> dict[str, object]:
    item = update_reminder_status(reminder_id, request.status)
    if item is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await hot_cache.invalidate_pattern("reminders:")
    return {"status": "updated", "item": item}


@app.delete("/reminders/{reminder_id}")
async def remove_reminder(reminder_id: int) -> dict[str, object]:
    if not delete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    await hot_cache.invalidate_pattern("reminders:")
    return {"status": "deleted"}


@app.delete("/notes/{note_id}")
async def remove_note(note_id: int) -> dict[str, object]:
    if not delete_note(note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    await hot_cache.invalidate_pattern("notes:")
    return {"status": "deleted"}


@app.get("/briefing/today")
async def today_briefing() -> dict[str, object]:
    return build_daily_briefing()


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, str]:
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio payload")
    suffix = ".webm"
    if audio.filename and "." in audio.filename:
        suffix = "." + audio.filename.rsplit(".", 1)[-1].lower()
    elif audio.content_type:
        if "wav" in audio.content_type:
            suffix = ".wav"
        elif "ogg" in audio.content_type:
            suffix = ".ogg"
        elif "mp4" in audio.content_type or "m4a" in audio.content_type:
            suffix = ".m4a"
    text = await asyncio.to_thread(transcribe_bytes, data, suffix)
    return {"text": text}


@app.post("/tts/edge")
async def tts_edge(payload: dict) -> StreamingResponse:
    """edge-tts synthesis — free, no API key, same voice as the wake listener."""
    from fastapi.responses import Response as _Resp
    text = (payload or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    from app.tts import synthesize
    audio = await synthesize(text)
    return _Resp(content=audio, media_type="audio/mpeg")


@app.post("/tts")
async def tts(payload: dict) -> StreamingResponse:
    """ElevenLabs TTS proxy. Falls back with HTTP 503 if not configured."""
    import httpx

    text = (payload or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip() or "21m00Tcm4TlvDq8ikWAM"  # Rachel
    if not api_key:
        raise HTTPException(status_code=503, detail="ELEVENLABS_API_KEY not configured")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    body = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75, "style": 0.2},
    }

    async def proxy():
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    detail = (await response.aread()).decode(errors="ignore")[:200]
                    log.warning("elevenlabs failed: %s %s", response.status_code, detail)
                    return
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(proxy(), media_type="audio/mpeg")


# ── OAuth ─────────────────────────────────────────────────────────────────

_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def _build_oauth_flow():
    if not settings.google_client_id or not settings.google_client_secret:
        return None
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore[import]

        return Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.google_redirect_uri],
                }
            },
            scopes=_GOOGLE_SCOPES,
            redirect_uri=settings.google_redirect_uri,
        )
    except ImportError:
        return None


@app.get("/oauth/status")
async def oauth_status() -> dict[str, object]:
    connected = get_connected_services()
    google_configured = bool(settings.google_client_id and settings.google_client_secret)
    return {
        "google_configured": google_configured,
        "connected": connected,
        "gmail": "google" in connected,
        "calendar": "google" in connected,
    }


def _pkce_pair() -> tuple[str, str]:
    """Generate a PKCE (code_verifier, code_challenge) pair."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@app.get("/oauth/google/start")
async def oauth_google_start():
    flow = _build_oauth_flow()
    if not flow:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to apps/api/.env",
        )

    state = secrets.token_urlsafe(16)
    verifier, challenge = _pkce_pair()
    _oauth_states[state] = verifier  # store verifier keyed by state

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return RedirectResponse(url=auth_url)


@app.get("/oauth/google/callback")
async def oauth_google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        log.warning("OAuth error from Google: %s", error)
        return RedirectResponse(url=f"{settings.frontend_url}?oauth_error={error}")

    if not code or state not in _oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth callback — missing code or state")

    verifier = _oauth_states.pop(state)

    flow = _build_oauth_flow()
    if not flow:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    try:
        # Allow HTTP in local development (oauthlib enforces HTTPS by default)
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
        flow.fetch_token(
            authorization_response=str(request.url),
            code_verifier=verifier,
        )
        creds = flow.credentials
        save_oauth_token("google", creds.to_json())
        log_entry("oauth_connected", "Google account connected", "Gmail and Calendar access granted")
    except Exception as exc:
        log.warning("OAuth token exchange failed: %s", exc)
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {exc}") from exc

    return RedirectResponse(url=f"{settings.frontend_url}?connected=google")


@app.delete("/oauth/google")
async def oauth_google_disconnect() -> dict[str, object]:
    deleted = delete_oauth_token("google")
    if deleted:
        log_entry("oauth_disconnected", "Google account disconnected")
    return {"status": "disconnected" if deleted else "not_connected"}


# ── Email ─────────────────────────────────────────────────────────────────


@app.get("/email/inbox")
async def email_inbox(max_results: int = Query(10, ge=1, le=50)) -> dict[str, object]:
    from app.gmail import list_inbox
    return await list_inbox(max_results=max_results)


@app.get("/email/message/{message_id}")
async def email_message(message_id: str) -> dict[str, object]:
    from app.gmail import read_email
    return await read_email(message_id=message_id)


@app.post("/email/send")
async def email_send(payload: dict) -> dict[str, object]:
    to = (payload or {}).get("to", "").strip()
    subject = (payload or {}).get("subject", "").strip()
    body = (payload or {}).get("body", "").strip()
    if not to or not subject:
        raise HTTPException(status_code=400, detail="to and subject required")
    from app.gmail import send_email
    result = await send_email(to=to, subject=subject, body=body)
    if result.get("ok"):
        log_entry("email_sent", f"Email to {to}", subject, {"to": to, "subject": subject})
    return result


@app.post("/email/draft")
async def email_draft(payload: dict) -> dict[str, object]:
    to = (payload or {}).get("to", "").strip()
    subject = (payload or {}).get("subject", "").strip()
    body = (payload or {}).get("body", "").strip()
    if not subject:
        raise HTTPException(status_code=400, detail="subject required")
    from app.gmail import draft_email
    return await draft_email(to=to, subject=subject, body=body)


@app.get("/email/search")
async def email_search(q: str = Query(..., min_length=1)) -> dict[str, object]:
    from app.gmail import search_email
    return await search_email(query=q)


# ── Calendar ──────────────────────────────────────────────────────────────


@app.get("/calendar/events")
async def calendar_events_route(days: int = Query(7, ge=1, le=30)) -> dict[str, object]:
    from app.gcal import list_events
    return await list_events(days_ahead=days)


@app.post("/calendar/events")
async def calendar_create_event(payload: dict) -> dict[str, object]:
    title = (payload or {}).get("title", "").strip()
    start = (payload or {}).get("start", "").strip()
    end = (payload or {}).get("end", "").strip()
    if not title or not start or not end:
        raise HTTPException(status_code=400, detail="title, start, end required")
    from app.gcal import create_event
    result = await create_event(
        title=title,
        start_datetime=start,
        end_datetime=end,
        description=(payload or {}).get("description", ""),
        attendees=(payload or {}).get("attendees"),
    )
    if result.get("ok"):
        log_entry("meeting_scheduled", title, f"Start: {start}", {"attendees": (payload or {}).get("attendees", [])})
    return result


@app.get("/calendar/freebusy")
async def calendar_freebusy(
    duration: int = Query(60, ge=15, le=480),
    days: int = Query(7, ge=1, le=14),
) -> dict[str, object]:
    from app.gcal import find_free_slot
    return await find_free_slot(duration_minutes=duration, days_ahead=days)


# ── Life Log ──────────────────────────────────────────────────────────────


@app.get("/life-log")
async def life_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    entry_type: str | None = Query(default=None),
) -> dict[str, object]:
    items, total = list_log_entries(skip=skip, limit=limit, entry_type=entry_type)
    return {
        "items": items,
        "pagination": {"skip": skip, "limit": limit, "total": total, "has_more": skip + limit < total},
    }


@app.post("/life-log")
async def add_life_log_entry(payload: dict) -> dict[str, object]:
    entry_type = (payload or {}).get("entry_type", "note").strip()
    title = (payload or {}).get("title", "").strip()
    content = (payload or {}).get("content", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    entry = log_entry(entry_type, title, content, (payload or {}).get("metadata"))
    return {"status": "created", "item": entry}


# ── Behavior / learning ────────────────────────────────────────────────────


@app.get("/behavior/insights")
async def behavior_insights() -> dict[str, object]:
    from app.behavior import get_behavior_summary, get_personalized_suggestions
    summary = get_behavior_summary()
    for mode in ("JARVIS", "FRIDAY", "VERONICA", "SENTINEL"):
        summary[f"suggestions_{mode.lower()}"] = get_personalized_suggestions(mode)
    return summary


# ── Habits ─────────────────────────────────────────────────────────────────


@app.get("/habits")
async def list_habits_route(include_archived: bool = Query(False)) -> dict[str, object]:
    from app.habits import list_habits, get_today_status
    if not include_archived:
        return {"items": get_today_status()}
    return {"items": list_habits(include_archived=True)}


@app.post("/habits")
async def create_habit_route(payload: dict) -> dict[str, object]:
    from app.habits import create_habit
    name = (payload or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    habit = create_habit(
        name,
        description=(payload or {}).get("description", ""),
        frequency=(payload or {}).get("frequency", "daily"),
        color=(payload or {}).get("color", "#22d3ee"),
    )
    return {"status": "created", "item": habit}


@app.post("/habits/{habit_id}/log")
async def log_habit_route(habit_id: int, payload: dict = {}) -> dict[str, object]:
    from app.habits import log_habit
    result = log_habit(habit_id, note=(payload or {}).get("note", ""))
    if not result.get("ok", True) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    log_entry("habit_logged", f"Habit {habit_id} logged", "")
    return {"status": "logged", "item": result}


@app.delete("/habits/{habit_id}")
async def archive_habit_route(habit_id: int) -> dict[str, object]:
    from app.habits import archive_habit
    if not archive_habit(habit_id):
        raise HTTPException(status_code=404, detail="Habit not found")
    return {"status": "archived"}


@app.get("/habits/{habit_id}/logs")
async def habit_logs_route(habit_id: int, limit: int = Query(30, ge=1, le=100)) -> dict[str, object]:
    from app.habits import get_habit_logs
    return {"items": get_habit_logs(habit_id, limit=limit)}


# ── News digest ─────────────────────────────────────────────────────────────


@app.get("/news/feeds")
async def list_feeds_route() -> dict[str, object]:
    from app.news import list_feeds
    return {"items": list_feeds()}


@app.post("/news/feeds")
async def add_feed_route(payload: dict) -> dict[str, object]:
    from app.news import add_feed
    url = (payload or {}).get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    return {"status": "created", "item": add_feed(
        url,
        title=(payload or {}).get("title", ""),
        category=(payload or {}).get("category", "general"),
    )}


@app.delete("/news/feeds/{feed_id}")
async def remove_feed_route(feed_id: int) -> dict[str, object]:
    from app.news import remove_feed
    if not remove_feed(feed_id):
        raise HTTPException(status_code=404, detail="Feed not found")
    return {"status": "deleted"}


@app.get("/news/digest")
async def news_digest_route(limit: int = Query(3, ge=1, le=10)) -> dict[str, object]:
    from app.news import get_digest
    return await asyncio.to_thread(get_digest, limit_per_feed=limit)


# ── Clipboard ───────────────────────────────────────────────────────────────


@app.get("/clipboard")
async def list_clipboard_route(
    limit: int = Query(20, ge=1, le=100),
    tag: str | None = Query(default=None),
) -> dict[str, object]:
    from app.clipboard import list_clips
    return {"items": list_clips(limit=limit, tag_filter=tag)}


@app.post("/clipboard")
async def save_clipboard_route(payload: dict) -> dict[str, object]:
    from app.clipboard import save_clip
    content = (payload or {}).get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content required")
    clip = save_clip(content, tags=(payload or {}).get("tags", ""), source=(payload or {}).get("source", "user"))
    return {"status": "saved", "item": clip}


@app.get("/clipboard/search")
async def search_clipboard_route(q: str = Query(..., min_length=1)) -> dict[str, object]:
    from app.clipboard import search_clips
    return {"items": search_clips(q)}


@app.delete("/clipboard/{clip_id}")
async def delete_clipboard_route(clip_id: int) -> dict[str, object]:
    from app.clipboard import delete_clip
    if not delete_clip(clip_id):
        raise HTTPException(status_code=404, detail="Clip not found")
    return {"status": "deleted"}


# ── Planner ─────────────────────────────────────────────────────────────────


@app.post("/planner/decompose")
async def planner_decompose(payload: dict) -> dict[str, object]:
    from app.planner import decompose_goal
    goal = (payload or {}).get("goal", "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal required")
    auto_create = bool((payload or {}).get("auto_create", False))
    result = await asyncio.to_thread(decompose_goal, goal, auto_create)
    return result


# ── Pomodoro ─────────────────────────────────────────────────────────────────


@app.post("/pomodoro/start")
async def pomodoro_start_route(payload: dict = {}) -> dict[str, object]:
    from app.pomodoro import start_timer
    label = (payload or {}).get("label", "Focus session")
    duration = int((payload or {}).get("duration_minutes", 25))
    return start_timer(label, duration)


@app.post("/pomodoro/stop")
async def pomodoro_stop_route(payload: dict = {}) -> dict[str, object]:
    from app.pomodoro import stop_timer
    completed = bool((payload or {}).get("completed", True))
    return stop_timer(completed)


@app.get("/pomodoro/status")
async def pomodoro_status_route() -> dict[str, object]:
    from app.pomodoro import get_status
    return get_status()


@app.get("/pomodoro/history")
async def pomodoro_history_route(limit: int = Query(10, ge=1, le=50)) -> dict[str, object]:
    from app.pomodoro import get_history
    return {"items": get_history(limit=limit)}


# ── System stats ─────────────────────────────────────────────────────────────


@app.get("/system/stats")
async def system_stats_route() -> dict[str, object]:
    import psutil
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": cpu,
        "ram_used_gb": round(mem.used / 1e9, 2),
        "ram_total_gb": round(mem.total / 1e9, 2),
        "ram_percent": mem.percent,
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
        "disk_percent": disk.percent,
    }


# ── Spotify OAuth ─────────────────────────────────────────────────────────

_spotify_pkce_states: dict[str, str] = {}


@app.get("/oauth/spotify/start")
async def oauth_spotify_start():
    client_id = settings.spotify_client_id
    if not client_id:
        raise HTTPException(status_code=503, detail="SPOTIFY_CLIENT_ID not configured in .env")
    from app.spotify import pkce_pair, SPOTIFY_SCOPES
    state = secrets.token_urlsafe(16)
    verifier, challenge = pkce_pair()
    _spotify_pkce_states[state] = verifier
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": settings.spotify_redirect_uri,
        "scope": SPOTIFY_SCOPES,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    from urllib.parse import urlencode
    url = "https://accounts.spotify.com/authorize?" + urlencode(params)
    return RedirectResponse(url=url)


@app.get("/oauth/spotify/callback")
async def oauth_spotify_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        return RedirectResponse(url=f"{settings.frontend_url}?oauth_error={error}")
    if not code or state not in _spotify_pkce_states:
        raise HTTPException(status_code=400, detail="Invalid Spotify OAuth callback")
    verifier = _spotify_pkce_states.pop(state)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.spotify_redirect_uri,
                    "client_id": settings.spotify_client_id,
                    "code_verifier": verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            r.raise_for_status()
            data = r.json()
        token = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_at": time.time() + data.get("expires_in", 3600),
        }
        save_oauth_token("spotify", json.dumps(token))
        log_entry("oauth_connected", "Spotify connected", "Music playback access granted")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Spotify OAuth failed: {exc}") from exc
    return RedirectResponse(url=f"{settings.frontend_url}?connected=spotify")


@app.delete("/oauth/spotify")
async def oauth_spotify_disconnect() -> dict:
    deleted = delete_oauth_token("spotify")
    return {"status": "disconnected" if deleted else "not_connected"}


# ── GitHub ────────────────────────────────────────────────────────────────


@app.get("/github/repos")
async def github_user_repos(limit: int = Query(30, ge=1, le=100)) -> dict:
    from app.github import list_user_repos
    return await list_user_repos(settings.github_username, limit)


@app.get("/github/{owner}/{repo}/pulls")
async def github_prs(owner: str, repo: str, state: str = Query("open")) -> dict:
    from app.github import list_pull_requests
    return await list_pull_requests(f"{owner}/{repo}", state)


@app.get("/github/{owner}/{repo}/pulls/{pr_number}")
async def github_pr(owner: str, repo: str, pr_number: int) -> dict:
    from app.github import get_pr_review
    return await get_pr_review(f"{owner}/{repo}", pr_number)


@app.get("/github/{owner}/{repo}/commits")
async def github_commits(owner: str, repo: str, limit: int = Query(5, ge=1, le=30)) -> dict:
    from app.github import list_recent_commits
    return await list_recent_commits(f"{owner}/{repo}", limit)


@app.get("/github/{owner}/{repo}/stats")
async def github_repo(owner: str, repo: str) -> dict:
    from app.github import get_repo_stats
    return await get_repo_stats(f"{owner}/{repo}")


# ── Spotify ───────────────────────────────────────────────────────────────


@app.get("/spotify/current")
async def spotify_current_route() -> dict:
    from app.spotify import get_current_track
    return await get_current_track()


@app.post("/spotify/play-pause")
async def spotify_toggle_route() -> dict:
    from app.spotify import spotify_play_pause
    return await spotify_play_pause()


@app.post("/spotify/next")
async def spotify_next_route() -> dict:
    from app.spotify import spotify_next
    return await spotify_next()


@app.post("/spotify/prev")
async def spotify_prev_route() -> dict:
    from app.spotify import spotify_prev
    return await spotify_prev()


@app.put("/spotify/volume")
async def spotify_volume_route(payload: dict) -> dict:
    from app.spotify import spotify_set_volume
    return await spotify_set_volume(int((payload or {}).get("volume_pct", 50)))


@app.post("/spotify/play")
async def spotify_play_route(payload: dict) -> dict:
    from app.spotify import spotify_search_play
    query = (payload or {}).get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    return await spotify_search_play(query)


@app.get("/spotify/status")
async def spotify_status_route() -> dict:
    from app.oauth_store import load_oauth_token
    token = load_oauth_token("spotify")
    configured = bool(settings.spotify_client_id)
    return {"connected": bool(token), "configured": configured}


# ── System alerts ──────────────────────────────────────────────────────────


@app.get("/system/alerts")
async def system_alerts_route(limit: int = Query(20, ge=1, le=100)) -> dict:
    from app.system_alert import get_alerts
    return {"items": get_alerts(limit)}


@app.get("/system/alerts/thresholds")
async def alert_thresholds_route() -> dict:
    from app.system_alert import get_thresholds
    return get_thresholds()


@app.put("/system/alerts/thresholds")
async def set_alert_thresholds_route(payload: dict) -> dict:
    from app.system_alert import set_thresholds
    return set_thresholds(
        cpu=payload.get("cpu_percent"),
        ram=payload.get("ram_percent"),
        disk=payload.get("disk_percent"),
    )


# ── WhatsApp ──────────────────────────────────────────────────────────────


@app.get("/whatsapp/status")
async def wa_status_route() -> dict:
    from app.whatsapp_client import wa_status
    return await wa_status()


@app.post("/whatsapp/start")
async def wa_start_route() -> dict:
    """Trigger WhatsApp service launch if not already running."""
    await asyncio.to_thread(_launch_whatsapp)
    # Poll up to 8s for the service to come up — return as soon as it responds
    from app.whatsapp_client import wa_status
    for _ in range(8):
        await asyncio.sleep(1)
        status = await wa_status()
        if status.get("ok") is not False:
            return {"triggered": True, "status": status}
    status = await wa_status()
    return {"triggered": True, "status": status}


def _kill_port_3001() -> None:
    """Kill whatever process is listening on port 3001 (Windows + Unix)."""
    global _whatsapp_proc
    # Kill tracked subprocess first
    if _whatsapp_proc and _whatsapp_proc.poll() is None:
        _whatsapp_proc.terminate()
        try:
            _whatsapp_proc.wait(timeout=5)
        except Exception:
            _whatsapp_proc.kill()
        _whatsapp_proc = None
    # Kill by port PID (handles processes we don't have a reference to)
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL
            )
            pids = set()
            for line in out.splitlines():
                if ":3001 " in line and ("LISTENING" in line or "ESTABLISHED" in line):
                    parts = line.split()
                    if parts:
                        try:
                            pids.add(int(parts[-1]))
                        except ValueError:
                            pass
            for pid in pids:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception:
                    pass
        else:
            subprocess.run(
                ["fuser", "-k", "3001/tcp"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception:
        pass


@app.post("/whatsapp/reset")
async def wa_reset_route() -> dict:
    """Kill the WhatsApp Node service, clear session, restart for a fresh QR."""
    import shutil as _shutil
    # Try graceful in-process reset first (works with updated index.js)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.post("http://localhost:3001/reset")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    # Kill whatever is on port 3001
    await asyncio.to_thread(_kill_port_3001)
    await asyncio.sleep(1)
    # Clear stale session so a fresh QR appears
    session_dir = Path.home() / ".veronica-wa-session" / "session-veronica"
    if session_dir.exists():
        _shutil.rmtree(session_dir, ignore_errors=True)
    # Start fresh
    await asyncio.to_thread(_launch_whatsapp)
    return {"ok": True, "message": "WhatsApp service restarted — new QR will appear shortly"}


@app.get("/whatsapp/qr")
async def wa_qr_route() -> dict:
    from app.whatsapp_client import wa_qr
    return await wa_qr()


@app.get("/whatsapp/contacts")
async def wa_contacts_route(q: str = Query(default="")) -> dict:
    from app.whatsapp_client import wa_contacts
    return await wa_contacts(q)


@app.get("/whatsapp/messages")
async def wa_messages_route(limit: int = Query(20, ge=1, le=100)) -> dict:
    from app.whatsapp_client import wa_messages
    return await wa_messages(limit)


@app.post("/whatsapp/send")
async def wa_send_route(payload: dict) -> dict:
    to = (payload or {}).get("to", "").strip()
    text = (payload or {}).get("text", "").strip()
    if not to or not text:
        raise HTTPException(status_code=400, detail="to and text required")
    from app.whatsapp_client import wa_send
    return await wa_send(to, text)


# ── Notion ────────────────────────────────────────────────────────────────


@app.get("/notion/search")
async def notion_search_route(q: str = Query(..., min_length=1)) -> dict:
    from app.notion import search_notion
    return await search_notion(q)


@app.get("/notion/page/{page_id}")
async def notion_page_route(page_id: str) -> dict:
    from app.notion import get_notion_page
    return await get_notion_page(page_id)


@app.get("/contacts")
async def list_contacts_route(limit: int = Query(100, ge=1, le=500)) -> dict[str, object]:
    from app.contacts import list_contacts
    return {"items": list_contacts(limit=limit)}


@app.get("/contacts/search")
async def search_contacts_route(q: str = Query(..., min_length=1)) -> dict[str, object]:
    from app.contacts import find_contacts
    return {"items": find_contacts(q)}


@app.post("/contacts")
async def add_contact_route(payload: dict) -> dict[str, object]:
    name = (payload or {}).get("name", "").strip()
    email = (payload or {}).get("email", "").strip()
    phone = (payload or {}).get("phone", "").strip()
    if not name or not email:
        raise HTTPException(status_code=400, detail="name and email required")
    from app.contacts import upsert_contact
    return {"status": "saved", "item": upsert_contact(name, email, source="manual", phone=phone)}


@app.patch("/contacts/{contact_name}/phone")
async def set_contact_phone_route(contact_name: str, payload: dict) -> dict[str, object]:
    phone = (payload or {}).get("phone", "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="phone required")
    from app.contacts import find_contacts, _normalize_phone
    matches = find_contacts(contact_name, limit=1)
    if not matches:
        raise HTTPException(status_code=404, detail=f"Contact '{contact_name}' not found")
    norm = _normalize_phone(phone)
    from app.db import get_db
    with get_db() as conn:
        conn.execute(
            "UPDATE contacts SET phone=? WHERE lower(name) LIKE ?",
            (norm, f"%{contact_name.lower()}%"),
        )
    return {"status": "updated", "name": matches[0]["name"], "phone": norm}


@app.post("/notion/sync")
async def notion_sync_route(payload: dict) -> dict:
    database_id = (payload or {}).get("database_id", "").strip()
    if not database_id:
        raise HTTPException(status_code=400, detail="database_id required")
    from app.notion import sync_notes_to_notion
    return await sync_notes_to_notion(database_id)


# ── Semantic search ───────────────────────────────────────────────────────────


@app.get("/search")
async def unified_search(q: str = Query(..., min_length=1), limit: int = Query(8, ge=1, le=20)) -> dict:
    from app.storage import semantic_search
    results = await asyncio.to_thread(semantic_search, q, limit)
    return {"query": q, "results": results, "total": len(results)}


@app.get("/memory/search")
async def memory_search(q: str = Query(..., min_length=1), limit: int = Query(8, ge=1, le=20)) -> dict:
    from app.storage import get_relevant_memories
    results = await asyncio.to_thread(get_relevant_memories, q, limit)
    return {"query": q, "results": results, "total": len(results)}


@app.get("/notes/search")
async def notes_search(q: str = Query(..., min_length=1), limit: int = Query(8, ge=1, le=20)) -> dict:
    from app.storage import get_relevant_notes
    results = await asyncio.to_thread(get_relevant_notes, q, limit)
    return {"query": q, "results": results, "total": len(results)}


# ── Journal ───────────────────────────────────────────────────────────────────


@app.get("/journal")
async def list_journals_route(limit: int = Query(14, ge=1, le=60)) -> dict:
    from app.journal import list_journals
    return {"items": list_journals(limit=limit)}


@app.get("/journal/today")
async def journal_today_route() -> dict:
    from app.journal import get_journal, generate_journal_entry
    existing = get_journal()
    if existing:
        return existing
    return await asyncio.to_thread(generate_journal_entry)


@app.post("/journal/generate")
async def journal_generate_route(payload: dict = {}) -> dict:
    from app.journal import generate_journal_entry, get_journal
    from app.db import get_db
    date_str = (payload or {}).get("date") or None
    force = bool((payload or {}).get("force", False))
    if force:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo
        d = date_str or _dt.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        with get_db() as conn:
            conn.execute(
                "DELETE FROM life_log WHERE entry_type = 'daily_journal' AND title = ?",
                (f"Journal — {d}",),
            )
    return await asyncio.to_thread(generate_journal_entry, date_str)


@app.get("/journal/{date_str}")
async def journal_by_date_route(date_str: str) -> dict:
    from app.journal import get_journal
    entry = get_journal(date_str)
    if not entry:
        raise HTTPException(status_code=404, detail=f"No journal entry for {date_str}")
    return entry


# ── Wake word event bus ───────────────────────────────────────────────────────
# wake_listener.py publishes stages here; frontend subscribes via SSE.

_wake_subscribers: list[asyncio.Queue] = []
_wake_last_event: dict = {"stage": "idle", "text": "", "response": ""}


@app.post("/wake/event")
async def wake_event(payload: dict) -> dict[str, object]:
    """
    Called by wake_listener.py to broadcast voice-pipeline stages.
    payload: { stage: "detected"|"transcribed"|"replied"|"idle", text?: str, response?: str }
    """
    stage    = (payload or {}).get("stage", "idle")
    text     = (payload or {}).get("text", "")
    response = (payload or {}).get("response", "")

    _wake_last_event.update(stage=stage, text=text, response=response)

    event = json.dumps({"stage": stage, "text": text, "response": response})
    dead: list[asyncio.Queue] = []
    for q in _wake_subscribers:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _wake_subscribers.remove(q)

    return {"ok": True}


@app.get("/wake/stream")
async def wake_stream():
    """SSE stream — frontend subscribes to get real-time wake word events."""
    q: asyncio.Queue = asyncio.Queue(maxsize=20)
    _wake_subscribers.append(q)

    async def event_gen():
        # Send current state immediately on connect
        yield f"data: {json.dumps(_wake_last_event)}\n\n"
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in _wake_subscribers:
                _wake_subscribers.remove(q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
