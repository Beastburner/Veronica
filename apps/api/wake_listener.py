#!/usr/bin/env python3
"""
Veronica Wake Word Listener
============================
Hands-free voice commands for Veronica — no account, no API key needed.

QUICK SETUP
-----------
1. Install deps:
       pip install openwakeword sounddevice edge-tts pygame numpy faster-whisper

2. Run from apps/api/:
       python wake_listener.py

DEFAULT WAKE WORD: "hey jarvis"  (built-in model, works immediately)

TO USE A CUSTOM "Hey Veronica" WAKE WORD
-----------------------------------------
Train one free (no account) at:
    https://huggingface.co/spaces/davidscripka/openWakeWord
Download the .onnx file, then add to .env:
    WAKE_WORD_MODEL=C:/path/to/hey_veronica.onnx
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import queue
import re
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

# ── Load .env ─────────────────────────────────────────────────────────────────
_env_path = Path(__file__).parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_env_path)
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
API_URL             = os.getenv("VERONICA_API_URL", "http://localhost:8000")
WAKE_WORD_MODEL     = os.getenv("WAKE_WORD_MODEL", "")
WAKE_THRESHOLD      = float(os.getenv("WAKE_THRESHOLD", "0.5"))
TTS_VOICE           = os.getenv("TTS_VOICE", "en-US-AriaNeural")
WHISPER_MODEL_NAME  = os.getenv("WHISPER_MODEL", "small.en")
SAMPLE_RATE         = 16_000
CHUNK               = 1280   # 80ms @ 16kHz — openWakeWord's preferred chunk size
SILENCE_THRESHOLD   = 400
SILENCE_DURATION    = 1.8
MAX_RECORD_SEC      = 20     # longer for email body dictation
MAX_FOLLOWUP_SEC    = 30     # even longer when Veronica asks for content

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("veronica.wake")


# ── Dependency check ──────────────────────────────────────────────────────────

def _can_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _check_deps() -> bool:
    required = {
        "openwakeword": "openwakeword",
        "sounddevice":  "sounddevice",
        "numpy":        "numpy",
        "edge_tts":     "edge-tts",
        "pygame":       "pygame",
        "httpx":        "httpx",
        "faster_whisper": "faster-whisper",
    }
    missing = [pip for mod, pip in required.items() if not _can_import(mod)]
    if missing:
        print("\n[!] Missing packages. Run:\n")
        print(f"    pip install {' '.join(missing)}\n")
        return False
    return True


# ── Wake word model ───────────────────────────────────────────────────────────

def _load_wake_model():
    import openwakeword
    from openwakeword.model import Model

    custom = Path(WAKE_WORD_MODEL) if WAKE_WORD_MODEL else None
    if custom and custom.exists():
        model = Model(wakeword_models=[str(custom)], inference_framework="onnx")
        label = custom.stem.replace("_", " ").title()
        log.info("Custom wake word model loaded: %s", custom.name)
    else:
        if WAKE_WORD_MODEL:
            log.warning(".onnx not found at '%s' — using built-in 'hey_jarvis'", WAKE_WORD_MODEL)
        log.info("Downloading wake word models (first run only) …")
        openwakeword.utils.download_models()
        model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        label = "Hey Jarvis"
        log.info("Using built-in wake word: hey_jarvis")

    return model, label


# ── Whisper STT ───────────────────────────────────────────────────────────────

def _load_whisper():
    from faster_whisper import WhisperModel
    log.info("Loading Whisper %s …", WHISPER_MODEL_NAME)
    return WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8", cpu_threads=2)


def transcribe(model, wav_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        tmp = f.name
    try:
        segs, _ = model.transcribe(
            tmp,
            beam_size=1, best_of=1, temperature=0.0,
            vad_filter=False,
            initial_prompt="Veronica AI assistant. Commands: task, reminder, github, calendar, email.",
        )
        return " ".join(s.text.strip() for s in segs).strip()
    finally:
        Path(tmp).unlink(missing_ok=True)


# ── Microphone recording ──────────────────────────────────────────────────────

_QUESTION_PHRASES = (
    "send this?", "schedule this?", "shall i", "should i",
    "what should the body", "what should i write", "who should i send",
    "what's the subject", "what is the subject", "confirm?",
)


def _is_question(text: str) -> bool:
    lowered = text.lower().strip()
    return text.rstrip().endswith("?") or any(p in lowered for p in _QUESTION_PHRASES)


def record_command(max_seconds: int = MAX_RECORD_SEC) -> bytes | None:
    """Record from mic until silence. Returns WAV bytes or None if nothing spoken."""
    import numpy as np
    import sounddevice as sd

    chunks: list = []
    silence_frames   = 0
    speech_started   = False
    frames_per_block = 1024
    silence_limit    = int(SILENCE_DURATION * SAMPLE_RATE / frames_per_block)
    max_blocks       = int(max_seconds * SAMPLE_RATE / frames_per_block)
    done             = threading.Event()

    def _cb(indata, frames, time_info, status):
        nonlocal silence_frames, speech_started
        energy = float(abs(indata).mean())
        chunks.append(indata.copy())
        if energy > SILENCE_THRESHOLD:
            speech_started = True
            silence_frames = 0
        elif speech_started:
            silence_frames += 1
        if (speech_started and silence_frames >= silence_limit) or len(chunks) >= max_blocks:
            done.set()
            raise sd.CallbackStop()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=frames_per_block, callback=_cb):
        done.wait(timeout=max_seconds + 2)

    if not speech_started or not chunks:
        return None

    audio = np.concatenate(chunks).flatten()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


# ── API call ──────────────────────────────────────────────────────────────────

import uuid as _uuid
_SESSION_ID = str(_uuid.uuid4())  # persistent across the whole listener session


def _beep(freq: int = 880, duration: float = 0.15) -> None:
    """Play a short acknowledgement tone using pygame (already owns the audio device)."""
    import numpy as np
    import pygame
    sr = 44100
    n = int(sr * duration)
    t = np.linspace(0, duration, n, False)
    wave_mono = (np.sin(2 * np.pi * freq * t) * 0.4 * 32767).astype(np.int16)
    stereo = np.column_stack([wave_mono, wave_mono])
    sound = pygame.sndarray.make_sound(stereo)
    sound.play()
    pygame.time.wait(int(duration * 1000) + 30)


def _push_event(stage: str, text: str = "", response: str = "") -> None:
    """Fire-and-forget POST to the backend wake event bus."""
    import httpx
    try:
        httpx.post(
            f"{API_URL}/wake/event",
            json={"stage": stage, "text": text, "response": response},
            timeout=3,
        )
    except Exception:
        pass  # event bus is best-effort


def call_api(text: str) -> str:
    import httpx
    try:
        resp = httpx.post(
            f"{API_URL}/chat",
            json={"message": text, "mode": "JARVIS"},
            headers={"X-Session-ID": _SESSION_ID},
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json().get("response") or "Done."
    except httpx.ConnectError:
        return "The Veronica backend is not running. Start it first."
    except Exception as exc:
        log.warning("API error: %s", exc)
        return "I couldn't reach the backend."


# ── TTS ───────────────────────────────────────────────────────────────────────

async def _speak_async(text: str) -> None:
    import edge_tts
    import pygame

    communicate = edge_tts.Communicate(text, TTS_VOICE)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    buf.seek(0)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(buf.read())
        tmp = f.name
    try:
        pygame.mixer.music.load(tmp)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(20)
    finally:
        pygame.mixer.music.unload()
        Path(tmp).unlink(missing_ok=True)


_URL_RE    = re.compile(r'https?://\S+')
_ISO_DT_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+\-]\d{2}:\d{2}')
_SKIP_LINE_PREFIXES = ("meet:", "calendar:", "http", "note:")


def _human_dt(iso: str) -> str:
    try:
        from datetime import datetime as _dt
        dt = _dt.fromisoformat(iso)
        hour = dt.strftime("%I").lstrip("0") or "12"
        return f"{hour} {dt.strftime('%p')} on {dt.strftime('%B %d')}"
    except Exception:
        return iso


def _clean_for_speech(text: str) -> str:
    """Strip URLs and raw timestamps; replace with a dashboard pointer if needed."""
    # Calendar confirmation → compact spoken summary
    if re.search(r'Title:\s*.+', text) and "Schedule this?" in text:
        title_m = re.search(r'Title:\s*(.+)', text)
        time_m  = re.search(r'Time:\s*(.+)', text)
        title_str = title_m.group(1).strip() if title_m else "the meeting"
        time_str  = time_m.group(1).strip()  if time_m  else ""
        time_str  = _ISO_DT_RE.sub(lambda m: _human_dt(m.group()), time_str)
        spoken = title_str
        if time_str:
            spoken += f", {time_str}"
        return spoken + " — schedule this?"

    had_details = bool(_URL_RE.search(text))

    clean: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = line.lower()
        if any(low.startswith(p) for p in _SKIP_LINE_PREFIXES):
            continue
        if _URL_RE.search(line):
            continue
        # Strip Attendees lines — redundant when title already names the person
        if low.startswith("attendees:"):
            continue
        line = _ISO_DT_RE.sub(lambda m: _human_dt(m.group()), line)
        clean.append(line)

    spoken = " ".join(clean).strip()
    if had_details:
        spoken = spoken.rstrip(".") + ". Details are on your dashboard, sir."
    return spoken or text


def speak(text: str) -> None:
    print(f"\n  VERONICA: {text}\n")
    spoken = _clean_for_speech(text)
    try:
        asyncio.run(_speak_async(spoken))
    except Exception as exc:
        log.warning("TTS failed: %s — response printed above", exc)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    if not _check_deps():
        sys.exit(1)

    import numpy as np
    import sounddevice as sd
    import pygame

    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

    wake_model, wake_label = _load_wake_model()
    whisper = _load_whisper()

    audio_q: queue.Queue[np.ndarray] = queue.Queue()

    def _sd_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
        audio_q.put(np.squeeze(indata).copy())

    print(f"\n{'━'*52}")
    print(f"  VERONICA  |  wake word: \"{wake_label}\"")
    print(f"  API  →  {API_URL}")
    print(f"  TTS  →  {TTS_VOICE}")
    print(f"{'━'*52}")
    print("  Listening …  (Ctrl+C to quit)\n")

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=CHUNK, callback=_sd_callback,
        ):
            while True:
                chunk = audio_q.get()
                scores = wake_model.predict(chunk)

                triggered = any(v >= WAKE_THRESHOLD for v in scores.values())
                if not triggered:
                    continue

                matched = max(scores, key=scores.get)
                print(f"  [{wake_label.upper()} DETECTED ({scores[matched]:.2f})]  speak your command …")
                _push_event("detected")

                # Beep signals recording start; its duration clears the wake-word
                # audio from the buffer so the command isn't clipped.
                _beep()
                while not audio_q.empty():
                    try:
                        audio_q.get_nowait()
                    except queue.Empty:
                        break

                wav = record_command()
                if not wav:
                    log.info("No speech detected.")
                    _push_event("idle")
                    continue

                command = transcribe(whisper, wav)
                if not command or len(command) < 3:
                    _push_event("idle")
                    continue

                print(f"\n  COMMANDER: {command}")
                _push_event("transcribed", text=command)
                reply = call_api(command)
                _push_event("replied", text=command, response=reply)
                speak(reply)

                # ── Auto-listen follow-up loop ─────────────────────────────
                # If Veronica asked a question (confirm, body, subject…)
                # skip wake word and go straight into recording.
                while _is_question(reply):
                    print("  [AUTO-LISTEN]  waiting for your reply …")
                    _push_event("detected", text="Auto-listen: waiting for reply")

                    # Lower beep signals auto-listen is ready
                    _beep(freq=660, duration=0.1)
                    while not audio_q.empty():
                        try:
                            audio_q.get_nowait()
                        except queue.Empty:
                            break

                    wav = record_command(max_seconds=MAX_FOLLOWUP_SEC)
                    if not wav:
                        log.info("No follow-up speech detected.")
                        break

                    command = transcribe(whisper, wav)
                    if not command or len(command) < 2:
                        break

                    print(f"\n  COMMANDER: {command}")
                    _push_event("transcribed", text=command)
                    reply = call_api(command)
                    _push_event("replied", text=command, response=reply)
                    speak(reply)

                _push_event("idle")

    except KeyboardInterrupt:
        print("\n  Shutting down …")
    finally:
        pygame.mixer.quit()


if __name__ == "__main__":
    main()
