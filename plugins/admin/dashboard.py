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

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import db
from utils.logger import debug

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

    def format_egress(mb):
        if mb >= 1048576:
            return f"{mb / 1048576:.2f} TB"
        elif mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        else:
            return f"{mb:.2f} MB"

    import datetime

    current_time_str = datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    start_date_obj = datetime.datetime.strptime(stats.get("bot_start_date"), "%Y-%m-%d")
    start_date_str = start_date_obj.strftime("%d %b %Y")

    text = (
        f"📊 **𝕏TV Usage Dashboard**\n"
        f"Updated: {current_time_str}\n"
        f"═════════════════════════\n"
        f"👥 Total Users: `{stats.get('total_users')}`\n"
        f"📁 Files Processed Today: `{stats.get('files_today')}`\n"
        f"📦 Egress Today: `{format_egress(stats.get('egress_today_mb'))}`\n"
    )

    if Config.PUBLIC_MODE:
        text += f"⚡ Active Right Now: `{active_slots}`\n"

    text += (
        f"─────────────────────────\n"
        f"📈 **All-Time**\n"
        f"─────────────────────────\n"
        f"📁 Total Files: `{stats.get('total_files')}`\n"
        f"📦 Total Egress: `{format_egress(stats.get('total_egress_mb'))}`\n"
        f"🗓️ Bot Running Since: `{start_date_str}`\n"
    )

    if Config.PUBLIC_MODE:
        text += (
            f"─────────────────────────\n"
            f"⚠️ Quota Hits Today: `{stats.get('quota_hits_today')}`\n"
            f"🚫 Blocked Users: `{stats.get('blocked_users')}`\n"
        )

    text += "─────────────────────────"

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔝 Top Users", callback_data="admin_dashboard_top_0"
                        ),
                        InlineKeyboardButton(
                            "📅 Daily Breakdown", callback_data="admin_dashboard_daily"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🔍 User Lookup", callback_data="prompt_user_lookup"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "← Back to Admin Panel", callback_data="admin_main"
                        )
                    ],
                ]
            ),
        )

debug("✅ Loaded handler: admin_dashboard_top_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_dashboard_top_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_top_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    page = int(callback_query.matches[0].group(1))
    limit = 10
    skip = page * limit

    users, total = await db.get_top_users_today(limit=limit, skip=skip)

    import datetime

    current_date = datetime.datetime.utcnow().strftime("%d %b")

    text = f"🏆 **Top Users — Today ({current_date})**\n\n"

    if not users:
        text += "No usage tracked today."
    else:
        for i, user in enumerate(users):
            rank = skip + i + 1
            user_id = user["_id"].replace("user_", "")

            try:
                user_obj = await client.get_users(int(user_id))
                display_name = (
                    f"@{user_obj.username}"
                    if user_obj.username
                    else f"{user_obj.first_name}"
                )
            except Exception:
                display_name = f"User {user_id}"

            usage = user.get("usage", {})
            files = usage.get("file_count", 0)
            mb = usage.get("egress_mb", 0.0)

            mb_str = f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.2f} MB"

            text += f"**#{rank}** {display_name} — {files} files · {mb_str}\n"

    buttons = []
    nav_row = []

    total_pages = (total + limit - 1) // limit if total > 0 else 1

    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                "← Prev", callback_data=f"admin_dashboard_top_{page-1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton("← Prev", callback_data="noop"))

    nav_row.append(
        InlineKeyboardButton(f"Page {page+1} / {total_pages}", callback_data="noop")
    )

    if skip + limit < total:
        nav_row.append(
            InlineKeyboardButton(
                "Next →", callback_data=f"admin_dashboard_top_{page+1}"
            )
        )
    else:
        nav_row.append(InlineKeyboardButton("Next →", callback_data="noop"))

    buttons.append(nav_row)

    buttons.append(
        [InlineKeyboardButton("← Back to Dashboard", callback_data="admin_usage_dashboard")]
    )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(buttons)
        )

debug("✅ Loaded handler: admin_dashboard_daily_cb")

@Client.on_callback_query(
    filters.regex("^admin_dashboard_daily$") & filters.user(Config.CEO_ID)
)
async def admin_dashboard_daily_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    daily_stats = await db.get_daily_stats(limit=7)

    text = "📅 **Last 7 Days Breakdown**\n\n"
    text += "`Date          Files    Egress`\n"
    text += "`──────────────────────────────`\n"

    if not daily_stats:
        text += "No history available."
    else:
        import datetime

        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        for stat in daily_stats:
            date_obj = datetime.datetime.strptime(stat["date"], "%Y-%m-%d")
            date_str = date_obj.strftime("%d %b %Y")

            files = stat.get("file_count", 0)
            mb = stat.get("egress_mb", 0.0)

            if mb >= 1048576:
                egress_str = f"{mb / 1048576:.2f} TB"
            elif mb >= 1024:
                egress_str = f"{mb / 1024:.2f} GB"
            else:
                egress_str = f"{mb:.2f} MB"

            is_today = " ← today" if stat["date"] == current_utc_date else ""

            text += f"`{date_str:<13} {files:<7} {egress_str:>7}`{is_today}\n"

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back to Dashboard", callback_data="admin_usage_dashboard"
                        )
                    ]
                ]
            ),
        )
