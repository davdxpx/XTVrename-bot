# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Admin Usage Stats panel.

Reachable from /admin → 📈 Usage Stats. Shows:

 * Global today hero card with quota-cap gauge.
 * 30-day global history bar chart.
 * Top users today / this week / lifetime.
 * Per-media-type + per-tool global breakdowns.
 * Admin-only "Purge old data" action (ad-hoc cleanup — TTL indexes
   usually handle this automatically).

Every panel sources data from ``db.usage_tracker`` and its backing
collections introduced in PR E.
"""

from __future__ import annotations

import contextlib
import datetime

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db import db
from plugins.admin.core import is_admin
from utils.telegram.log import get_logger

logger = get_logger("plugins.admin.usage_stats")

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


# --- Shared formatting -------------------------------------------------------
def _fmt_mb(mb: float) -> str:
    if mb < 0.01:
        return "0 MB"
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    if gb < 1024:
        return f"{gb:.2f} GB"
    return f"{gb / 1024:.2f} TB"


def _bar(value: float, max_value: float, width: int = 14) -> str:
    if max_value <= 0:
        return "░" * width
    filled = int(round((value / max_value) * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _shorten(label: str, n: int = 14) -> str:
    return label if len(label) <= n else label[: n - 1] + "…"


def _format_user_row(row: dict) -> str:
    uid = row.get("uid") or row.get("_id") or "?"
    egress = float(row.get("egress_mb") or 0.0)
    files = int(row.get("file_count") or 0)
    return f"`{str(uid):<12}` {_fmt_mb(egress):>9}  ·  {files}× files"


# --- Panel renderers ---------------------------------------------------------
async def _render_hero(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    if db.usage_tracker is None:
        return (
            "📈 **Usage Stats**\n\n_Stats are unavailable right now._",
            InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data="admin_panel")]]),
        )
    today = await db.usage_tracker.get_global_today()
    cap_mb = await db.get_global_daily_egress_limit()
    used_mb = float(today.get("total_egress_mb") or 0.0)
    unique_users = len(today.get("unique_user_ids") or [])
    file_count = int(today.get("total_file_count") or 0)

    if cap_mb > 0:
        used_pct = min(100.0, (used_mb / cap_mb) * 100) if cap_mb else 0
        gauge = f"`{_bar(used_mb, cap_mb, 18)}` `{used_pct:5.1f}%`"
        cap_line = f"Cap: `{_fmt_mb(cap_mb)}`  ·  Used: `{_fmt_mb(used_mb)}`"
    else:
        gauge = "`(no daily cap configured)`"
        cap_line = f"Used: `{_fmt_mb(used_mb)}`"

    date = today.get("date", datetime.datetime.utcnow().strftime("%Y-%m-%d"))

    text = (
        f"📈 **Usage Stats**\n"
        f"{DIVIDER}\n\n"
        f"**Today ({date})**\n"
        f"{gauge}\n"
        f"{cap_line}\n"
        f"• Unique users: `{unique_users}`\n"
        f"• Files processed: `{file_count}`\n"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 30-day history", callback_data="admin_usage_history"
                ),
                InlineKeyboardButton(
                    "🏆 Leaderboards", callback_data="admin_usage_leaderboard_today"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🎬 By media type", callback_data="admin_usage_by_type"
                ),
                InlineKeyboardButton(
                    "🛠 By tool", callback_data="admin_usage_by_tool"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🧹 Purge old data", callback_data="admin_usage_purge_confirm"
                ),
            ],
            [InlineKeyboardButton("← Back to Admin", callback_data="admin_panel")],
        ]
    )
    return text, kb


async def _render_history() -> tuple[str, InlineKeyboardMarkup]:
    if db.usage_tracker is None:
        return ("Stats unavailable.", InlineKeyboardMarkup([]))
    history = await db.usage_tracker.get_global_history(30)
    if not history:
        text = (
            "📊 **Global history (30 days)**\n"
            f"{DIVIDER}\n\n_No data yet._"
        )
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back", callback_data="admin_usage")]]
        )
        return text, kb
    reversed_hist = list(reversed(history))
    peak = max((float(h.get("total_egress_mb") or 0.0)) for h in reversed_hist)
    chart_lines = ["📊 **Global history (last 30 days)**", DIVIDER, ""]
    total = 0.0
    for h in reversed_hist:
        date = h.get("date", "?")
        mb = float(h.get("total_egress_mb") or 0.0)
        total += mb
        chart_lines.append(
            f"`{date[-5:]} {_bar(mb, peak or 1)} {_fmt_mb(mb):>9}`"
        )
    chart_lines.append("")
    chart_lines.append(f"**Window total:** `{_fmt_mb(total)}`")
    text = "\n".join(chart_lines)
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="admin_usage")]]
    )
    return text, kb


async def _render_leaderboard(scope: str) -> tuple[str, InlineKeyboardMarkup]:
    if db.usage_tracker is None:
        return ("Stats unavailable.", InlineKeyboardMarkup([]))

    if scope == "today":
        rows, _total = await db.usage_tracker.get_leaderboard_today(limit=10)
        title = "🏆 Leaderboard — Today"
    elif scope == "7d":
        today = datetime.datetime.utcnow().date()
        start = today - datetime.timedelta(days=6)
        rows = await db.usage_tracker.get_leaderboard_period(
            start.strftime("%Y-%m-%d"),
            today.strftime("%Y-%m-%d"),
            limit=10,
        )
        title = "🏆 Leaderboard — Last 7 days"
    else:
        rows = await db.usage_tracker.get_leaderboard_alltime(limit=10)
        # Normalise lifetime rows so the formatter can reuse _format_user_row.
        rows = [
            {
                "uid": r.get("uid") or r.get("_id"),
                "egress_mb": r.get("egress_mb_alltime", 0),
                "file_count": r.get("file_count_alltime", 0),
            }
            for r in rows
        ]
        title = "🏆 Leaderboard — Lifetime"

    if not rows:
        body = "_No entries yet._"
    else:
        body_lines = []
        for i, row in enumerate(rows, start=1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i:>2}.")
            body_lines.append(f"{medal} {_format_user_row(row)}")
        body = "\n".join(body_lines)

    text = f"{title}\n{DIVIDER}\n\n{body}"
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    ("· Today ·" if scope == "today" else "Today"),
                    callback_data="admin_usage_leaderboard_today",
                ),
                InlineKeyboardButton(
                    ("· 7 days ·" if scope == "7d" else "7 days"),
                    callback_data="admin_usage_leaderboard_7d",
                ),
                InlineKeyboardButton(
                    ("· Lifetime ·" if scope == "lifetime" else "Lifetime"),
                    callback_data="admin_usage_leaderboard_lifetime",
                ),
            ],
            [InlineKeyboardButton("← Back", callback_data="admin_usage")],
        ]
    )
    return text, kb


async def _render_global_breakdown(kind: str) -> tuple[str, InlineKeyboardMarkup]:
    """kind ∈ {'type', 'tool'}."""
    if db.usage_tracker is None:
        return ("Stats unavailable.", InlineKeyboardMarkup([]))
    today = await db.usage_tracker.get_global_today()
    # Sum over last 30 days for the "lifetime-ish" panel.
    history = await db.usage_tracker.get_global_history(30)

    if kind == "type":
        today_map = today.get("by_type_totals") or {}
        history_key = "by_type_totals"
        header = "🎬 **Global breakdown — media type**"
    else:
        today_map = today.get("by_tool_totals") or {}
        history_key = "by_tool_totals"
        header = "🛠 **Global breakdown — tool**"

    # Aggregate over last 30 days from history.
    agg: dict[str, dict] = {}
    for h in history:
        bucket = h.get(history_key) or {}
        for key, val in bucket.items():
            if not isinstance(val, dict):
                continue
            node = agg.setdefault(key, {"egress_mb": 0.0, "count": 0})
            node["egress_mb"] += float(val.get("egress_mb") or 0.0)
            node["count"] += int(val.get("count") or 0)

    def _render_list(data: dict, title: str) -> str:
        rows: list[tuple[str, float, int]] = []
        for key, val in data.items():
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
            return f"**{title}**\n_No data._"
        rows.sort(key=lambda r: r[1], reverse=True)
        rows = rows[:10]
        peak = rows[0][1] or 1
        lines = [f"**{title}**"]
        for key, mb, cnt in rows:
            if mb == 0 and cnt == 0:
                continue
            lines.append(
                f"`{_shorten(key, 16):<16}` {_bar(mb, peak, 10)} {_fmt_mb(mb):>9}  ·  {cnt}×"
            )
        return "\n".join(lines)

    text_parts = [header, DIVIDER, ""]
    text_parts.append(_render_list(today_map, "Today"))
    text_parts.append("")
    text_parts.append(_render_list(agg, "Last 30 days"))
    text = "\n".join(text_parts)

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="admin_usage")]]
    )
    return text, kb


async def _render_purge_confirm() -> tuple[str, InlineKeyboardMarkup]:
    from db import schema
    text = (
        "🧹 **Purge old usage data**\n"
        f"{DIVIDER}\n\n"
        f"This will delete:\n"
        f"• Per-user daily docs older than **{schema.USAGE_TTL_DAYS} days**.\n"
        f"• Global daily docs older than **{schema.USAGE_DAILY_GLOBAL_TTL_DAYS} days**.\n\n"
        f"TTL indexes usually handle this automatically. Only use this if\n"
        f"you want to free space *now* rather than waiting for MongoDB's\n"
        f"60-second TTL sweep.\n\n"
        f"Continue?"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Yes, purge now", callback_data="admin_usage_purge_run"
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="admin_usage"),
            ]
        ]
    )
    return text, kb


async def _run_purge() -> tuple[str, InlineKeyboardMarkup]:
    user_stats = await db.usage_tracker.purge_old_days()
    global_stats = await db.usage_tracker.purge_old_global_days()
    text = (
        "✅ **Purge complete**\n"
        f"{DIVIDER}\n\n"
        f"• User-day docs deleted: `{user_stats.get('deleted', 0)}`\n"
        f"   cutoff: `{user_stats.get('cutoff', '?')}`\n"
        f"• Global-day docs deleted: `{global_stats.get('deleted', 0)}`\n"
        f"   cutoff: `{global_stats.get('cutoff', '?')}`\n"
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back", callback_data="admin_usage")]]
    )
    return text, kb


# --- Callback handlers -------------------------------------------------------
def _admin_gate(callback_query) -> bool:
    if is_admin(callback_query.from_user.id):
        return True
    # Fire-and-forget — Pyrogram discards the coroutine, but the alert fires.
    import asyncio
    asyncio.ensure_future(
        callback_query.answer("Admins only.", show_alert=True)
    )
    return False


@Client.on_callback_query(filters.regex(r"^admin_usage$"))
async def admin_usage_hero(client, callback_query):
    if not _admin_gate(callback_query):
        return
    await callback_query.answer()
    text, kb = await _render_hero(callback_query.from_user.id)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^admin_usage_history$"))
async def admin_usage_history(client, callback_query):
    if not _admin_gate(callback_query):
        return
    await callback_query.answer()
    text, kb = await _render_history()
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^admin_usage_leaderboard_(today|7d|lifetime)$"))
async def admin_usage_leaderboard(client, callback_query):
    if not _admin_gate(callback_query):
        return
    await callback_query.answer()
    scope = callback_query.data.rsplit("_", 1)[-1]
    text, kb = await _render_leaderboard(scope)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^admin_usage_by_type$"))
async def admin_usage_by_type(client, callback_query):
    if not _admin_gate(callback_query):
        return
    await callback_query.answer()
    text, kb = await _render_global_breakdown("type")
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^admin_usage_by_tool$"))
async def admin_usage_by_tool(client, callback_query):
    if not _admin_gate(callback_query):
        return
    await callback_query.answer()
    text, kb = await _render_global_breakdown("tool")
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^admin_usage_purge_confirm$"))
async def admin_usage_purge_confirm(client, callback_query):
    if not _admin_gate(callback_query):
        return
    await callback_query.answer()
    text, kb = await _render_purge_confirm()
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)


@Client.on_callback_query(filters.regex(r"^admin_usage_purge_run$"))
async def admin_usage_purge_run(client, callback_query):
    if not _admin_gate(callback_query):
        return
    await callback_query.answer("Purging…")
    text, kb = await _run_purge()
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=kb)
