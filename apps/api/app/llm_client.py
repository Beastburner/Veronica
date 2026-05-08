from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterator
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from app.config import settings

log = logging.getLogger("veronica.llm")

_groq_client: OpenAI | None = None
_ollama_client: OpenAI | None = None
_init_lock = threading.Lock()


def _groq() -> tuple[OpenAI, str]:
    global _groq_client
    if _groq_client is None:
        with _init_lock:
            if _groq_client is None:
                _groq_client = OpenAI(
                    api_key=settings.groq_api_key,
                    base_url=settings.groq_base_url,
                    timeout=25.0,
                )
                log.info("Groq client initialized: model=%s", settings.groq_model)
    return _groq_client, settings.groq_model


def _ollama() -> tuple[OpenAI, str]:
    global _ollama_client
    if _ollama_client is None:
        with _init_lock:
            if _ollama_client is None:
                _ollama_client = OpenAI(api_key="ollama", base_url=settings.ollama_base_url)
                log.info("Ollama client initialized: model=%s", settings.ollama_model)
    return _ollama_client, settings.ollama_model


def call_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    model: str | None = None,
) -> tuple[str | None, str]:
    backends = [_groq(), _ollama()] if settings.groq_api_key else [_ollama()]

    for i, (client, default_model) in enumerate(backends):
        is_last = i == len(backends) - 1
        try:
            completion = client.chat.completions.create(
                model=model or default_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return completion.choices[0].message.content or "", "ok"
        except RateLimitError:
            if is_last:
                return None, "rate_limited"
            log.warning("Groq rate limited — falling back to Ollama")
        except APIConnectionError:
            if is_last:
                return None, "offline"
            log.warning("Groq unreachable — falling back to Ollama")
        except APIStatusError as exc:
            log.warning("LLM API error: %s", exc.status_code)
            return None, f"error:{exc.status_code}"
        except Exception:
            log.exception("LLM call failed")
            return None, "error:unexpected"

    return None, "offline"


def stream_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    model: str | None = None,
) -> Iterator[tuple[str | None, str]]:
    backends = [_groq(), _ollama()] if settings.groq_api_key else [_ollama()]

    for i, (client, default_model) in enumerate(backends):
        is_last = i == len(backends) - 1
        try:
            stream = client.chat.completions.create(
                model=model or default_model,
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
            return
        except RateLimitError:
            if is_last:
                yield None, "rate_limited"
                return
            log.warning("Groq rate limited — falling back to Ollama for stream")
        except APIConnectionError:
            if is_last:
                yield None, "offline"
                return
            log.warning("Groq unreachable — falling back to Ollama for stream")
        except APIStatusError as exc:
            log.warning("LLM stream error: %s", exc.status_code)
            yield None, f"error:{exc.status_code}"
            return
        except Exception:
            log.exception("LLM stream failed")
            yield None, "error:unexpected"
            return


def call_json(prompt: str, *, schema_hint: str = "", max_tokens: int = 200) -> dict[str, Any] | None:
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


def backend_status() -> dict[str, Any]:
    using_groq = bool(settings.groq_api_key)

    if using_groq:
        return {
            "mode": "groq",
            "model": settings.groq_model,
            "base_url": settings.groq_base_url,
            "configured": True,
            "provider_key_present": True,
            "running": True,
        }

    try:
        import httpx
        resp = httpx.get(f"{settings.ollama_base_url.replace('/v1', '')}/api/tags", timeout=2)
        running = resp.status_code == 200
    except Exception:
        running = False
    return {
        "mode": "ollama",
        "model": settings.ollama_model,
        "base_url": settings.ollama_base_url,
        "configured": True,
        "provider_key_present": True,
        "running": running,
    }


def get_embedding(text: str) -> list[float] | None:
    # Groq doesn't support embeddings — always use Ollama for this
    client, model = _ollama()
    try:
        resp = client.embeddings.create(input=[text], model=model)
        return resp.data[0].embedding
    except Exception as e:
        log.warning("Embedding failed: %s", e)
        return None
