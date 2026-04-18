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

Text-input flows (`awaiting_public_*`) are registered with the shared
``text_dispatcher`` and routed here at runtime.
"""

import contextlib

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import db
from plugins.admin.core import admin_sessions, edit_or_reply, is_admin


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
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "🌐 **Public Mode Settings**\n\nSelect a setting to edit:",
                reply_markup=get_admin_public_settings_menu(),
            )
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
        with contextlib.suppress(MessageNotModified):
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
        return

    # --- Bot name / Community / Support display ---
    if data == "admin_public_bot_name":
        await callback_query.answer()
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        current_val = config.get("bot_name", "Not set")
        with contextlib.suppress(MessageNotModified):
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
        return

    if data == "admin_public_community_name":
        await callback_query.answer()
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        current_val = config.get("community_name", "Not set")
        with contextlib.suppress(MessageNotModified):
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
        return

    if data == "admin_public_support_contact":
        await callback_query.answer()
        if not Config.PUBLIC_MODE:
            return
        config = await db.get_public_config()
        current_val = config.get("support_contact", "Not set")
        with contextlib.suppress(MessageNotModified):
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
        with contextlib.suppress(MessageNotModified):
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
        return


# ---------------------------------------------------------------------------
# Text-input state handler (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def handle_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_public_* states."""
    from pyrogram import ContinuePropagation

    user_id = message.from_user.id
    field = state.replace("awaiting_public_", "")

    val = message.text.strip() if message.text else ""
    if not val:
        raise ContinuePropagation

    if field == "bot_name":
        await db.update_public_config("bot_name", val)
        await edit_or_reply(client, message, msg_id, f"✅ Bot Name updated to `{val}`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Public Settings", callback_data="admin_public_settings")]]
            ),
        )
    elif field == "community_name":
        await db.update_public_config("community_name", val)
        await edit_or_reply(client, message, msg_id, f"✅ Community Name updated to `{val}`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Public Settings", callback_data="admin_public_settings")]]
            ),
        )
    elif field == "support_contact":
        await db.update_public_config("support_contact", val)
        await edit_or_reply(client, message, msg_id, f"✅ Support Contact updated to `{val}`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Public Settings", callback_data="admin_public_settings")]]
            ),
        )
    elif field == "force_sub":
        if val.lower() == "/cancel":
            admin_sessions.pop(user_id, None)
            await edit_or_reply(client, message, msg_id, "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Force-Sub Settings", callback_data="admin_force_sub_menu")]]
                )
            )
        else:
            await edit_or_reply(client, message, msg_id,
                "⏳ **Still Waiting...**\n\nPlease add me as an Admin to the channel, or type `/cancel` to abort.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                )
            )
        return
    elif field == "rate_limit":
        if not val.isdigit():
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_public_settings")]]
                ),
            )
            return
        await db.update_public_config("rate_limit_delay", int(val))
        await edit_or_reply(client, message, msg_id, f"✅ Rate limit updated to `{val}` seconds.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Public Settings", callback_data="admin_public_settings")]]
            ),
        )
    elif field == "daily_egress":
        val_lower = val.lower().strip()
        val_num = 0

        if "gb" in val_lower:
            try:
                gb_val = float(val_lower.replace("gb", "").strip())
                val_num = int(gb_val * 1024)
            except ValueError:
                await edit_or_reply(client, message, msg_id,
                    "❌ Invalid GB format. Please use something like `2 GB`.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_plan_free")]])
                )
                return
        else:
            try:
                val_num = int(float(val_lower.replace("mb", "").strip()))
            except ValueError:
                await edit_or_reply(client, message, msg_id, "❌ Invalid number format. Try again.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_plan_free")]])
                )
                return

        await db.update_public_config("daily_egress_mb", val_num)
        await edit_or_reply(client, message, msg_id,
            f"✅ **Success!**\n\nThe Daily Egress Limit for the **Free Plan** has been updated to **{val_num} MB**.\n\nChanges have been saved and applied globally.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_edit_plan_free")]]
            ),
        )
    elif field == "daily_files":
        if not val.isdigit():
            await edit_or_reply(client, message, msg_id, "❌ Invalid number. Try again.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_edit_plan_free")]]
                ),
            )
            return
        await db.update_public_config("daily_file_count", int(val))
        await edit_or_reply(client, message, msg_id,
            f"✅ **Success!**\n\nThe Daily File Limit for the **Free Plan** has been updated to **{val} files**.\n\nChanges have been saved and applied globally.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Plan Settings", callback_data="admin_edit_plan_free")]]
            ),
        )

    admin_sessions.pop(user_id, None)


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_public_", handle_text)
