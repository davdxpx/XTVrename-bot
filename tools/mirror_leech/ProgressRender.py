# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Progress-bar formatting and throttled message-edit helper.

Mirrors the Rename / Convert visual style: double divider lines
(`━━━━━━━━━━━━━━━━━━━━`), `■ / □` progress blocks (10 chars) and the
XTVEngine signature footer.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from tools.mirror_leech.UIChrome import (
    format_bytes,
    format_elapsed,
    format_eta,
    frame,
    progress_block,
)
from utils.log import get_logger

if TYPE_CHECKING:
    from tools.mirror_leech.Tasks import MLTask

logger = get_logger("mirror_leech.progress")

_MIN_EDIT_INTERVAL = 5.0  # seconds between message edits, aligned with
                          # plugins/process.py ffmpeg_progress throttle
_last_edit: dict[str, float] = {}

_STATUS_HEADER = {
    "queued":       "⏳ **Mirror-Leech — Queued**",
    "downloading":  "⬇️ **Downloading Media...**",
    "uploading":    "☁️ **Uploading to Destination...**",
    "done":         "✅ **Mirror-Leech — Completed**",
    "failed":       "❌ **Mirror-Leech — Failed**",
    "cancelled":    "🚫 **Mirror-Leech — Cancelled**",
}


def render_task_text(task: "MLTask") -> str:
    """Render the editable progress message body for `task`."""
    header = _STATUS_HEADER.get(
        task.status, f"• **Mirror-Leech — {task.status.title()}**"
    )
    source_preview = task.source[:60] + ("…" if len(task.source) > 60 else "")

    lines: list[str] = []
    lines.append(f"> 🔗 `{source_preview}`")
    if task.downloader_id and task.uploader_ids:
        ups = ", ".join(f"`{u}`" for u in task.uploader_ids)
        lines.append(f"> 📥 `{task.downloader_id}`  →  📤 {ups}")
    lines.append("")
    lines.append(progress_block(task.progress_fraction))

    if task.status in ("downloading", "uploading") and task.speed_bps > 0:
        lines.append("")
        lines.append(
            f"> **Speed:** `{format_bytes(task.speed_bps)}/s`"
        )
        elapsed = int(time.time() - (task.started_at or time.time()))
        lines.append(
            f"> **Elapsed:** `{format_elapsed(elapsed)}` · "
            f"**ETA:** `{format_eta(task.eta_sec)}`"
        )

    if task.error:
        lines.append("")
        lines.append(f"⚠️ `{task.error}`")

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

    return frame(header, "\n".join(lines))


async def update_progress_message(client, task: "MLTask") -> None:
    """Edit the bot-owned progress message for `task`, throttled so we
    don't hammer Telegram between chunks."""
    now = time.time()
    last = _last_edit.get(task.id, 0.0)
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
