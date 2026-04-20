"""Background worker that drains the persistent Mirror-Leech queue.

Polls `Queue.get_ready()` and `Queue.get_retry_ready()` every 30 s,
CAS-acquires each due row, and hands it to `Runner.run_task` inside
the in-memory `ml_worker_pool` so the per-user / global concurrency
caps still apply.

On a transient failure the row is marked failed with `next_retry_at =
now + min(5 * (2 ** attempt), 60) * 60` (5 min, 10 min, 20 min, 40 min,
60 min, …). Once `attempt >= max_attempts` the row flips to
`permanent_fail` and the user gets a DM with a manual-retry button.

The worker is deliberately best-effort — if Mongo is offline the loop
just keeps looping with a debug log. It does NOT take over the
foreground `/ml` flow: live tasks still run through `ml_go` without
touching this queue.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from tools.mirror_leech import Queue
from tools.mirror_leech.Runner import run_task
from tools.mirror_leech.Tasks import MLTask, ml_worker_pool
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.worker")

POLL_INTERVAL_SEC = 30
BATCH_SIZE = 10
_BACKOFF_MINUTES_CAP = 60
_BACKOFF_MINUTES_BASE = 5

_started = False


def _backoff_seconds(attempt: int) -> float:
    """Exponential with a ceiling: 5, 10, 20, 40, 60, 60, …
    (attempt is the *new* attempt number, 1-indexed)."""
    minutes = min(
        _BACKOFF_MINUTES_BASE * (2 ** max(attempt - 1, 0)),
        _BACKOFF_MINUTES_CAP,
    )
    return minutes * 60.0


async def _notify_permanent_failure(
    client: Any, entry: Queue.QueueEntry
) -> None:
    """DM the user with a manual-retry button. Swallows errors — a
    blocked-bot user or deleted chat must not kill the worker loop."""
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    text = (
        f"❌ **Mirror-Leech task failed permanently**\n\n"
        f"> Source: `{entry.source_url[:120]}`\n"
        f"> Destinations: {', '.join(entry.uploader_ids) or '—'}\n"
        f"> Attempts: {entry.attempt}/{entry.max_attempts}\n"
        f"> Last error: `{(entry.last_error or '')[:200]}`\n\n"
        "Tap below to retry from scratch (attempt counter resets)."
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔁 Retry now", callback_data=f"ml_retry_{entry.task_id}"
                ),
                InlineKeyboardButton(
                    "🗑 Dismiss", callback_data=f"ml_qdrop_{entry.task_id}"
                ),
            ]
        ]
    )
    try:
        await client.send_message(entry.user_id, text, reply_markup=kb)
    except Exception as exc:
        logger.debug(
            "permanent-fail DM to %s for task %s failed: %s",
            entry.user_id, entry.task_id, exc,
        )


def _entry_to_task(entry: Queue.QueueEntry) -> MLTask:
    """Lift a persistent queue row into the in-memory task model so the
    existing Runner can execute it unchanged."""
    t = MLTask(
        id=entry.task_id,
        user_id=entry.user_id,
        source=entry.source_url,
        downloader_id=entry.downloader_id or "",
        uploader_ids=list(entry.uploader_ids),
    )
    # created_at on the in-memory model is informational; use the DB
    # value so the /mlqueue UI reports the original request time.
    t.created_at = entry.created_at
    return t


async def _execute_entry(client: Any, entry: Queue.QueueEntry) -> None:
    """Run one queue row end-to-end and persist the outcome. Does NOT
    raise — exceptions are caught and routed into mark_failed /
    mark_permanent_failed so the worker loop keeps running."""
    task = _entry_to_task(entry)

    try:
        # Hand the task to the in-memory pool so per-user + global
        # concurrency caps still apply. The pool's _wrapped sets
        # status=done/failed/cancelled when the runner returns.
        done_event = asyncio.Event()

        async def _runner(t: MLTask) -> None:
            try:
                await run_task(t, client, progress_cb=None)
            finally:
                done_event.set()

        ml_worker_pool.enqueue(task, _runner)
        await done_event.wait()
    except Exception as exc:
        logger.exception(
            "Worker: unexpected error running %s: %s", entry.task_id, exc
        )
        task.status = "failed"
        task.error = str(exc)

    # --- Persist outcome ---
    if task.status == "done":
        # Strip results to a shallow serializable dict; avoid storing the
        # full MLTask (it contains asyncio.Event which doesn't serialise).
        result_payload = {
            "uploads": [
                {
                    "uploader": r.uploader_id,
                    "ok": r.ok,
                    "url": r.url,
                    "message": r.message,
                }
                for r in task.results
            ]
        }
        await Queue.mark_done(entry.task_id, result_payload)
        logger.info(
            "Worker: task %s done (attempt %d)",
            entry.task_id, entry.attempt + 1,
        )
        return

    if task.status == "cancelled":
        await Queue.mark_cancelled(entry.task_id)
        logger.info("Worker: task %s cancelled", entry.task_id)
        return

    # Failure path — decide retry vs. permanent.
    error = task.error or "unknown error"
    new_attempt = entry.attempt + 1
    if new_attempt >= entry.max_attempts:
        await Queue.mark_permanent_failed(entry.task_id, error)
        logger.warning(
            "Worker: task %s hit max attempts (%d), permanent fail",
            entry.task_id, entry.max_attempts,
        )
        # Refresh the row so the DM reflects the cap hit.
        refreshed = await Queue.get(entry.task_id) or entry
        await _notify_permanent_failure(client, refreshed)
        return

    next_at = time.time() + _backoff_seconds(new_attempt)
    await Queue.mark_failed(
        entry.task_id,
        error,
        attempt=new_attempt,
        next_retry_at=next_at,
    )
    logger.info(
        "Worker: task %s failed (attempt %d/%d), retry in %.0fs: %s",
        entry.task_id, new_attempt, entry.max_attempts,
        next_at - time.time(), error[:120],
    )


async def _tick(client: Any) -> None:
    """One pass through the queue — scheduled rows first, then retries."""
    try:
        ready = await Queue.get_ready(limit=BATCH_SIZE)
        retry_ready = await Queue.get_retry_ready(limit=BATCH_SIZE)
    except Exception as exc:
        logger.debug("Worker tick read failed: %s", exc)
        return

    for entry in list(ready) + list(retry_ready):
        # CAS: only the first worker to flip pending/failed → running wins.
        won = await Queue.mark_running(entry.task_id)
        if not won:
            continue
        # Re-read so attempt / error fields reflect the CAS'd state.
        current = await Queue.get(entry.task_id) or entry
        # Fire-and-forget so one slow task doesn't block the loop.
        asyncio.create_task(_execute_entry(client, current))


async def worker_loop(client: Any) -> None:
    """Top-level coroutine. Runs forever; cancelling the Task stops it."""
    await Queue.ensure_indexes()
    logger.info(
        "Mirror-Leech worker loop started (poll=%ds, batch=%d)",
        POLL_INTERVAL_SEC, BATCH_SIZE,
    )
    while True:
        try:
            await _tick(client)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Worker tick crashed: %s", exc)
        await asyncio.sleep(POLL_INTERVAL_SEC)


def start(client: Any) -> None:
    """Schedule the worker loop on the given Pyrogram client's event
    loop. Idempotent — a second call is a no-op."""
    global _started
    if _started:
        return
    _started = True
    client.loop.create_task(worker_loop(client))
