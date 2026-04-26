from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("veronica.transcribe")

_model: Any = None
_model_lock = threading.Lock()
_model_name = os.getenv("WHISPER_MODEL", "small.en")
_model_compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
_model_device = os.getenv("WHISPER_DEVICE", "cpu")
_cpu_threads = int(os.getenv("WHISPER_CPU_THREADS", str(max(1, (os.cpu_count() or 4)))))
_num_workers = int(os.getenv("WHISPER_WORKERS", "1"))
_initial_prompt = os.getenv(
    "WHISPER_PROMPT",
    "VERONICA is a Tony Stark style AI assistant. Commands include: "
    "add a task, set a reminder, take a note, deploy coding mode, "
    "deploy architecture mode, deploy security mode, run optimization simulation, "
    "what should I focus on today, JARVIS, FRIDAY, SENTINEL.",
)


def _load_model() -> Any:
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel
        log.info(
            "loading whisper model=%s device=%s compute=%s threads=%s",
            _model_name,
            _model_device,
            _model_compute,
            _cpu_threads,
        )
        _model = WhisperModel(
            _model_name,
            device=_model_device,
            compute_type=_model_compute,
            cpu_threads=_cpu_threads,
            num_workers=_num_workers,
        )
        return _model


def transcribe_bytes(audio_bytes: bytes, suffix: str = ".webm") -> str:
    if not audio_bytes:
        return ""
    model = _load_model()

    tmp = tempfile.NamedTemporaryFile(prefix="veronica_audio_", suffix=suffix, delete=False)
    try:
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()

        kwargs: dict[str, Any] = {
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 300},
            "beam_size": 1,
            "best_of": 1,
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "initial_prompt": _initial_prompt,
            "no_speech_threshold": 0.5,
        }
        if not _model_name.endswith(".en"):
            kwargs["language"] = "en"

        segments, _ = model.transcribe(tmp.name, **kwargs)
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass


def warm_up() -> None:
    try:
        _load_model()
    except Exception as exc:
        log.warning("whisper warmup failed: %s", exc)
