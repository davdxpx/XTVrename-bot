# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
User Moderation & Lookup admin domain.

Handles everything reachable from "🔍 User Lookup" on the dashboard as
well as the `/lookup <id|username>` shortcut:
- /lookup <digits>                        → inline lookup by numeric ID
- prompt_user_lookup                      → prompt for ID/username, set state
- awaiting_user_lookup (utils.state)      → resolve & show profile
- admin_block_<id>                        → block user, refresh profile
- admin_unblock_<id>                      → unblock user, refresh profile
- admin_reset_quota_<id>                  → reset today's quota, refresh profile

All handlers were already standalone-decorated in the legacy monolith.
This is a pure move, including the shared `show_user_lookup` helper.

Note: the text dispatcher here uses `utils.state` (own dict), not the
`admin_sessions` dict used by the shared ``text_dispatcher``.
"""

import contextlib

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from db import db
from utils.logger import debug


# --- Shared helper -----------------------------------------------------------
async def show_user_lookup(client: Client, message: Message, user_id: int):
    usage = await db.get_user_usage(user_id)
    is_blocked = await db.is_user_blocked(user_id)

    import datetime

    current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    current_date_display = datetime.datetime.utcnow().strftime("%d %b")

    files_today = 0
    egress_today_mb = 0.0
    quota_hits_today = 0

    if usage.get("date") == current_utc_date:
        files_today = usage.get("file_count", 0)
        egress_today_mb = usage.get("egress_mb", 0.0)
        quota_hits_today = usage.get("quota_hits", 0)

    files_alltime = usage.get("file_count_alltime", 0)
    egress_alltime_mb = usage.get("egress_mb_alltime", 0.0)

    def format_egress(mb):
        if mb >= 1048576:
            return f"{mb / 1048576:.2f} TB"
        elif mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        else:
            return f"{mb:.2f} MB"

    try:
        user_obj = await client.get_users(user_id)
        name = user_obj.first_name
        username = f"@{user_obj.username}" if user_obj.username else "N/A"
    except Exception:
        name = "Unknown User"
        username = "N/A"

    user_settings = await db.get_settings(user_id)
    joined_date = "Unknown"

    has_thumb = "No"
    current_template = "Default"

    if user_settings:
        if user_settings.get("thumbnail_file_id") or user_settings.get(
            "thumbnail_binary"
        ):
            has_thumb = "Yes"

        templates = user_settings.get("templates", {})
        if templates and templates.get("caption") != "{random}":
            current_template = "Custom"

        _id = user_settings.get("_id")
        if _id:
            try:

                import bson

                if isinstance(_id, bson.ObjectId):
                    joined_date = _id.generation_time.strftime("%d %b %Y")
                else:
                    joined_date = usage.get("date", "Unknown")
            except Exception:
                joined_date = usage.get("date", "Unknown")

    text = (
        f"👤 **User Lookup**\n\n"
        f"**ID:** `{user_id}`\n"
        f"**Name:** {name}\n"
        f"**Username:** {username}\n"
        f"**Joined:** {joined_date}\n"
        f"**Template:** {current_template}\n"
        f"**Custom Thumb:** {has_thumb}\n"
        f"──────────────────────────\n"
        f"📊 **Today ({current_date_display})**\n"
        f"Files: `{files_today}`\n"
        f"Egress: `{format_egress(egress_today_mb)}`\n"
        f"Quota hits: `{quota_hits_today}`\n\n"
        f"📈 **All-Time**\n"
        f"Files: `{files_alltime}`\n"
        f"Egress: `{format_egress(egress_alltime_mb)}`\n"
        f"──────────────────────────\n"
    )

    if is_blocked:
        text += "🔴 **Status: BLOCKED**\n"

    buttons = []

    if is_blocked:
        buttons.append(
            [
                InlineKeyboardButton(
                    "✅ Unblock User", callback_data=f"admin_unblock_{user_id}"
                )
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    "🚫 Block User", callback_data=f"admin_block_{user_id}"
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "🗑️ Reset Today's Quota", callback_data=f"admin_reset_quota_{user_id}"
            )
        ]
    )
    buttons.append(
        [InlineKeyboardButton("← Back to Dashboard", callback_data="admin_usage_dashboard")]
    )

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# --- /lookup command ---------------------------------------------------------
@Client.on_message(filters.regex(r"^/lookup (\d+)$") & filters.user(Config.CEO_ID))
async def admin_lookup_user(client: Client, message: Message):
    user_id = int(message.matches[0].group(1))
    await show_user_lookup(client, message, user_id)


# --- Callback handlers -------------------------------------------------------
debug("✅ Loaded handler: admin_block_user_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_block_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_block_user_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("User Blocked", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.block_user(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_unblock_user_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_unblock_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_unblock_user_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("User Unblocked", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.unblock_user(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_reset_quota_cb")

@Client.on_callback_query(
    filters.regex(r"^admin_reset_quota_(\d+)$") & filters.user(Config.CEO_ID)
)
async def admin_reset_quota_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer("Quota Reset", show_alert=True)
    user_id = int(callback_query.matches[0].group(1))
    await db.reset_user_quota(user_id)
    await show_user_lookup(client, callback_query.message, user_id)
    await callback_query.message.delete()

debug("✅ Loaded handler: admin_prompt_lookup_cb")

@Client.on_callback_query(
    filters.regex("^prompt_user_lookup$") & filters.user(Config.CEO_ID)
)
async def admin_prompt_lookup_cb(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "🔍 **User Lookup**\n\n"
            "Please send the user's Telegram ID (e.g., 123456789) to view their profile.",
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
    from utils.state import set_state

    set_state(callback_query.from_user.id, "awaiting_user_lookup")


# --- Text state handler ------------------------------------------------------
@Client.on_message(
    filters.text & filters.private & filters.user(Config.CEO_ID), group=1
)
async def admin_handle_user_lookup_text(client: Client, message: Message):
    from utils.state import clear_session, get_state

    state = get_state(message.from_user.id)

    if not state or state != "awaiting_user_lookup":
        raise ContinuePropagation

    if state == "awaiting_user_lookup":
        val = message.text.strip()

        if val.isdigit():
            user_id = int(val)
        else:

            try:
                user = await client.get_users(val)
                user_id = user.id
            except Exception:
                await message.reply_text("❌ Could not find a user with that ID or username. Please make sure the ID is correct.",
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
                clear_session(message.from_user.id)
                return

        await show_user_lookup(client, message, user_id)
        clear_session(message.from_user.id)
        raise ContinuePropagation
