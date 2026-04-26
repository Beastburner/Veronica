import asyncio
import json
import logging
import os
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse

from app.agent import generate_response, model_health, stream_response, summarize_turns
from app.bootstrap import ensure_ollama
from app.config import settings
from app.context.manager import BoundedContextWindow
from app.db import init_db
from app.intent_router import classify
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
from app.tools import REGISTRY as TOOL_REGISTRY
from app.tools import execute_tool
from app.transcribe import transcribe_bytes
from app.transcribe import warm_up as warm_up_whisper

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("veronica")


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    status = await asyncio.to_thread(ensure_ollama)
    log.info("ollama bootstrap: %s", status)
    asyncio.create_task(asyncio.to_thread(warm_up_whisper))
    asyncio.create_task(asyncio.to_thread(_run_compaction))
    yield


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

    intent = classify(request.message)

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

    if intent.type == "read":
        message_text = intent.payload.get("message", "")
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
        log_action("VERONICA", f"chat:{request.mode.value}:read", "low", True, message_text[:240])
        return response

    tool_results: list[dict] = []
    if intent.type == "tool":
        tool_name = intent.payload.get("tool")
        args = intent.payload.get("args") or {}
        if tool_name in TOOL_REGISTRY:
            tool_results.append(await execute_tool(tool_name, args))

    forced_protocol = intent.payload.get("protocol") if intent.type == "protocol" else None

    history = window.get_context_messages()
    recent_summary = get_recent_summary(session_id)
    if recent_summary:
        history = [{"role": "system", "content": f"Session summary: {recent_summary}"}] + history

    storage_context = build_assistant_context(request.message)
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

    intent = classify(request.message)

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

    if intent.type == "write":
        kind = intent.payload.get("kind", "item")
        message_text = intent.payload.get("message", "")
        await hot_cache.invalidate_pattern(f"{kind}s:")
        window.add_message("assistant", message_text)
        log_action("VERONICA", f"chat:{request.mode.value}:write:{kind}", "low", True, message_text[:240])
        return await emit_single(message_text, f"direct_write:{kind}")

    if intent.type == "read":
        message_text = intent.payload.get("message", "")
        window.add_message("assistant", message_text)
        log_action("VERONICA", f"chat:{request.mode.value}:read", "low", True, message_text[:240])
        return await emit_single(message_text, "direct_data")

    tool_results: list[dict] = []
    if intent.type == "tool":
        tool_name = intent.payload.get("tool")
        args = intent.payload.get("args") or {}
        if tool_name in TOOL_REGISTRY:
            tool_results.append(await execute_tool(tool_name, args))

    forced_protocol = intent.payload.get("protocol") if intent.type == "protocol" else None

    history = window.get_context_messages()
    recent_summary = get_recent_summary(session_id)
    if recent_summary:
        history = [{"role": "system", "content": f"Session summary: {recent_summary}"}] + history

    storage_context = build_assistant_context(request.message)
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
