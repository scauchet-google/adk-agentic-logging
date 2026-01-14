import asyncio

import pytest

from adk_agentic_logging.core.context import log_ctx


@pytest.mark.asyncio
async def test_context_isolation() -> None:
    async def worker(worker_id: int, delay: float) -> str:
        log_ctx.clear()
        log_ctx.add("id", worker_id)
        await asyncio.sleep(delay)
        # Verify that the ID is still what we set, not overwritten by other workers
        actual_id = log_ctx.get_all().get("id")
        return f"Worker {worker_id}: {actual_id}"

    results = await asyncio.gather(worker(1, 0.2), worker(2, 0.1), worker(3, 0.05))

    assert "Worker 1: 1" in results
    assert "Worker 2: 2" in results
    assert "Worker 3: 3" in results


def test_exception_recording() -> None:
    log_ctx.clear()
    try:
        raise ValueError("test error")
    except ValueError as e:
        log_ctx.record_exception(e)

    ctx = log_ctx.get_all()
    assert ctx["severity"] == "ERROR"
    assert ctx["error"]["type"] == "ValueError"
    assert ctx["error"]["message"] == "test error"
    assert ctx["error"]["module"] == "builtins"
