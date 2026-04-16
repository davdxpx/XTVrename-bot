"""Mirror-Leech task model and worker pool.

An `MLTask` is the unit of work — one source URL / file ref → one local
download → one or more uploads to configured destinations. `ml_worker_pool`
runs tasks with per-user + global concurrency caps and updates a shared
progress message while they run.

This module is deliberately framework-agnostic (no Pyrogram imports) so
it can be unit-tested without a real Telegram client.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from utils.log import get_logger

logger = get_logger("mirror_leech.tasks")

TaskStatus = Literal[
    "queued", "downloading", "uploading", "done", "failed", "cancelled"
]


@dataclass
class UploadResult:
    """Outcome of a single uploader running on a completed download."""

    uploader_id: str
    ok: bool
    url: Optional[str] = None
    message: str = ""


@dataclass
class MLContext:
    """Execution handle handed to downloader / uploader implementations.

    Carries the task's cancel event, progress reporter, temp-dir path, and
    user/session info the provider needs. Implementations should call
    `ctx.progress(done, total)` frequently while streaming bytes.
    """

    task_id: str
    user_id: int
    source: str
    temp_dir: Path
    cancel_event: asyncio.Event
    report_progress: Callable[[float, float, float], None]  # (done_bytes, total_bytes, speed_bps)
    report_status: Callable[[TaskStatus], None]

    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def progress(self, done: float, total: float, speed_bps: float = 0.0) -> None:
        self.report_progress(done, total, speed_bps)

    def status(self, new_status: TaskStatus) -> None:
        self.report_status(new_status)


@dataclass
class MLTask:
    """One Mirror-Leech job."""

    id: str
    user_id: int
    source: str
    downloader_id: str
    uploader_ids: list[str]

    status: TaskStatus = "queued"
    progress_fraction: float = 0.0
    speed_bps: float = 0.0
    eta_sec: int = 0

    message_chat_id: Optional[int] = None
    message_id: Optional[int] = None

    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    error: Optional[str] = None
    results: list[UploadResult] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        user_id: int,
        source: str,
        downloader_id: str,
        uploader_ids: list[str],
    ) -> "MLTask":
        return cls(
            id=uuid.uuid4().hex[:12],
            user_id=user_id,
            source=source,
            downloader_id=downloader_id,
            uploader_ids=list(uploader_ids),
        )


class MLWorkerPool:
    """In-memory task registry + concurrency-bounded runner.

    Production use will wrap `enqueue` from the callback handlers. The
    pool does not persist tasks across restarts (by design — bots crash
    mid-transfer all the time and users just retry).
    """

    def __init__(
        self,
        *,
        max_concurrent_per_user: int = 2,
        max_global_concurrent: int = 10,
    ) -> None:
        self.max_concurrent_per_user = max_concurrent_per_user
        self.max_global_concurrent = max_global_concurrent
        self._global_sem = asyncio.Semaphore(max_global_concurrent)
        self._user_sems: dict[int, asyncio.Semaphore] = {}
        self._tasks: dict[str, MLTask] = {}
        self._running: dict[str, asyncio.Task] = {}

    # ----- lookup ---------------------------------------------------------

    def get(self, task_id: str) -> Optional[MLTask]:
        return self._tasks.get(task_id)

    def list_for_user(self, user_id: int) -> list[MLTask]:
        return sorted(
            (t for t in self._tasks.values() if t.user_id == user_id),
            key=lambda t: t.created_at,
            reverse=True,
        )

    def active_count(self, user_id: int) -> int:
        return sum(
            1
            for t in self._tasks.values()
            if t.user_id == user_id and t.status in ("queued", "downloading", "uploading")
        )

    # ----- execution ------------------------------------------------------

    def _user_sem(self, user_id: int) -> asyncio.Semaphore:
        sem = self._user_sems.get(user_id)
        if sem is None:
            sem = asyncio.Semaphore(self.max_concurrent_per_user)
            self._user_sems[user_id] = sem
        return sem

    def enqueue(
        self,
        task: MLTask,
        runner: Callable[[MLTask], Any],
    ) -> None:
        """Register `task` and start an asyncio.Task that awaits the
        semaphores then invokes `runner(task)`. `runner` is an async
        callable supplied by the controller (dependency injection keeps
        this module framework-agnostic)."""
        self._tasks[task.id] = task

        async def _wrapped():
            async with self._global_sem, self._user_sem(task.user_id):
                task.started_at = time.time()
                try:
                    await runner(task)
                    if task.status not in ("failed", "cancelled"):
                        task.status = "done"
                except asyncio.CancelledError:
                    task.status = "cancelled"
                    raise
                except Exception as exc:
                    logger.exception("MLTask %s failed", task.id)
                    task.status = "failed"
                    task.error = str(exc)
                finally:
                    task.finished_at = time.time()
                    self._running.pop(task.id, None)

        self._running[task.id] = asyncio.create_task(_wrapped())

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.cancel_event.set()
        running = self._running.get(task_id)
        if running and not running.done():
            running.cancel()
        return True

    async def shutdown(self) -> None:
        """Cancel all running tasks — called from main.py on shutdown."""
        for task_id in list(self._running.keys()):
            self.cancel(task_id)
        if self._running:
            await asyncio.gather(*self._running.values(), return_exceptions=True)


# Singleton instance imported by the rest of the subsystem.
ml_worker_pool = MLWorkerPool()
