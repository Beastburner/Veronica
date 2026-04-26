from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_llm_fallback(monkeypatch):
    """Force LLM-driven intent extraction to return None so tests stay deterministic."""
    from app import intent_router, llm_client

    monkeypatch.setattr(llm_client, "call_json", lambda *a, **k: None)
    monkeypatch.setattr(intent_router, "call_json", lambda *a, **k: None)


def test_set_reminder_regex(fresh_db):
    from app.intent_router import classify

    result = classify("set reminder to call mom daily at 9 pm")
    assert result.type == "write"
    assert result.payload["kind"] == "reminder"


def test_add_task_regex(fresh_db):
    from app.intent_router import classify

    result = classify("add task to ship voice pipeline")
    assert result.type == "write"
    assert result.payload["kind"] == "task"


def test_remember_that_creates_note(fresh_db):
    from app.intent_router import classify

    result = classify("remember that the wifi password is hunter2")
    assert result.type == "write"
    assert result.payload["kind"] == "note"


def test_memorize_creates_memory(fresh_db):
    from app.intent_router import classify

    result = classify("memorize: my dog is named Pixel")
    assert result.type == "write"
    assert result.payload["kind"] == "memory"


def test_time_query(fresh_db):
    from app.intent_router import classify

    result = classify("what time is it")
    assert result.type == "read"
    assert result.payload["kind"] == "time"


def test_show_tasks(fresh_db):
    from app.intent_router import classify

    result = classify("show my tasks")
    assert result.type == "read"
    assert result.payload["kind"] == "tasks"


def test_show_reminders(fresh_db):
    from app.intent_router import classify

    result = classify("what are my reminders")
    assert result.type == "read"
    assert result.payload["kind"] == "reminders"


def test_calculator_expression(fresh_db):
    from app.intent_router import classify

    result = classify("(3 + 4) * 5")
    assert result.type == "tool"
    assert result.payload["tool"] == "calculator"


def test_weather_intent(fresh_db):
    from app.intent_router import classify

    result = classify("weather in Mumbai")
    assert result.type == "tool"
    assert result.payload["tool"] == "get_weather"
    assert result.payload["args"]["city"].lower().startswith("mumbai")


def test_search_intent(fresh_db):
    from app.intent_router import classify

    result = classify("search for fastapi streaming responses")
    assert result.type == "tool"
    assert result.payload["tool"] == "web_search"


def test_protocol_detection(fresh_db):
    from app.intent_router import classify

    result = classify("activate sentinel security mode")
    assert result.type == "protocol"
    assert result.payload["protocol"] == "security"


def test_falls_through_to_llm(fresh_db):
    from app.intent_router import classify

    result = classify("explain how websockets work")
    assert result.type == "llm"
