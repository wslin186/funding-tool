"""Unit tests for the in-process async TaskManager."""
import asyncio
from pathlib import Path

import pytest

from funding_tool.web.tasks import TaskManager


async def test_submit_and_poll_done(tmp_path: Path) -> None:
    tm = TaskManager(tmp_path)

    async def work():
        await asyncio.sleep(0.01)
        return {"answer": 42}

    tid = tm.submit(work)
    s = None
    for _ in range(50):
        s = await tm.status(tid)
        if s["status"] == "done":
            break
        await asyncio.sleep(0.02)
    assert s is not None
    assert s["status"] == "done"
    assert s["result"] == {"answer": 42}


async def test_failed_task_records_error(tmp_path: Path) -> None:
    tm = TaskManager(tmp_path)

    async def boom():
        raise ValueError("nope")

    tid = tm.submit(boom)
    s = None
    for _ in range(50):
        s = await tm.status(tid)
        if s["status"] == "failed":
            break
        await asyncio.sleep(0.02)
    assert s is not None
    assert s["status"] == "failed"
    assert s["error"]["code"]


async def test_unknown_task_id(tmp_path: Path) -> None:
    tm = TaskManager(tmp_path)
    with pytest.raises(KeyError):
        await tm.status("nope")


async def test_status_falls_back_to_persisted_file(tmp_path) -> None:
    """When in-memory status is gone, status() reads from JSON."""
    tm = TaskManager(base_dir=tmp_path)
    async def work():
        return {"value": 42}
    task_id = tm.submit(work)
    # Wait for completion + persist
    await asyncio.sleep(0.05)
    # Simulate process restart / eviction: clear in-memory state
    tm._status.clear()
    st = await tm.status(task_id)
    assert st["status"] == "done"
    assert st["result"] == {"value": 42}


async def test_cleanup_expired_removes_stale_files(tmp_path) -> None:
    """cleanup_expired deletes JSON files older than TTL."""
    import json
    import time as _time
    tm = TaskManager(base_dir=tmp_path, ttl_seconds=10)
    # Stale: created 1 hour ago
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps({"status": "done", "created": _time.time() - 3600}))
    # Fresh: just now
    fresh = tmp_path / "fresh.json"
    fresh.write_text(json.dumps({"status": "done", "created": _time.time()}))
    await tm.cleanup_expired()
    assert not stale.exists()
    assert fresh.exists()
