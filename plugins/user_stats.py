# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""User-facing stats panel.

Reachable from Settings → 📊 Your Stats. Shows:

 * Hero card — lifetime totals (egress, files, streak, peak day).
 * 7-day / 30-day text bar chart of daily egress.
 * Top tools + top media types (pie-chart-as-progress-bars).
 * Today's activity snapshot.

Every panel reads from ``db.usage_tracker`` so the bot's writes and UI
reads share one source of truth. Data is computed on-demand per render;
no caching layer needed because the tracker queries are indexed and
fast (single-digit ms for a 30-day window).
"""

from __future__ import annotations

import contextlib
import datetime

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db import db
from utils.telegram.log import get_logger

logger = get_logger("plugins.user_stats")

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


# --- Formatting helpers ------------------------------------------------------
def _fmt_mb(mb: float) -> str:
    """Render bytes-scaled human string from an MB float."""
    if mb < 0.01:
        return "0 MB"
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    if gb < 1024:
        return f"{gb:.2f} GB"
    return f"{gb / 1024:.2f} TB"


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days = hours // 24
    rem_hours = hours % 24
    return f"{days}d {rem_hours}h"


def _bar(value: float, max_value: float, width: int = 10) -> str:
    """Progress bar in the house style: ``[■■■■□□□□□□]``.

    Narrower (10 cells) than a classic full-block bar because the
    brackets eat two chars and the denser ``■`` glyph reads well at
    smaller widths. Empty state renders ``[□□…□]`` so the frame
    stays visible even with zero progress.
    """
    if max_value <= 0:
        return "[" + "□" * width + "]"
    filled = int(round((value / max_value) * width))
    filled = max(0, min(width, filled))
    return "[" + "■" * filled + "□" * (width - filled) + "]"


def _shorten(label: str, n: int = 14) -> str:
    return label if len(label) <= n else label[: n - 1] + "…"


# --- Chart renderers ---------------------------------------------------------
def _render_history_chart(history: list[dict], *, days_label: str) -> str:
    """Render a text bar chart of daily egress over the given history."""
    if not history:
        return "__No activity yet.__"
    reversed_hist = list(reversed(history))  # oldest first for left-to-right
    peak = max((h.get("egress_mb") or 0.0) for h in reversed_hist)
    lines = [f"📈 **{days_label} egress (MB)**"]
    for h in reversed_hist:
        date = h.get("date", "?")
        mb = float(h.get("egress_mb") or 0.0)
        lines.append(f"`{date[-5:]} {_bar(mb, peak or 1)} {_fmt_mb(mb):>9}`")
    return "\n".join(lines)


def _render_top_breakdown(
    counters: dict, *, label: str, limit: int = 5
) -> str:
    """Render a top-N list of dict-of-dicts where each value has 'egress_mb'
    and 'count'. Sorted by egress_mb desc."""
    if not counters:
        return ""
    rows: list[tuple[str, float, int]] = []
    for key, val in counters.items():
        if not isinstance(val, dict):
            continue
        rows.append(
            (
                str(key),
                float(val.get("egress_mb") or 0.0),
                int(val.get("count") or 0),
            )
        )
    if not rows:
        return ""
    rows.sort(key=lambda r: r[1], reverse=True)
    rows = rows[:limit]
    peak = rows[0][1] or 1
    out = [f"🏷 **{label}**"]
    for key, mb, cnt in rows:
        if mb == 0 and cnt == 0:
            continue
        out.append(
            f"`{_shorten(key, 14):<14}` {_bar(mb, peak, 10)} {_fmt_mb(mb):>9}  ·  {cnt}×"
        )
    return "\n".join(out)


# --- Panel renderers ---------------------------------------------------------
async def _render_main_stats(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Hero card — lifetime totals + streak + today snapshot."""
    if db.usage_tracker is None:
        return (
            f"📊 **Your Stats**\n"
            f"{DIVIDER}\n\n"
            f"__Stats are unavailable right now.__\n\n"
            f"{DIVIDER}",
            InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Settings", callback_data="user_main")]]
            ),
        )

    alltime = await db.usage_tracker.get_user_alltime(user_id)
    # Recompute streak on view so it's always fresh.
    streak_update = await db.usage_tracker.refresh_user_streak(user_id)
    if streak_update:
        alltime.update(streak_update)
    today = await db.usage_tracker.get_user_today(user_id)

    first_seen = alltime.get("first_seen_at")
    first_seen_str = "—"
    if first_seen:
        first_seen_str = datetime.datetime.utcfromtimestamp(first_seen).strftime("%Y-%m-%d")

    peak = alltime.get("peak_day") or {}
    peak_str = "—"
    if peak.get("date"):
        peak_str = f"{peak['date']} ({_fmt_mb(peak.get('egress_mb', 0))})"

    text = (
        f"📊 **Your Stats**\n"
        f"{DIVIDER}\n\n"
        f"**Lifetime**\n"
        f"• Egress: `{_fmt_mb(alltime.get('egress_mb_alltime', 0))}`\n"
        f"• Files processed: `{alltime.get('file_count_alltime', 0)}`\n"
        f"• Quota hits: `{alltime.get('quota_hits_alltime', 0)}`\n"
        f"• Batch runs: `{alltime.get('batch_runs_alltime', 0)}`\n"
        f"• First seen: `{first_seen_str}`\n"
        f"• Peak day: `{peak_str}`\n"
        f"• Current streak: `{alltime.get('current_streak_days', 0)}` day(s)\n"
        f"• Total active days: `{alltime.get('total_active_days', 0)}`\n\n"
        f"**Today ({today.get('date', '—')})**\n"
        f"• Egress: `{_fmt_mb(today.get('egress_mb', 0))}`\n"
        f"• Files: `{today.get('file_count', 0)}`\n"
        f"• Processing time: `{_fmt_duration(today.get('processing_time_seconds', 0))}`\n\n"
        f"{DIVIDER}"
    )

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📈 7-day chart", callback_data="user_stats_7d"),
                InlineKeyboardButton("📉 30-day chart", callback_data="user_stats_30d"),
            ],
            [
                InlineKeyboardButton(
                    "🎬 By media type", callback_data="user_stats_breakdown_type"
                ),
                InlineKeyboardButton(
                    "🛠 By tool", callback_data="user_stats_breakdown_tool"
                ),
            ],
            [InlineKeyboardButton("← Back to Settings", callback_data="user_main")],
        ]
    )
    return text, kb


async def _render_history(user_id: int, days: int) -> tuple[str, InlineKeyboardMarkup]:
    history = await db.usage_tracker.get_user_history(user_id, days=days)
    total_mb = sum(float(h.get("egress_mb") or 0) for h in history)
    total_files = sum(int(h.get("file_count") or 0) for h in history)
    active_days = sum(
        1 for h in history if (h.get("egress_mb") or 0) > 0 or (h.get("file_count") or 0) > 0
    )
    chart = _render_history_chart(history, days_label=f"Last {days} days")

    text = (
        f"📈 **Your last {days} days**\n"
        f"> Daily egress, newest day at the top.\n"
        f"{DIVIDER}\n\n"
        f"• Egress: `{_fmt_mb(total_mb)}`\n"
        f"• Files: `{total_files}`\n"
        f"• Active days: `{active_days}/{days}`\n"
        f"• Daily average: `{_fmt_mb(total_mb / max(1, active_days))}`\n\n"
        f"{chart}\n\n"
        f"{DIVIDER}"
    )

    other = 30 if days == 7 else 7
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"↔ Show last {other} days",
                    callback_data=f"user_stats_{other}d",
                )
            ],
            [InlineKeyboardButton("← Back", callback_data="user_stats")],
        ]
    )
    return text, kb


async def _render_breakdown(
    user_id: int, kind: str
) -> tuple[str, InlineKeyboardMarkup]:
    """kind ∈ {'type', 'tool'}."""
    alltime = await db.usage_tracker.get_user_alltime(user_id)
    today = await db.usage_tracker.get_user_today(user_id)

    if kind == "type":
        alltime_map = alltime.get("by_type_alltime") or {}
        today_map = today.get("by_type") or {}
        header = "🎬 **Breakdown by media type**"
        quote = "> Your uploads grouped by what you were renaming."
    else:
        alltime_map = alltime.get("by_tool_alltime") or {}
        today_map = today.get("by_tool") or {}
        header = "🛠 **Breakdown by tool**"
        quote = "> Which tools you reach for the most."

    lifetime_block = _render_top_breakdown(alltime_map, label="Lifetime", limit=10)
    today_block = _render_top_breakdown(today_map, label="Today", limit=5)

    body_parts = []
    if lifetime_block:
        body_parts.append(lifetime_block)
    else:
        body_parts.append("__No lifetime breakdown yet — upload some files!__")
    if today_block:
        body_parts.append(today_block)

    text = (
        f"{header}\n"
        f"{quote}\n"
        f"{DIVIDER}\n\n"
        + "\n\n".join(body_parts)
        + f"\n\n{DIVIDER}"
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="user_stats")]]
    )
    return text, kb


# --- Callback handlers -------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^user_stats$"))
async def open_user_stats(client, callback_query):
    await callback_query.answer()
    text, kb = await _render_main_stats(callback_query.from_user.id)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^user_stats_7d$"))
async def user_stats_7d(client, callback_query):
    await callback_query.answer()
    text, kb = await _render_history(callback_query.from_user.id, 7)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^user_stats_30d$"))
async def user_stats_30d(client, callback_query):
    await callback_query.answer()
    text, kb = await _render_history(callback_query.from_user.id, 30)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^user_stats_breakdown_type$"))
async def user_stats_breakdown_type(client, callback_query):
    await callback_query.answer()
    text, kb = await _render_breakdown(callback_query.from_user.id, "type")
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^user_stats_breakdown_tool$"))
async def user_stats_breakdown_tool(client, callback_query):
    await callback_query.answer()
    text, kb = await _render_breakdown(callback_query.from_user.id, "tool")
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)
