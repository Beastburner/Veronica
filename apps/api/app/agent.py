import asyncio
import logging


from app.llm_client import call_chat, stream_chat
from app.models import AssistantMode, ChatRequest, ChatResponse, ToolCallPlan

log = logging.getLogger("veronica.agent")


MODE_PROMPTS = {
    AssistantMode.jarvis: """
JARVIS MODE — Master Executive Intelligence.
Personality: Formal, measured, highly efficient. You are the command layer.
Tone: Composed, precise, occasionally dry. Address the user as 'Sir'
naturally and sparingly — never robotically or every sentence.
Reasoning: Systems-first. Think in terms of architecture, dependencies,
and downstream consequences before answering.
Priorities: Accuracy over speed. Never guess. If uncertain, say so
and give the most likely answer with a confidence note.
Format: Lead with the answer, follow with reasoning. Keep it tight.
Avoid: Filler phrases, unnecessary caveats, sycophantic openers.
""",

    AssistantMode.friday: """
FRIDAY MODE — Productivity and Human Intelligence Operator.
Personality: Warm, proactive, emotionally aware. You notice what
the user hasn't said as much as what they have.
Tone: Casual but sharp. Slightly warmer than JARVIS. Still efficient.
Reasoning: People-first. Think about workload, mental state, and what
the user actually needs versus what they literally asked for.
Priorities: Help the user focus and make real progress today.
Format: Conversational but structured. Short lists when genuinely helpful.
Avoid: Cold technical responses. Always acknowledge context.
""",

    AssistantMode.veronica: """
VERONICA MODE — Core Operational Intelligence.
Personality: Sharp, dry wit. Brutally concise. Slightly sarcastic
when appropriate — never cruel. You do not suffer fools but you
are never condescending to the person you work for.
Tone: Confident, clipped, clever. Cut to the solution immediately.
Reasoning: Pragmatic. Point out flaws in the user's thinking if
you see them — respectfully but directly. Don't pad answers.
Priorities: Efficiency and correctness above all else.
Format: As short as possible without losing meaning. One-liners
when appropriate. Lists only when structure genuinely helps.
Avoid: Filler, repetition, over-explanation, unnecessary politeness.
""",

    AssistantMode.sentinel: """
SENTINEL MODE — Security and Risk Assessment System.
Personality: Terse, watchful, threat-aware. Every input is treated
as potentially adversarial until assessed.
Tone: Clipped military precision. No warmth. Maximum signal density.
Reasoning: Threat-model first. For every request consider: what
could go wrong, who could be harmed, what is at risk.
Priorities: Safety over functionality. Flag risks explicitly.
Format: SHORT. Use structured assessments for risk evaluation:
  THREAT: [what]
  VECTOR: [how]
  RISK: [LOW/MED/HIGH]
  RECOMMENDATION: [action]
Avoid: Casual tone, long explanations, anything that is not signal.
""",
}


PROTOCOLS = {
    "coding": "Developer Mode online. Repository analysis, code generation, debugging, and shell planning are prioritized.",
    "architecture": "Architecture analysis engaged. Mapping components, risks, scaling constraints, and upgrade paths.",
    "optimization": "Optimization simulation running. Evaluating bottlenecks, trade-offs, and likely performance gains.",
    "security": "SENTINEL sweep initialized. Reviewing attack surface, secrets exposure, and execution permissions.",
    "focus": "FRIDAY focus planning active. Ranking tasks by urgency, leverage, and mental load.",
}


def build_system_prompt(mode: AssistantMode, protocol: str | None) -> str:
    protocol_line = PROTOCOLS.get(protocol, "No special protocol active.")
    mode_block = MODE_PROMPTS[mode]
    return f"""You are VERONICA — a personal AI assistant built for
a developer and researcher. You are intelligent, technically precise,
and have a distinct personality that shifts based on the active mode.
You are NOT a generic chatbot. You have opinions, you challenge poor
decisions, and you give direct answers.

ACTIVE MODE:
{mode_block}

PROTOCOL STATUS: {protocol_line}

HARD RULES (apply in ALL modes, no exceptions):
- NEVER start a response with: I, Sure, Certainly, Of course, Great,
  Absolutely, That's a great question, I'd be happy to, or Of course.
- NEVER use filler like "I understand", "I see", "Noted".
- NEVER pad a short answer with unnecessary context.
- If you don't know something, say so directly. Never hallucinate facts.
- You have tools that can access the internet (web_search, web_scrape, news_digest,
  weather, GitHub, Gmail, Calendar). These tools run server-side — you DO have
  internet access via these tools. NEVER say "I have no internet access."
- When a tool result is injected, use it. When no tool result is present, do not
  invent live data — say you need to run a search instead.
- Keep responses under 150 words unless the user asks for detail.
- When the user is about to make a mistake you recognize, say so once,
  clearly, without lecturing.
- If the user sends ONLY a greeting (hi, hey, wassup, yo, sup, etc.),
  respond with ONLY a single short casual greeting. No questions, no
  context, no task suggestions, no project references. Nothing else.
- When a tool result is injected, read the ok field carefully:
  ok=True  → confirm concisely: "Email sent to X." / "Meeting scheduled for [time]."
  ok=False → report failure directly: "Email failed: [error]." NEVER say it succeeded.
  Do NOT re-show the full email body or event details unless asked.
"""


_FALLBACK_REASON: dict[str, str] = {
    "not_configured":  "No model provider configured. Set OPENROUTER_API_KEYS or OPENAI_API_KEY in .env.",
    "rate_limited":    "All available API keys are currently rate-limited. Try again in a moment.",
    "offline":         "Ollama is unreachable. Run: ollama serve",
}


def local_fallback_response(request: ChatRequest, protocol: str | None, tool_plan: list[ToolCallPlan], provider_status: str) -> str:
    if provider_status in _FALLBACK_REASON:
        reason = _FALLBACK_REASON[provider_status]
    elif provider_status.startswith("error:"):
        code = provider_status.split(":", 1)[1]
        if code == "500":
            from app.config import settings as _cfg
            reason = f"Ollama returned 500 — model not loaded. Run: ollama pull {_cfg.ollama_model}"
        else:
            reason = f"Ollama returned HTTP {code}."
    else:
        reason = "Model unavailable."
    return f"Sir, inference offline. {reason}"


def build_messages(request: ChatRequest, protocol: str | None, extras: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(request.mode, protocol)}
    ]
    if extras:
        messages.extend(extras)
    for item in request.history[-8:]:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
        else:
            role = item.role
            content = item.content
        if role and content:
            messages.append({"role": str(role), "content": str(content)})
    messages.append({"role": "user", "content": request.message})
    return messages


def call_llm(request: ChatRequest, protocol: str | None) -> tuple[str | None, str]:
    return call_chat(build_messages(request, protocol), temperature=0.7)


def stream_llm(request: ChatRequest, protocol: str | None):
    yield from stream_chat(build_messages(request, protocol), temperature=0.7)


def summarize_turns(turns: list[dict[str, str]], mode: str) -> str:
    transcript = "\n".join(
        f"{(t.get('role') or '').upper()}: {(t.get('content') or '')[:400]}"
        for t in turns
        if t.get("role") and t.get("content")
    )
    if not transcript:
        return ""

    text, status = call_chat(
        [
            {
                "role": "system",
                "content": (
                    "Summarize this VERONICA conversation in 2-3 sentences. "
                    "Capture the user's intent, any decisions made, and pending follow-ups. "
                    "Stay terse, no filler."
                ),
            },
            {"role": "user", "content": f"[mode={mode}]\n{transcript}"},
        ],
        temperature=0.2,
        max_tokens=140,
    )
    if status != "ok" or not text:
        return ""
    return text.strip()


def get_suggested_actions(mode: AssistantMode, protocol: str | None) -> list[str]:
    try:
        from app.behavior import get_personalized_suggestions
        suggestions = get_personalized_suggestions(mode.value.upper())
        if suggestions:
            if protocol == "coding":
                suggestions.insert(0, "Paste or attach code for immediate analysis.")
            elif protocol == "security":
                suggestions.insert(0, "Specify the target surface for the security sweep.")
            elif protocol == "focus":
                suggestions.insert(0, "Tell VERONICA what your #1 priority is right now.")
            return suggestions[:3]
    except Exception:
        pass

    base = {
        AssistantMode.jarvis: [
            "Request a full system architecture overview.",
            "Run a dependency audit on the current project.",
            "Ask VERONICA to draft a technical decision brief.",
        ],
        AssistantMode.friday: [
            "Ask VERONICA to prioritize your task list by urgency.",
            "Set a focus block for your most important task today.",
            "Request a daily briefing summary.",
        ],
        AssistantMode.veronica: [
            "Describe your current problem — VERONICA will triage it.",
            "Ask VERONICA to review your last decision.",
            "Request a concise status report on active tasks.",
        ],
        AssistantMode.sentinel: [
            "Run a secrets exposure scan on the codebase.",
            "Request a threat model for the current system.",
            "Ask VERONICA to audit recent action logs for anomalies.",
        ],
    }
    suggestions = list(base.get(mode, []))
    if protocol == "coding":
        suggestions.insert(0, "Paste or attach code for immediate analysis.")
    elif protocol == "security":
        suggestions.insert(0, "Specify the target surface for the security sweep.")
    elif protocol == "focus":
        suggestions.insert(0, "Tell VERONICA what your #1 priority is right now.")
    return suggestions[:3]


def model_health() -> dict[str, str | bool | int]:
    from app.llm_client import backend_status
    return backend_status()


async def generate_response(
    request: ChatRequest,
    *,
    forced_protocol: str | None = None,
    tool_results: list[dict] | None = None,
) -> ChatResponse:
    protocol = forced_protocol
    tool_plan: list[ToolCallPlan] = []

    extras: list[dict[str, str]] = []
    if tool_results:
        for result in tool_results:
            ok = "✓" if result.get("ok") else "✗"
            extras.append(
                {
                    "role": "system",
                    "content": f"Tool {result.get('tool')} {ok}: {result}",
                }
            )

    messages = build_messages(request, protocol, extras)
    generated, provider_status = await asyncio.to_thread(
        lambda: call_chat(messages, temperature=0.7)
    )
    response = generated or local_fallback_response(request, protocol, tool_plan, provider_status)

    return ChatResponse(
        mode=request.mode,
        response=response,
        protocol=protocol,
        provider_status=provider_status,
        memory_updates=[],
        suggested_actions=get_suggested_actions(request.mode, protocol),
        tool_plan=tool_plan,
    )


async def stream_response(
    request: ChatRequest,
    *,
    forced_protocol: str | None = None,
    tool_results: list[dict] | None = None,
):
    """Async generator yielding (kind, payload) pairs.

    kinds: 'token' (str chunk), 'meta' (final ChatResponse-like dict), 'fallback' (full text on error).
    """
    protocol = forced_protocol
    tool_plan: list[ToolCallPlan] = []

    extras: list[dict[str, str]] = []
    if tool_results:
        for result in tool_results:
            ok = "ok" if result.get("ok") else "err"
            extras.append(
                {
                    "role": "system",
                    "content": f"Tool {result.get('tool')} [{ok}]: {result}",
                }
            )

    messages = build_messages(request, protocol, extras)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str | None, str]] = asyncio.Queue()
    sentinel = object()

    def producer():
        try:
            for chunk, status in stream_chat(messages, temperature=0.7):
                loop.call_soon_threadsafe(queue.put_nowait, (chunk, status))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)  # type: ignore[arg-type]

    asyncio.get_running_loop().run_in_executor(None, producer)

    accumulated_text = ""
    terminal_status = "ok"
    while True:
        item = await queue.get()
        if item is sentinel:
            break
        chunk, status = item  # type: ignore[misc]
        if status == "ok" and chunk:
            accumulated_text += chunk
            yield "token", chunk
        elif status == "done":
            terminal_status = "ok"
            break
        else:
            terminal_status = status
            break

    if not accumulated_text:
        fallback = local_fallback_response(request, protocol, tool_plan, terminal_status)
        accumulated_text = fallback
        yield "token", fallback

    yield "meta", {
        "mode": request.mode.value,
        "response": accumulated_text,
        "protocol": protocol,
        "provider_status": terminal_status,
        "memory_updates": [],
        "suggested_actions": get_suggested_actions(request.mode, protocol),
        "tool_plan": [p.model_dump() for p in tool_plan],
    }
