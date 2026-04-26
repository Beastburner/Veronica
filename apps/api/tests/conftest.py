"""Shared pytest fixtures.

Each test gets a fresh on-disk SQLite file under a temp directory; the storage
module's DB_PATH is monkey-patched before any storage import touches the DB.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    db_file = tmp_path / "veronica_test.db"
    # Patch DB_PATH on the live module if already imported
    if "app.db" in sys.modules:
        monkeypatch.setattr(sys.modules["app.db"], "DB_PATH", db_file)
    else:
        from app import db as db_module  # noqa: WPS433
        monkeypatch.setattr(db_module, "DB_PATH", db_file)

    from app import db as db_module  # noqa: WPS433

    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    db_module.init_db()

    # Reload storage so its bound `get_db` and `DB_PATH` use the patched value
    if "app.storage" in sys.modules:
        importlib.reload(sys.modules["app.storage"])

    yield db_file
