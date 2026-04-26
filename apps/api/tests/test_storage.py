from __future__ import annotations


def test_create_and_list_task(fresh_db):
    from app import storage

    created = storage.create_task("Ship voice pipeline", priority="high")
    assert created["id"]
    assert created["status"] == "pending"

    items, total = storage.list_tasks(status="pending")
    assert total == 1
    assert items[0]["description"] == "Ship voice pipeline"


def test_duplicate_task_is_detected(fresh_db):
    from app import storage

    storage.create_task("Identical")
    second = storage.create_task("Identical")
    assert second.get("duplicate") is True


def test_complete_and_delete_task(fresh_db):
    from app import storage

    task = storage.create_task("Replace fan")
    updated = storage.update_task_status(task["id"], "done")
    assert updated and updated["status"] == "done"

    assert storage.delete_task(task["id"]) is True
    assert storage.delete_task(task["id"]) is False


def test_create_note_and_dedup(fresh_db):
    from app import storage

    a = storage.create_note("Buy milk")
    b = storage.create_note("Buy milk")
    assert a["id"] == b["id"]
    assert b["duplicate"] is True


def test_reminder_due_label_daily(fresh_db):
    from app import storage

    item = storage.create_reminder("take pills", "daily:18:00")
    assert "Daily" in (item.get("due_label") or "")


def test_memory_crud(fresh_db):
    from app import storage

    m = storage.create_memory("user lives in Mumbai")
    items, total = storage.list_memories()
    assert total == 1
    assert items[0]["content"] == "user lives in Mumbai"

    assert storage.delete_memory(m["id"]) is True
    _, total = storage.list_memories()
    assert total == 0


def test_perform_create_task_message(fresh_db):
    from app import storage

    result = storage.perform_create_task("Deploy router")
    assert result["kind"] == "task"
    assert result["status"] == "created"
    assert "Deploy router" in result["message"]
