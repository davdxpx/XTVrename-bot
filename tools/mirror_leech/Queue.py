"""Persistent Mirror-Leech task queue.

The in-memory `MLWorkerPool` (Tasks.py) runs live tasks but loses
everything on process exit. This module backs the scheduler / auto-retry
work with a Mongo collection so:

  * a user can schedule an upload for later — "Tonight at 3 AM",
    "In 1 hour", custom timestamp — and it survives restarts;
  * a failed upload is retried with exponential backoff without any
    user action, capped at `max_attempts`;
  * after the cap the user receives a DM and can tap a retry button,
    which resets attempt=0 and unsticks the row.

The document shape is deliberately flat (no embedded structures beyond
the uploader list) so queries stay cheap even with thousands of rows.

State machine::

        pending  ── scheduled_at ≤ now ──►  running
                                             │
            ┌────────────── failed ──────────┤  (raised / upload error)
            │                                │
    next_retry_at ≤ now                      └──►  done  (success)
            ▼                                │
        running ◄────────────────────────────┘
            │
            ├──► permanent_fail   (attempt ≥ max_attempts)
            └──► cancelled        (user aborted)

This module is the data layer only — the worker loop that consumes
`get_ready()` + `get_retry_ready()` lives in Worker.py.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from db import db
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.queue")


# State constants kept as module-level strings rather than an Enum so
# Mongo documents are human-readable in Compass and mongosh without
# conversion. Treat them as a closed set — the worker's dispatch relies
# on exact-string matches.
STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_FAILED = "failed"
STATE_DONE = "done"
STATE_CANCELLED = "cancelled"
STATE_PERMANENT_FAIL = "permanent_fail"

DEFAULT_MAX_ATTEMPTS = 5


@dataclass
class QueueEntry:
    """Snapshot of one row in `MediaStudio-ml-queue`."""

    task_id: str
    user_id: int
    source_url: str
    downloader_id: Optional[str]
    uploader_ids: list[str]
    state: str
    scheduled_at: float
    attempt: int
    max_attempts: int
    next_retry_at: Optional[float]
    last_error: Optional[str]
    created_at: float
    updated_at: float
    result: Optional[dict] = None

    @classmethod
    def from_doc(cls, doc: dict) -> "QueueEntry":
        return cls(
            task_id=str(doc.get("task_id") or ""),
            user_id=int(doc.get("user_id") or 0),
            source_url=str(doc.get("source_url") or ""),
            downloader_id=doc.get("downloader_id") or None,
            uploader_ids=list(doc.get("uploader_ids") or []),
            state=str(doc.get("state") or STATE_PENDING),
            scheduled_at=float(doc.get("scheduled_at") or 0.0),
            attempt=int(doc.get("attempt") or 0),
            max_attempts=int(doc.get("max_attempts") or DEFAULT_MAX_ATTEMPTS),
            next_retry_at=(
                float(doc["next_retry_at"])
                if doc.get("next_retry_at") is not None
                else None
            ),
            last_error=doc.get("last_error") or None,
            created_at=float(doc.get("created_at") or 0.0),
            updated_at=float(doc.get("updated_at") or 0.0),
            result=doc.get("result") or None,
        )


# --- schema / indexes ---------------------------------------------------

_indexes_ready = False


async def ensure_indexes() -> None:
    """Idempotent. Safe to call on every worker-loop startup; Mongo
    skips indexes that already exist."""
    global _indexes_ready
    if _indexes_ready or db.ml_queue is None:
        return
    try:
        await db.ml_queue.create_index("task_id", unique=True)
        # Compound on (state, scheduled_at) — lets the scheduler scan the
        # pending rows with the earliest due times in order.
        await db.ml_queue.create_index([("state", 1), ("scheduled_at", 1)])
        await db.ml_queue.create_index([("state", 1), ("next_retry_at", 1)])
        await db.ml_queue.create_index("user_id")
    except Exception as exc:  # pragma: no cover - index create errors
        logger.warning("ml_queue index create failed: %s", exc)
        return
    _indexes_ready = True


# --- writes -------------------------------------------------------------


async def enqueue(
    user_id: int,
    source_url: str,
    downloader_id: Optional[str],
    uploader_ids: list[str],
    *,
    scheduled_at: Optional[float] = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Optional[str]:
    """Insert a new pending row. Returns the generated task_id, or None
    if the DB is unavailable (caller should fall back to a direct
    run_task invocation)."""
    if db.ml_queue is None:
        return None
    now = time.time()
    task_id = uuid.uuid4().hex[:12]
    doc = {
        "task_id": task_id,
        "user_id": int(user_id),
        "source_url": source_url,
        "downloader_id": downloader_id,
        "uploader_ids": list(uploader_ids),
        "state": STATE_PENDING,
        "scheduled_at": float(scheduled_at if scheduled_at is not None else now),
        "attempt": 0,
        "max_attempts": int(max_attempts),
        "next_retry_at": None,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
        "result": None,
    }
    try:
        await db.ml_queue.insert_one(doc)
    except Exception as exc:
        logger.warning("ml_queue enqueue failed: %s", exc)
        return None
    logger.info(
        "ml_queue enqueue: task=%s user=%s providers=%s scheduled_at=%s",
        task_id, user_id, uploader_ids, scheduled_at,
    )
    return task_id


async def mark_running(task_id: str) -> bool:
    """CAS transition pending → running. Returns True if this caller
    won the row (i.e. the worker that should execute it). Used to keep
    two worker loops from double-picking the same task after a race."""
    if db.ml_queue is None:
        return False
    res = await db.ml_queue.update_one(
        {
            "task_id": task_id,
            "state": {"$in": [STATE_PENDING, STATE_FAILED]},
        },
        {"$set": {"state": STATE_RUNNING, "updated_at": time.time()}},
    )
    return res.modified_count == 1


async def mark_failed(
    task_id: str,
    error: str,
    *,
    attempt: int,
    next_retry_at: float,
) -> None:
    """Record a transient failure; scheduler will pick it up again once
    `next_retry_at` passes. `attempt` is the *new* attempt number."""
    if db.ml_queue is None:
        return
    await db.ml_queue.update_one(
        {"task_id": task_id},
        {
            "$set": {
                "state": STATE_FAILED,
                "attempt": int(attempt),
                "next_retry_at": float(next_retry_at),
                "last_error": error[:500],
                "updated_at": time.time(),
            }
        },
    )


async def mark_permanent_failed(task_id: str, error: str) -> None:
    """Terminal failure — no more retries. The user gets a DM with a
    manual-retry button that flips the row back to pending."""
    if db.ml_queue is None:
        return
    await db.ml_queue.update_one(
        {"task_id": task_id},
        {
            "$set": {
                "state": STATE_PERMANENT_FAIL,
                "next_retry_at": None,
                "last_error": error[:500],
                "updated_at": time.time(),
            }
        },
    )


async def mark_done(task_id: str, result: Optional[dict] = None) -> None:
    if db.ml_queue is None:
        return
    await db.ml_queue.update_one(
        {"task_id": task_id},
        {
            "$set": {
                "state": STATE_DONE,
                "next_retry_at": None,
                "last_error": None,
                "result": result or None,
                "updated_at": time.time(),
            }
        },
    )


async def mark_cancelled(task_id: str) -> None:
    if db.ml_queue is None:
        return
    await db.ml_queue.update_one(
        {"task_id": task_id},
        {
            "$set": {
                "state": STATE_CANCELLED,
                "next_retry_at": None,
                "updated_at": time.time(),
            }
        },
    )


async def reset_for_manual_retry(task_id: str) -> bool:
    """Flip a permanent-failed row back to pending with attempt=0.
    Returns True if the row was reset."""
    if db.ml_queue is None:
        return False
    res = await db.ml_queue.update_one(
        {"task_id": task_id, "state": STATE_PERMANENT_FAIL},
        {
            "$set": {
                "state": STATE_PENDING,
                "attempt": 0,
                "next_retry_at": None,
                "last_error": None,
                "scheduled_at": time.time(),
                "updated_at": time.time(),
            }
        },
    )
    return res.modified_count == 1


# --- reads --------------------------------------------------------------


async def get(task_id: str) -> Optional[QueueEntry]:
    if db.ml_queue is None:
        return None
    doc = await db.ml_queue.find_one({"task_id": task_id})
    return QueueEntry.from_doc(doc) if doc else None


async def get_ready(limit: int = 10) -> list[QueueEntry]:
    """Rows in state=pending whose scheduled_at is due. Ordered
    earliest-due-first so long-overdue tasks get priority if the worker
    was paused for a while."""
    if db.ml_queue is None:
        return []
    now = time.time()
    cursor = (
        db.ml_queue.find(
            {"state": STATE_PENDING, "scheduled_at": {"$lte": now}}
        )
        .sort("scheduled_at", 1)
        .limit(int(limit))
    )
    return [QueueEntry.from_doc(d) async for d in cursor]


async def get_retry_ready(limit: int = 10) -> list[QueueEntry]:
    """Rows in state=failed whose next_retry_at is due and still under
    the max-attempts cap."""
    if db.ml_queue is None:
        return []
    now = time.time()
    cursor = (
        db.ml_queue.find(
            {
                "state": STATE_FAILED,
                "next_retry_at": {"$lte": now},
            }
        )
        .sort("next_retry_at", 1)
        .limit(int(limit))
    )
    # Cap-filter happens in Python — keeps the index slim and lets the
    # worker promote rows to permanent_fail cleanly if the cap was
    # lowered retroactively.
    out: list[QueueEntry] = []
    async for doc in cursor:
        entry = QueueEntry.from_doc(doc)
        if entry.attempt < entry.max_attempts:
            out.append(entry)
    return out


async def list_for_user(
    user_id: int,
    *,
    limit: int = 50,
    states: Optional[list[str]] = None,
) -> list[QueueEntry]:
    """Recent rows for a user, newest-first. When `states` is set, only
    rows in one of those states are returned — used by the `/mlqueue`
    UI to show pending + permanent_fail separately."""
    if db.ml_queue is None:
        return []
    query: dict[str, Any] = {"user_id": int(user_id)}
    if states:
        query["state"] = {"$in": states}
    cursor = (
        db.ml_queue.find(query).sort("created_at", -1).limit(int(limit))
    )
    return [QueueEntry.from_doc(d) async for d in cursor]


async def count_for_user(user_id: int, state: Optional[str] = None) -> int:
    if db.ml_queue is None:
        return 0
    query: dict[str, Any] = {"user_id": int(user_id)}
    if state:
        query["state"] = state
    return await db.ml_queue.count_documents(query)


async def delete(task_id: str) -> bool:
    if db.ml_queue is None:
        return False
    res = await db.ml_queue.delete_one({"task_id": task_id})
    return res.deleted_count == 1
