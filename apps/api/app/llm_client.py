from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from app.config import settings

log = logging.getLogger("veronica.llm")

_client: OpenAI | None = None


def get_client() -> OpenAI | None:
    global _client
    if not settings.openai_api_key:
        return None
    if _client is None:
        kwargs: dict[str, str] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        _client = OpenAI(**kwargs)
    return _client


def call_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    model: str | None = None,
) -> tuple[str | None, str]:
    client = get_client()
    if client is None:
        return None, "not_configured"

    try:
        completion = client.chat.completions.create(
            model=model or settings.openai_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content or "", "ok"
    except RateLimitError:
        return None, "rate_limited"
    except APIConnectionError:
        return None, "offline"
    except APIStatusError as exc:
        log.warning("LLM API error: %s", exc.status_code)
        return None, f"error:{exc.status_code}"
    except Exception:
        log.exception("LLM call failed")
        return None, "error:unexpected"


def stream_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    model: str | None = None,
) -> Iterator[tuple[str | None, str]]:
    """Yields (chunk, status). status='ok' on each chunk, terminal status on stop/error."""
    client = get_client()
    if client is None:
        yield None, "not_configured"
        return

    try:
        stream = client.chat.completions.create(
            model=model or settings.openai_model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for event in stream:
            choice = event.choices[0] if event.choices else None
            if choice is None:
                continue
            delta = choice.delta.content if choice.delta else None
            if delta:
                yield delta, "ok"
        yield None, "done"
    except RateLimitError:
        yield None, "rate_limited"
    except APIConnectionError:
        yield None, "offline"
    except APIStatusError as exc:
        log.warning("LLM stream error: %s", exc.status_code)
        yield None, f"error:{exc.status_code}"
    except Exception:
        log.exception("LLM stream failed")
        yield None, "error:unexpected"


def call_json(prompt: str, *, schema_hint: str = "", max_tokens: int = 200) -> dict[str, Any] | None:
    """Call the model and parse a JSON object from the reply. Returns None on failure."""
    system = (
        "You produce ONLY a single JSON object as a reply. "
        "No prose, no code fences, no markdown. "
        f"{schema_hint}"
    )
    text, status = call_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=max_tokens,
    )
    if status != "ok" or not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        return json.loads(cleaned[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
