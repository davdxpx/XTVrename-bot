"""Hardened wrappers for fire-and-forget asyncio tasks.

Plain `asyncio.create_task(coro())` swallows any exception the coroutine
raises — the task simply dies, the user sees nothing, the logs stay clean.
Across XTV-MediaStudio we create ~20 such tasks (file processing, batch
sweeping, session persistence). This module gives them:

* an on-done callback that logs any uncaught exception
* optional user-facing error reporting
* a global registry keyed by user_id so we can cancel them
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from utils.telegram.log import get_logger

logger = get_logger("utils.tasks")

# user_id → set of active tasks. Using a set allows multiple parallel tasks
# per user (batch processing spawns several). Pop on done.
_active_tasks: Dict[int, Set[asyncio.Task]] = {}

# Optional keyed registry — used so a UI cancel button (keyed by status-message id)
# can cancel exactly the task that owns that status message.
_keyed_tasks: Dict[Any, asyncio.Task] = {}


def _on_task_done(task: asyncio.Task, user_id: Optional[int], label: str,
                  on_error: Optional[Callable[[BaseException], Awaitable[None]]],
                  key: Any = None):
    # Remove from registry first so cancel loops don't revisit.
    if user_id is not None:
        bucket = _active_tasks.get(user_id)
        if bucket is not None:
            bucket.discard(task)
            if not bucket:
                _active_tasks.pop(user_id, None)
    if key is not None and _keyed_tasks.get(key) is task:
        _keyed_tasks.pop(key, None)

    if task.cancelled():
        logger.debug(f"[task:{label}] cancelled (user={user_id})")
        return

    exc = task.exception()
    if exc is None:
        return

    logger.exception(
        f"[task:{label}] unhandled exception for user={user_id}: {exc}",
        exc_info=exc,
    )

    if on_error is not None:
        try:
            # Fire-and-forget the error reporter — but at least log if *it* fails.
            reporter = asyncio.ensure_future(on_error(exc))

            def _report_done(t: asyncio.Task):
                if t.cancelled():
                    return
                e2 = t.exception()
                if e2:
                    logger.warning(f"[task:{label}] on_error reporter failed: {e2}")

            reporter.add_done_callback(_report_done)
        except Exception as e:
            logger.warning(f"[task:{label}] could not schedule on_error: {e}")


def spawn(
    coro: Awaitable[Any],
    *,
    user_id: Optional[int] = None,
    label: str = "unnamed",
    on_error: Optional[Callable[[BaseException], Awaitable[None]]] = None,
    key: Any = None,
) -> asyncio.Task:
    """Create an asyncio.Task with error logging + cancel registry.

    Always prefer this over `asyncio.create_task` for any long-running
    coroutine that isn't already awaited by the caller.

    Pass `key` (e.g. status_message_id) to support direct keyed cancellation
    via `cancel_by_key(key)`.
    """
    task = asyncio.create_task(coro, name=label)
    if user_id is not None:
        _active_tasks.setdefault(user_id, set()).add(task)
    if key is not None:
        _keyed_tasks[key] = task
    task.add_done_callback(
        lambda t: _on_task_done(t, user_id, label, on_error, key)
    )
    return task


def cancel_by_key(key: Any) -> bool:
    """Cancel the task registered under the given key. Returns True if a
    task was live and got cancelled."""
    task = _keyed_tasks.get(key)
    if task is not None and not task.done():
        task.cancel()
        return True
    return False


def active_tasks(user_id: int) -> Set[asyncio.Task]:
    """Return the (live) set of active tasks for a user. Empty set if none."""
    return set(_active_tasks.get(user_id, set()))


def cancel_user_tasks(user_id: int) -> int:
    """Cancel every live task for a user. Returns how many were cancelled."""
    bucket = _active_tasks.get(user_id)
    if not bucket:
        return 0
    cancelled = 0
    for t in list(bucket):
        if not t.done():
            t.cancel()
            cancelled += 1
    return cancelled


def cancel_task_by_name(user_id: int, label: str) -> int:
    """Cancel tasks with a given label for a user (exact match)."""
    bucket = _active_tasks.get(user_id)
    if not bucket:
        return 0
    cancelled = 0
    for t in list(bucket):
        if t.get_name() == label and not t.done():
            t.cancel()
            cancelled += 1
    return cancelled


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
