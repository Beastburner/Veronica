from __future__ import annotations

import pytest

from app import tools


@pytest.mark.asyncio
async def test_calculator_basic():
    result = await tools.calculator("2 + 3 * 4")
    assert result["ok"] is True
    assert result["result"] == 14


@pytest.mark.asyncio
async def test_calculator_caret_power():
    result = await tools.calculator("2 ^ 10")
    assert result["ok"] is True
    assert result["result"] == 1024


@pytest.mark.asyncio
async def test_calculator_rejects_unsafe():
    result = await tools.calculator("__import__('os').system('echo hi')")
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_get_current_time_shape():
    result = await tools.get_current_time()
    assert result["ok"] is True
    assert "iso" in result["result"]
    assert "human" in result["result"]


@pytest.mark.asyncio
async def test_run_system_command_whitelist():
    result = await tools.run_system_command("rm -rf /")
    assert result["ok"] is False
    assert "whitelist" in result


@pytest.mark.asyncio
async def test_execute_tool_unknown():
    result = await tools.execute_tool("does_not_exist", {})
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_get_weather_handles_failure(monkeypatch):
    """If httpx raises we should return an error shape, not crash."""
    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            import httpx as _httpx
            raise _httpx.HTTPError("network down")

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Boom())
    result = await tools.get_weather("Mumbai")
    assert result["ok"] is False
    assert "unreachable" in result["error"]
