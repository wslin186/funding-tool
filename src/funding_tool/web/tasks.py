"""In-process async task manager.

Used by /api/history to run long-running funding-income jobs without
blocking the request. Each task's status is mirrored to a JSON file
inside ``base_dir`` so a poll that arrives after a worker restart can
still locate a terminal result (until TTL cleanup deletes it).

The manager intentionally stays single-process: it leans on asyncio's
event loop and does not need a background thread. Callers should never
share a TaskManager between event loops — construct it once at startup
and keep it on app.state.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from funding_tool.web.errors import map_core_exception


class TaskManager:
    """Submit coroutines for background execution and poll their status.

    Status dict shape:
        status:   "running" | "done" | "failed"
        progress: optional dict (currently unused, reserved for future use)
        result:   JSON-serialisable payload (set when status == "done")
        error:    {"code": str, "message": str} (set when status == "failed")
        created:  unix timestamp (seconds since epoch)
    """

    def __init__(self, base_dir: Path, ttl_seconds: int = 3600) -> None:
        self._base = base_dir
        self._base.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._status: dict[str, dict[str, Any]] = {}

    def submit(self, coro_factory: Callable[[], Awaitable[Any]]) -> str:
        """Schedule ``coro_factory()`` on the running event loop.

        Returns a hex task id callers can poll via :meth:`status`. The
        coroutine factory is deferred (rather than passing a coroutine
        directly) so the coroutine is created on the loop that will run
        it — avoids "coroutine was never awaited" warnings if creation
        fails.
        """
        task_id = uuid.uuid4().hex
        self._status[task_id] = {
            "status": "running",
            "progress": None,
            "result": None,
            "error": None,
            "created": time.time(),
        }
        loop = asyncio.get_running_loop()
        self._tasks[task_id] = loop.create_task(self._run(task_id, coro_factory))
        return task_id

    async def _run(
        self, task_id: str, factory: Callable[[], Awaitable[Any]]
    ) -> None:
        try:
            result = await factory()
            self._status[task_id]["status"] = "done"
            self._status[task_id]["result"] = result
        except Exception as e:  # noqa: BLE001 — final task barrier
            web = map_core_exception(e)
            self._status[task_id]["status"] = "failed"
            self._status[task_id]["error"] = {
                "code": web.code,
                "message": web.message,
            }
        finally:
            self._persist(task_id)
            self._tasks.pop(task_id, None)

    def _persist(self, task_id: str) -> None:
        p = self._base / f"{task_id}.json"
        # default=str so Decimals (stringified upstream by Pydantic
        # serializers) and any stray datetimes survive the dump.
        p.write_text(json.dumps(self._status[task_id], default=str))

    async def status(self, task_id: str) -> dict[str, Any]:
        if task_id in self._status:
            return self._status[task_id]
        p = self._base / f"{task_id}.json"
        if p.exists():
            return json.loads(p.read_text())
        raise KeyError(task_id)

    async def cleanup_expired(self) -> None:
        """Delete persisted task JSONs older than ``ttl_seconds``.

        Safe to call from a periodic background task. Skips files that
        fail to parse rather than letting one corrupt entry abort the
        whole sweep.
        """
        now = time.time()
        for p in self._base.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                # JSON numbers deserialize to int|float natively — no
                # explicit cast needed. (Also satisfies the no-float
                # web-layer guard.)
                created = data.get("created", 0)
                if (now - created) > self._ttl:
                    p.unlink()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                continue
