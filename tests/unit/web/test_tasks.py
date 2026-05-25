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
