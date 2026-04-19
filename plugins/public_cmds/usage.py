# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""plugins.public_cmds.usage — ``/usage`` command + ``refresh_usage`` callback.

Mode: PUBLIC-ONLY. In non-public mode there are no per-user egress or
file-count limits, so ``/usage`` is a no-op there.

The render layout follows the bot's wider design language: a ━ separator
under the header (and optional admin badge), dim blockquotes wrapping
the numeric blocks, and a single ``>`` quoted hint for the reset timer.
"""

from __future__ import annotations

import contextlib
import datetime

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from utils.log import get_logger

logger = get_logger("plugins.public_cmds.usage")


def _is_public_mode() -> bool:
    return bool(Config.PUBLIC_MODE)


def format_egress(mb: float) -> str:
    if mb >= 1048576:
        return f"{mb / 1048576:.2f} TB"
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.2f} MB"


async def _send_usage(client, target, user_id: int, is_callback: bool = False) -> None:
    is_admin_user = user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS

    config = await db.get_public_config()
    daily_egress_mb_limit = config.get("daily_egress_mb", 0)
    daily_file_count_limit = config.get("daily_file_count", 0)
    global_limit_mb = await db.get_global_daily_egress_limit()

    usage = await db.get_user_usage(user_id)

    current_utc = datetime.datetime.now(datetime.timezone.utc)
    current_utc_date = current_utc.strftime("%Y-%m-%d")
    current_date_display = current_utc.strftime("%d %b %Y")

    tomorrow = current_utc + datetime.timedelta(days=1)
    midnight = datetime.datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=datetime.timezone.utc
    )
    time_to_midnight = midnight - current_utc
    hours, remainder = divmod(int(time_to_midnight.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)

    files_today = 0
    egress_today_mb = 0.0
    if usage.get("date") == current_utc_date:
        files_today = usage.get("file_count", 0)
        egress_today_mb = usage.get("egress_mb", 0.0)

    files_alltime = usage.get("file_count_alltime", 0)
    egress_alltime_mb = usage.get("egress_mb_alltime", 0.0)

    if is_admin_user:
        files_limit_str = "Unlimited"
        if global_limit_mb > 0:
            egress_limit_str = format_egress(global_limit_mb) + " (Global)"
            limit_to_check = global_limit_mb
        else:
            egress_limit_str = "Unlimited"
            limit_to_check = 0
        percent_files = 0.0
        percent_egress = (
            (egress_today_mb / global_limit_mb) * 100 if global_limit_mb > 0 else 0.0
        )
    else:
        files_limit_str = (
            f"{daily_file_count_limit}" if daily_file_count_limit > 0 else "Unlimited"
        )

        limit_to_check = daily_egress_mb_limit
        if global_limit_mb > 0 and (
            daily_egress_mb_limit <= 0 or global_limit_mb < daily_egress_mb_limit
        ):
            limit_to_check = global_limit_mb

        egress_limit_str = (
            format_egress(limit_to_check) if limit_to_check > 0 else "Unlimited"
        )

        percent_files = (
            (files_today / daily_file_count_limit) * 100
            if daily_file_count_limit > 0
            else 0.0
        )
        percent_egress = (
            (egress_today_mb / limit_to_check) * 100 if limit_to_check > 0 else 0.0
        )

    max_percent = min(max(percent_files, percent_egress), 100.0)
    filled_blocks = int((max_percent / 100) * 10)
    empty_blocks = 10 - filled_blocks
    progress_bar = ("■" * filled_blocks) + ("□" * empty_blocks)

    has_limits = limit_to_check > 0 or (
        not is_admin_user and daily_file_count_limit > 0
    )

    # Layout — matches the bot's wider design language:
    #   [admin badge + ─── separator]
    #   📊 header + ━━━ separator
    #   <blockquote>Today block</blockquote>
    #   <blockquote>All-Time block</blockquote>
    #   > Resets at midnight UTC (in …)
    lines: list[str] = []

    if is_admin_user:
        lines.append("👑 **Admin Account**")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

    lines.append(f"📊 **Your Usage — {current_date_display}**")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    today_block = [
        "<blockquote>**Today**",
        f"📁 Files: `{files_today} / {files_limit_str}`",
        f"📦 Egress: `{format_egress(egress_today_mb)} / {egress_limit_str}`",
    ]
    if has_limits:
        today_block.append(f"`{progress_bar}` {max_percent:.1f}%")
    else:
        today_block.append("__(No limits currently applied)__")
    today_block[-1] = today_block[-1] + "</blockquote>"
    lines.extend(today_block)
    lines.append("")

    lines.append("<blockquote>**All-Time**")
    lines.append(f"📁 Files: `{files_alltime}`")
    lines.append(f"📦 Egress: `{format_egress(egress_alltime_mb)}`</blockquote>")
    lines.append("")

    lines.append(f"> Resets at midnight UTC (in ~{hours}h {minutes}m)")

    text = "\n".join(lines)

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Refresh", callback_data="refresh_usage")]]
    )

    if is_callback:
        with contextlib.suppress(MessageNotModified):
            await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


@Client.on_message(filters.command("usage") & filters.private, group=0)
async def usage_command(client, message):
    if not _is_public_mode():
        return
    await _send_usage(client, message, message.from_user.id, False)


@Client.on_callback_query(filters.regex(r"^refresh_usage$"))
async def refresh_usage_cb(client, callback_query):
    with contextlib.suppress(Exception):
        await callback_query.answer("Refreshed!")
    if not _is_public_mode():
        return
    await _send_usage(
        client, callback_query.message, callback_query.from_user.id, True
    )
