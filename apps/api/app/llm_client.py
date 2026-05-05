from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Iterator
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from app.config import settings

log = logging.getLogger("veronica.llm")

# ── Key pool for OpenRouter multi-key rotation ───────────────────────────────

_OPENROUTER_COOLDOWN = 300  # 5 min cooldown before retrying a rate-limited key


class _KeyPool:
    """
    Holds multiple OpenRouter API keys.  When a key returns 429 it is marked
    exhausted for _OPENROUTER_COOLDOWN seconds; the pool automatically tries
    the next available key.  All keys expired → returns "rate_limited".
    """

    def __init__(self, keys: list[str], base_url: str, model: str) -> None:
        self._keys = keys
        self._base_url = base_url
        self._model = model
        self._exhausted: dict[str, float] = {}  # key -> monotonic time when marked
        self._lock = threading.Lock()
        self._clients: dict[str, OpenAI] = {}

    # ── internal ─────────────────────────────────────────────────────────────

    def _client(self, key: str) -> OpenAI:
        if key not in self._clients:
            self._clients[key] = OpenAI(
                api_key=key,
                base_url=self._base_url,
                default_headers={
                    "HTTP-Referer": "https://veronica.local",
                    "X-Title": "VERONICA",
                },
            )
        return self._clients[key]

    def _available(self) -> list[str]:
        now = time.monotonic()
        with self._lock:
            return [
                k for k in self._keys
                if now - self._exhausted.get(k, 0.0) > _OPENROUTER_COOLDOWN
            ]

    def _exhaust(self, key: str) -> None:
        with self._lock:
            self._exhausted[key] = time.monotonic()
        log.warning("OpenRouter key ...%s rate-limited — rotating to next key", key[-8:])

    # ── public status ─────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        available = self._available()
        return {
            "mode": "openrouter",
            "model": self._model,
            "base_url": self._base_url,
            "total_keys": len(self._keys),
            "available_keys": len(available),
            "configured": len(available) > 0,
            "provider_key_present": len(self._keys) > 0,
        }

    # ── chat ──────────────────────────────────────────────────────────────────

    def call_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> tuple[str | None, str]:
        keys = self._available()
        if not keys:
            return None, "rate_limited"

        for key in keys:
            try:
                completion = self._client(key).chat.completions.create(
                    model=model or self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return completion.choices[0].message.content or "", "ok"
            except RateLimitError:
                self._exhaust(key)
            except APIStatusError as exc:
                if exc.status_code == 429:
                    self._exhaust(key)
                else:
                    log.warning("LLM API error: %s", exc.status_code)
                    return None, f"error:{exc.status_code}"
            except APIConnectionError:
                return None, "offline"
            except Exception:
                log.exception("LLM call failed")
                return None, "error:unexpected"

        return None, "rate_limited"

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> Iterator[tuple[str | None, str]]:
        keys = self._available()
        if not keys:
            yield None, "rate_limited"
            return

        for key in keys:
            try:
                stream = self._client(key).chat.completions.create(
                    model=model or self._model,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                )
                # 429 would have been raised before we get here, so it's safe to stream
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
                self._exhaust(key)
                # try next key — no tokens yielded yet
            except APIStatusError as exc:
                if exc.status_code == 429:
                    self._exhaust(key)
                else:
                    log.warning("LLM stream error: %s", exc.status_code)
                    yield None, f"error:{exc.status_code}"
                    return
            except APIConnectionError:
                yield None, "offline"
                return
            except Exception:
                log.exception("LLM stream failed")
                yield None, "error:unexpected"
                return

        yield None, "rate_limited"


# ── Legacy single-key client (OpenAI / Ollama / any compatible backend) ──────

class _SingleClient:
    def __init__(self, api_key: str, base_url: str | None, model: str) -> None:
        self._model = model
        self._base_url = base_url
        kwargs: dict[str, str] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def status(self) -> dict[str, Any]:
        return {
            "mode": "single",
            "model": self._model,
            "base_url": self._base_url or "default",
            "configured": True,
            "provider_key_present": True,
        }

    def call_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> tuple[str | None, str]:
        try:
            completion = self._client.chat.completions.create(
                model=model or self._model,
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
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> Iterator[tuple[str | None, str]]:
        try:
            stream = self._client.chat.completions.create(
                model=model or self._model,
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


# ── Backend initialisation ────────────────────────────────────────────────────
# Primary  : OpenRouter key pool (if OPENROUTER_API_KEYS is set)
# Fallback : single-key Ollama / OpenAI (if OPENAI_API_KEY is set)
# Behaviour: primary is tried first; if it returns rate_limited, fallback is used.

_primary:  _KeyPool | _SingleClient | None = None
_fallback: _SingleClient | None = None
_init_lock = threading.Lock()
_initialised = False


def _init_backends() -> None:
    global _primary, _fallback, _initialised
    with _init_lock:
        if _initialised:
            return

        or_keys = settings.openrouter_keys_list
        if or_keys:
            _primary = _KeyPool(
                keys=or_keys,
                base_url=settings.openrouter_base_url,
                model=settings.openrouter_model,
            )
            log.info("OpenRouter pool: %d key(s), model=%s", len(or_keys), settings.openrouter_model)

        if settings.openai_api_key:
            _fallback = _SingleClient(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_model,
            )
            log.info("Fallback client: model=%s base=%s", settings.openai_model, settings.openai_base_url or "default")

        _initialised = True


def _backends() -> list[_KeyPool | _SingleClient]:
    _init_backends()
    return [b for b in (_primary, _fallback) if b is not None]


# ── Public API ────────────────────────────────────────────────────────────────

def _should_fallback(status: str) -> bool:
    """Return True when the status means we should try the next backend."""
    if status in ("rate_limited", "offline"):
        return True
    # Also fall through on server-side or model-not-found errors (4xx/5xx from provider).
    # Do NOT fall through on auth errors (401/403) — the next backend won't fix those.
    if status.startswith("error:"):
        try:
            code = int(status.split(":", 1)[1])
            return code not in (401, 403)
        except ValueError:
            return True  # "error:unexpected" etc.
    return False


def call_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    model: str | None = None,
) -> tuple[str | None, str]:
    chain = _backends()
    if not chain:
        return None, "not_configured"
    last_status = "not_configured"
    for backend in chain:
        text, status = backend.call_chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)
        if not _should_fallback(status):
            return text, status
        last_status = status
        log.info("Backend %s (%s) — trying next", status, getattr(backend, "_model", "?"))
    return None, last_status


def stream_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    model: str | None = None,
) -> Iterator[tuple[str | None, str]]:
    chain = _backends()
    if not chain:
        yield None, "not_configured"
        return
    for i, backend in enumerate(chain):
        last_status: str | None = None
        for chunk, status in backend.stream_chat(messages, temperature=temperature, model=model):
            last_status = status
            if _should_fallback(status) and i + 1 < len(chain):
                log.info(
                    "Backend %s (%s) — falling back to next backend",
                    status, getattr(backend, "_model", "?"),
                )
                break  # don't yield the error; try next backend
            yield chunk, status
        else:
            return  # stream finished cleanly (done or final backend errored)
    # all backends exhausted
    yield None, "rate_limited"


def call_json(prompt: str, *, schema_hint: str = "", max_tokens: int = 200) -> dict[str, Any] | None:
    system = (
        "You produce ONLY a single JSON object as a reply. "
        "No prose, no code fences, no markdown. "
        f"{schema_hint}"
    )
    text, status = call_chat(
        [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
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
        end   = cleaned.rindex("}") + 1
        return json.loads(cleaned[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


def backend_status() -> dict[str, Any]:
    """Return combined status — configured=True if ANY backend can serve requests."""
    _init_backends()
    if _primary is None and _fallback is None:
        return {"mode": "none", "configured": False, "provider_key_present": False, "model": None, "base_url": None}

    primary_ok   = _primary is not None and _primary.status()["configured"]
    fallback_ok  = _fallback is not None  # SingleClient is always ready

    # Report whichever backend will actually handle the next request
    active = _primary if primary_ok else (_fallback if fallback_ok else _primary)
    status = active.status()  # type: ignore[union-attr]

    # System is usable if at least one backend is ready
    status["configured"] = primary_ok or fallback_ok

    if _primary and _fallback:
        status["fallback_model"] = _fallback._model
        status["fallback_base_url"] = _fallback._base_url or "default"
        status["primary_ok"] = primary_ok
        status["fallback_ok"] = fallback_ok

    return status


def get_embedding(text: str) -> list[float] | None:
    """Get a vector embedding for semantic search."""
    _init_backends()
    client_to_use = _fallback or _primary
    if not client_to_use:
        return None
    try:
        if hasattr(client_to_use, "_clients"):
            c = getattr(client_to_use, "_client")(getattr(client_to_use, "_keys")[0])
        else:
            c = getattr(client_to_use, "_client")
            
        model = getattr(client_to_use, "_model", "text-embedding-3-small")
        if "llama" in model.lower() or "qwen" in model.lower():
            # Ollama handles embeddings using the chat model name usually, or nomic-embed-text
            pass
            
        resp = c.embeddings.create(input=[text], model=model)
        return resp.data[0].embedding
    except Exception as e:
        log.warning("Failed to get embedding: %s", e)
        return None
