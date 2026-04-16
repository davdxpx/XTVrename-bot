# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Public Settings admin domain.

Houses the Public Mode Settings submenu (bot name, community name,
support contact, view config) and the prompt setup for those text-input
fields.

The menu builder `get_admin_public_settings_menu` also lives here.

Daily egress / file limits (`admin_daily_*`, `set_daily_egress_*`,
`prompt_daily_*`) remain in `_legacy.py` for now because they are
tightly coupled to the per-plan editing flow.

Text-input flows (`awaiting_public_*`) still route through
`_legacy.handle_admin_text`.
"""

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import db
from plugins.admin.core import admin_sessions, is_admin


def get_admin_public_settings_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🤖 Edit Bot Name", callback_data="admin_public_bot_name"
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 Edit Community Name",
                    callback_data="admin_public_community_name",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔗 Edit Support Contact",
                    callback_data="admin_public_support_contact",
                )
            ],
            [
                InlineKeyboardButton(
                    "👀 View Public Config", callback_data="admin_public_view"
                )
            ],
            [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")],
        ]
    )


@Client.on_callback_query(
    filters.regex(
        r"^(admin_public_(?:settings|view|bot_name|community_name|support_contact)$"
        r"|prompt_public_(?:bot_name|community_name|support_contact)$)"
    )
)
async def public_settings_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    data = callback_query.data

    # --- Public Settings menu ---
    if data == "admin_public_settings":
        await callback_query.answer()
        try:
            await callback_query.message.edit_text(
                "🌐 **Public Mode Settings**\n\nSelect a setting to edit:",
                reply_markup=get_admin_public_settings_menu(),
            )
        except MessageNotModified:
            pass
        return

    # --- View config ---
    if data == "admin_public_view":
        await callback_query.answer()
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        text = "👀 **Public Mode Config**\n\n"
        text += f"**Bot Name:** {config.get('bot_name', 'Not set')}\n"
        text += f"**Community Name:** {config.get('community_name', 'Not set')}\n"
        text += f"**Support Contact:** {config.get('support_contact', 'Not set')}\n"
        text += f"**Force-Sub Channel:** {config.get('force_sub_channel', 'Not set')}\n"
        text += f"**Daily Egress Limit:** {config.get('daily_egress_mb', 0)} MB\n"
        text += f"**Daily File Limit:** {config.get('daily_file_count', 0)} files\n"
        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "← Back to Public Settings",
                                callback_data="admin_public_settings",
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Bot name / Community / Support display ---
    if data == "admin_public_bot_name":
        await callback_query.answer()
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        current_val = config.get("bot_name", "Not set")
        try:
            await callback_query.message.edit_text(
                f"🤖 **Edit Bot Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_public_bot_name"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Public Settings",
                                callback_data="admin_public_settings",
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_public_community_name":
        await callback_query.answer()
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        current_val = config.get("community_name", "Not set")
        try:
            await callback_query.message.edit_text(
                f"👥 **Edit Community Name**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change",
                                callback_data="prompt_public_community_name",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Public Settings",
                                callback_data="admin_public_settings",
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    if data == "admin_public_support_contact":
        await callback_query.answer()
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        current_val = config.get("support_contact", "Not set")
        try:
            await callback_query.message.edit_text(
                f"🔗 **Edit Support Contact**\n\nCurrent: `{current_val}`\n\nClick below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change",
                                callback_data="prompt_public_support_contact",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Public Settings",
                                callback_data="admin_public_settings",
                            )
                        ],
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return

    # --- Prompt text-input setup ---
    if data.startswith("prompt_public_"):
        if not Config.PUBLIC_MODE:
            return
        field = data.replace("prompt_public_", "")
        admin_sessions[user_id] = {
            "state": f"awaiting_public_{field}",
            "msg_id": callback_query.message.id,
        }
        if field == "bot_name":
            text = "🤖 **Send the new bot name:**"
        elif field == "community_name":
            text = "👥 **Send the new community name:**"
        elif field == "support_contact":
            text = "🔗 **Send the new support contact (e.g., @username or link):**"
        else:
            text = "Send the new value:"
        cancel_btn = "admin_public_settings"
        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data=cancel_btn
                            )
                        ]
                    ]
                ),
            )
        except MessageNotModified:
            pass
        return
