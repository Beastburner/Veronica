from __future__ import annotations

import asyncio
import io
import logging
import os

log = logging.getLogger("veronica.tts")

_DEFAULT_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")


async def synthesize(text: str, voice: str | None = None) -> bytes:
    """Return MP3 audio bytes for the given text via edge-tts."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice or _DEFAULT_VOICE)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def synthesize_sync(text: str, voice: str | None = None) -> bytes:
    return asyncio.run(synthesize(text, voice))
