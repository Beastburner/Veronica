from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.config import settings

log = logging.getLogger("veronica.bootstrap")


def _ollama_host() -> tuple[str, int] | None:
    base = settings.openai_base_url or ""
    if "11434" not in base and "ollama" not in base.lower():
        return None
    parsed = urlparse(base)
    return parsed.hostname or "127.0.0.1", parsed.port or 11434


def _is_ollama_up(host: str, port: int) -> bool:
    try:
        with urlopen(f"http://{host}:{port}/api/tags", timeout=1.5) as resp:
            return resp.status == 200
    except (URLError, OSError, ValueError):
        return False


def _model_present(host: str, port: int, model: str) -> bool:
    try:
        with urlopen(f"http://{host}:{port}/api/tags", timeout=2) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
        names = {m.get("name", "") for m in data.get("models", [])}
        return model in names or any(n.startswith(model.split(":")[0] + ":") for n in names)
    except Exception:
        return False


def _pull_model(host: str, port: int, model: str) -> None:
    import json
    payload = json.dumps({"name": model}).encode("utf-8")
    req = Request(
        f"http://{host}:{port}/api/pull",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=600) as resp:
            for _ in resp:
                pass
    except Exception as exc:
        log.error("ollama pull failed: %s", exc)


def ensure_ollama() -> dict[str, object]:
    target = _ollama_host()
    if target is None:
        return {"managed": False, "reason": "non-ollama base url"}

    host, port = target
    started = False

    if not _is_ollama_up(host, port):
        binary = shutil.which("ollama")
        if not binary:
            return {"managed": False, "reason": "ollama binary not found", "running": False}

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            subprocess.Popen(
                [binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
            )
            started = True
        except Exception as exc:
            return {"managed": False, "reason": f"failed to launch: {exc}", "running": False}

        deadline = time.time() + 20
        while time.time() < deadline:
            if _is_ollama_up(host, port):
                break
            time.sleep(0.5)
        else:
            return {"managed": True, "started": True, "running": False, "reason": "ollama did not become ready in 20s"}

    model = settings.openai_model
    has_model = _model_present(host, port, model)
    if not has_model:
        log.info("pulling ollama model %s (first run)...", model)
        _pull_model(host, port, model)
        has_model = _model_present(host, port, model)

    return {
        "managed": True,
        "started": started,
        "running": True,
        "model": model,
        "model_present": has_model,
    }
