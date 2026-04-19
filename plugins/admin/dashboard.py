# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Usage Dashboard admin domain.

Handles the three read-only admin views reachable from the main panel's
"📊 Usage Dashboard" button:
- admin_usage_dashboard   → overview (today + all-time, live slots in public mode)
- admin_dashboard_top_N   → top users today, paginated
- admin_dashboard_daily   → last-7-days breakdown

These handlers were already self-contained with their own decorators in the
legacy monolith; this extraction is a pure move.
"""

import contextlib
import datetime

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from utils.telegram.logger import debug


SEPARATOR = "━━━━━━━━━━━━━━━━━━━━"


def _format_egress(mb: float) -> str:
    mb = float(mb or 0)
    if mb >= 1048576:
        return f"{mb / 1048576:.2f} TB"
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.2f} MB"


def _bar(filled: int, total: int = 10) -> str:
    filled = max(0, min(total, filled))
    return "■" * filled + "□" * (total - filled)


debug("✅ Loaded handler: admin_dashboard_overview_cb")

@Client.on_callback_query(
    filters.regex("^admin_usage_dashboard$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_overview_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    stats = await db.get_dashboard_stats()

    from plugins.process import _SEMAPHORES

    active_slots = 0
    for phase in ["download", "process", "upload"]:
        for user_sems in _SEMAPHORES.values():
            if phase in user_sems and user_sems[phase] is not None:
                active_slots += 3 - user_sems[phase]._value

    now = datetime.datetime.utcnow()
    cutoff_7d = now - datetime.timedelta(days=7)
    new_users_7d = await db.count_users({"joined_at": {"$gte": cutoff_7d}})

    cap_mb = 0.0
    if Config.PUBLIC_MODE:
        public_config = await db.get_public_config()
        cap_mb = float(public_config.get("daily_egress_mb", 0) or 0)

    today_str = now.strftime("%d %b %Y")
    refresh_str = now.strftime("%H:%M UTC")
    start_date_obj = datetime.datetime.strptime(stats.get("bot_start_date"), "%Y-%m-%d")
    start_date_str = start_date_obj.strftime("%d %b %Y")
    egress_today_mb = float(stats.get("egress_today_mb") or 0)

    today_block_lines = [
        f"**Today — {today_str}**",
        f"📁 Files processed: `{stats.get('files_today', 0)}`",
        f"📦 Egress: `{_format_egress(egress_today_mb)}`",
    ]
    if Config.PUBLIC_MODE:
        today_block_lines.append(f"⚡ Active slots: `{active_slots}`")
        if cap_mb > 0:
            pct = min(egress_today_mb / cap_mb * 100, 100)
            filled = int(round(pct / 10))
            today_block_lines.append(f"`{_bar(filled)}` {pct:.0f}% of daily cap")

    all_time_block_lines = [
        "**All-Time**",
        f"📁 Files processed: `{stats.get('total_files', 0)}`",
        f"📦 Egress: `{_format_egress(stats.get('total_egress_mb'))}`",
        f"👥 Total users: `{stats.get('total_users', 0)}`",
        f"🆕 New users (7d): `{new_users_7d}`",
        f"🗓 Bot running since: `{start_date_str}`",
    ]

    lines = [
        "**📊 Usage Dashboard**",
        SEPARATOR,
        "",
        "<blockquote>" + "\n".join(today_block_lines) + "</blockquote>",
        "",
        "<blockquote>" + "\n".join(all_time_block_lines) + "</blockquote>",
        "",
    ]

    if Config.PUBLIC_MODE:
        warn_block_lines = [
            f"⚠️ Quota hits today: `{stats.get('quota_hits_today', 0)}`",
            f"🚫 Blocked users: `{stats.get('blocked_users', 0)}`",
        ]
        lines.append("<blockquote>" + "\n".join(warn_block_lines) + "</blockquote>")
        lines.append("")

    lines.append(f"> Last refresh: {refresh_str} · tap 🔄 to update")

    text = "\n".join(lines)

    buttons = [
        [
            InlineKeyboardButton("🔝 Top Users", callback_data="admin_dashboard_top_0"),
            InlineKeyboardButton("📅 Daily Breakdown", callback_data="admin_dashboard_daily"),
        ],
        [
            InlineKeyboardButton("📈 Weekly Trend", callback_data="admin_dashboard_trend"),
            InlineKeyboardButton("🔍 Find User", callback_data="admin_user_search_start"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="admin_usage_dashboard"),
            InlineKeyboardButton("← Back", callback_data="admin_main"),
        ],
    ]

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )

_RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _short_display_name(user_obj, user_id: str) -> str:
    if user_obj is None:
        return f"user_{user_id}"[:14]
    if user_obj.username:
        return f"@{user_obj.username}"
    name = (user_obj.first_name or f"user_{user_id}").strip()
    return name[:14] if len(name) > 14 else name


async def _render_top_users(
    client: Client,
    callback_query: CallbackQuery,
    *,
    date_str: str | None,
    page: int,
    back_callback: str,
):
    limit = 10
    skip = page * limit
    users, total = await db.get_top_users_today(limit=limit, skip=skip, date=date_str)

    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    if date_str is None or date_str == today:
        title_date = "Today"
        page_callback_prefix = "admin_dashboard_top_"  # backward-compatible
    else:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        title_date = date_obj.strftime("%a %d %b")
        page_callback_prefix = f"admin_dashboard_day|{date_str}|"

    lines = [f"**🔝 Top Users — {title_date}**", SEPARATOR, ""]

    user_buttons: list[InlineKeyboardButton] = []
    if not users:
        lines.append("_No usage tracked for this day._")
    else:
        for i, user in enumerate(users):
            rank = skip + i + 1
            user_id = user["_id"].replace("user_", "")

            try:
                user_obj = await client.get_users(int(user_id))
            except Exception:
                user_obj = None

            display_name = _short_display_name(user_obj, user_id)
            medal = _RANK_MEDALS.get(rank, f"{rank:>2}.")

            usage = user.get("usage", {})
            files = usage.get("file_count", 0)
            mb = float(usage.get("egress_mb", 0.0) or 0)

            lines.append(
                f"{medal} `{display_name}` — {files} files · {_format_egress(mb)}"
            )
            user_buttons.append(
                InlineKeyboardButton(
                    f"👤 {display_name}", callback_data=f"view_user|{user_id}"
                )
            )

        lines.append("")
        lines.append("> Tap a user to open their profile.")

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    buttons: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(user_buttons), 2):
        buttons.append(user_buttons[i : i + 2])

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                "‹ Prev", callback_data=f"{page_callback_prefix}{page - 1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton("·", callback_data="noop"))
    nav_row.append(
        InlineKeyboardButton(
            f"Page {page + 1}/{total_pages}", callback_data="noop"
        )
    )
    if skip + limit < total:
        nav_row.append(
            InlineKeyboardButton(
                "Next ›", callback_data=f"{page_callback_prefix}{page + 1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton("·", callback_data="noop"))
    buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("← Back", callback_data=back_callback)])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
        )


debug("✅ Loaded handler: admin_dashboard_top_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_dashboard_top_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_top_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    page = int(callback_query.matches[0].group(1))
    await _render_top_users(
        client,
        callback_query,
        date_str=None,
        page=page,
        back_callback="admin_usage_dashboard",
    )


debug("✅ Loaded handler: admin_dashboard_day_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_dashboard_day\|(\d{4}-\d{2}-\d{2})(?:\|(\d+))?$")
    & filters.user(Config.CEO_ID)
)
async def admin_dashboard_day_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    matches = callback_query.matches[0]
    date_str = matches.group(1)
    page = int(matches.group(2) or 0)
    await _render_top_users(
        client,
        callback_query,
        date_str=date_str,
        page=page,
        back_callback="admin_dashboard_daily",
    )


debug("✅ Loaded handler: admin_dashboard_daily_cb")

@Client.on_callback_query(
    filters.regex("^admin_dashboard_daily$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_daily_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    daily_stats = await db.get_daily_stats(limit=7)

    lines = ["**📅 Daily Breakdown — Last 7 Days**", SEPARATOR, ""]

    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    day_buttons: list[InlineKeyboardButton] = []

    if not daily_stats:
        lines.append("_No history available yet._")
    else:
        ordered = sorted(daily_stats, key=lambda s: s["date"])
        peak_mb = max((float(s.get("egress_mb") or 0) for s in ordered), default=0.0)

        chart_lines = ["<blockquote>"]
        for stat in ordered:
            date_obj = datetime.datetime.strptime(stat["date"], "%Y-%m-%d")
            day_label = date_obj.strftime("%a %d %b")
            mb = float(stat.get("egress_mb") or 0)
            files = stat.get("file_count", 0)
            filled = int(round(mb / peak_mb * 10)) if peak_mb > 0 else 0
            today_marker = " ← today" if stat["date"] == today else ""
            peak_marker = " · peak" if peak_mb > 0 and mb == peak_mb else ""
            chart_lines.append(
                f"`{day_label}  {_bar(filled)}`  {files} files · {_format_egress(mb)}"
                f"{today_marker}{peak_marker}"
            )
        chart_lines[-1] = chart_lines[-1] + "</blockquote>"
        lines.extend(chart_lines)
        lines.append("")
        lines.append("> Bar = egress relative to the 7-day peak. Tap a day for top users.")

        for stat in ordered:
            date_obj = datetime.datetime.strptime(stat["date"], "%Y-%m-%d")
            short_label = date_obj.strftime("%a %d")
            day_buttons.append(
                InlineKeyboardButton(
                    f"📆 {short_label}",
                    callback_data=f"admin_dashboard_day|{stat['date']}",
                )
            )

    buttons: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(day_buttons), 4):
        buttons.append(day_buttons[i : i + 4])
    buttons.append(
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="admin_dashboard_daily"),
            InlineKeyboardButton("← Back", callback_data="admin_usage_dashboard"),
        ]
    )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
        )

debug("✅ Loaded handler: admin_dashboard_trend_cb")

@Client.on_callback_query(
    filters.regex("^admin_dashboard_trend$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_trend_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    daily_stats = await db.get_daily_stats(limit=7)

    lines = ["**📈 Weekly Trend**", SEPARATOR, ""]

    if not daily_stats:
        lines.append("No history available yet.")
    else:
        ordered = sorted(daily_stats, key=lambda s: s["date"])
        peak_mb = max((float(s.get("egress_mb") or 0) for s in ordered), default=0.0)
        total_mb = sum(float(s.get("egress_mb") or 0) for s in ordered)
        avg_mb = total_mb / len(ordered) if ordered else 0.0

        lines.append("Last 7 days · bar = egress relative to peak")
        lines.append("")

        bar_lines = []
        for stat in ordered:
            date_obj = datetime.datetime.strptime(stat["date"], "%Y-%m-%d")
            day_str = date_obj.strftime("%a %d %b")
            mb = float(stat.get("egress_mb") or 0)
            filled = int(round(mb / peak_mb * 10)) if peak_mb > 0 else 0
            peak_marker = "  ← peak" if peak_mb > 0 and mb == peak_mb else ""
            bar_lines.append(f"`{day_str}  {_bar(filled)}  {_format_egress(mb)}`{peak_marker}")

        lines.append("\n".join(bar_lines))
        lines.append("")
        lines.append(
            f"> 7-day total: {_format_egress(total_mb)} · daily avg: {_format_egress(avg_mb)}"
        )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back to Dashboard",
                            callback_data="admin_usage_dashboard",
                        )
                    ]
                ]
            ),
        )
