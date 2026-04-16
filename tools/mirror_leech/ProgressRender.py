"""Progress-bar formatting and throttled message-edit helper.

Reuses utils.progress for the throttling math so we don't invent a second
rate-limit. Every update pulls the current task state and patches the
bot-owned message that the user is watching.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from utils.log import get_logger

if TYPE_CHECKING:
    from tools.mirror_leech.Tasks import MLTask

logger = get_logger("mirror_leech.progress")

_MIN_EDIT_INTERVAL = 3.0  # seconds between message edits
_last_edit: dict[str, float] = {}

_BAR_LENGTH = 20


def format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_eta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def progress_bar(fraction: float) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(fraction * _BAR_LENGTH)
    return "█" * filled + "░" * (_BAR_LENGTH - filled)


def render_task_text(task: "MLTask") -> str:
    """Render an editable progress message body for `task`."""
    status_icon = {
        "queued": "⏳",
        "downloading": "⬇️",
        "uploading": "☁️",
        "done": "✅",
        "failed": "❌",
        "cancelled": "🚫",
    }.get(task.status, "•")

    fraction = task.progress_fraction
    lines = [
        f"{status_icon} **Mirror-Leech — {task.status.title()}**",
        f"`{task.source[:60]}`",
        "",
        f"`[{progress_bar(fraction)}]` {fraction * 100:.1f}%",
    ]
    if task.speed_bps > 0:
        lines.append(f"⚡ {format_bytes(task.speed_bps)}/s   ⌛ {format_eta(task.eta_sec)}")
    if task.downloader_id:
        lines.append(f"📥 `{task.downloader_id}`  →  📤 {', '.join(f'`{u}`' for u in task.uploader_ids)}")
    if task.error:
        lines.append("")
        lines.append(f"⚠️ {task.error}")
    if task.results:
        lines.append("")
        lines.append("**Results**")
        for r in task.results:
            if r.ok and r.url:
                lines.append(f"• `{r.uploader_id}`: {r.url}")
            elif r.ok:
                lines.append(f"• `{r.uploader_id}`: ✅")
            else:
                lines.append(f"• `{r.uploader_id}`: ❌ {r.message}")
    return "\n".join(lines)


async def update_progress_message(client, task: "MLTask") -> None:
    """Edit the bot-owned progress message for `task`, throttled to one
    edit per ~3s per task. Safe to call on every chunk boundary."""
    now = time.time()
    last = _last_edit.get(task.id, 0.0)
    # Always edit on terminal statuses so the final state is visible.
    terminal = task.status in ("done", "failed", "cancelled")
    if not terminal and now - last < _MIN_EDIT_INTERVAL:
        return
    _last_edit[task.id] = now

    if task.message_chat_id is None or task.message_id is None:
        return
    try:
        await client.edit_message_text(
            chat_id=task.message_chat_id,
            message_id=task.message_id,
            text=render_task_text(task),
        )
    except Exception as exc:
        logger.debug("progress edit suppressed for task %s: %s", task.id, exc)
