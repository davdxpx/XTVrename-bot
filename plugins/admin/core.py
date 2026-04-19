# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Shared core for the plugins/admin package.

Holds the single source of truth for admin session state and the tiny
helpers / menu builders that more than one admin submodule needs.

Rule: this module MUST NOT import from any `plugins.admin.<domain>` module
(to keep the package free of import cycles).
"""

import contextlib

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from utils.log import get_logger

logger = get_logger("plugins.admin.core")

# --- Shared state ------------------------------------------------------------
# Single source of truth for admin input state (prompted action + anchor msg).
# Every admin submodule imports THIS dict. Never reassign in another module —
# only mutate in place.
admin_sessions: dict = {}


# --- Access check ------------------------------------------------------------
def is_admin(user_id):
    return user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS


# --- Message edit helper -----------------------------------------------------
async def edit_or_reply(client, message, msg_id, text, reply_markup=None):
    # Try to edit the original bot prompt to reduce spam
    with contextlib.suppress(Exception):
        await message.delete()  # delete user's input

    if msg_id:
        try:
            return await client.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=text,
                reply_markup=reply_markup,
            )
        except Exception:
            pass

    # Fallback if editing fails
    return await message.reply_text(text, reply_markup=reply_markup)


# --- Shared menu builders ----------------------------------------------------
def get_admin_main_menu(pro_session, public_mode, myfiles_enabled=True):
    pro_btn_text = "🚀 Manage 𝕏TV Pro™" if pro_session else "🚀 Setup 𝕏TV Pro™"

    myfiles_txt = "📁 MyFiles Settings" if myfiles_enabled else "📁 Setup MyFiles™"
    keyboard = []

    keyboard.append(
        [InlineKeyboardButton("👤 User Management", callback_data="admin_users_menu")]
    )

    if public_mode:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🌐 Public Mode Settings", callback_data="admin_public_settings"
                ),
                InlineKeyboardButton(
                    "🔒 Settings", callback_data="admin_access_limits"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "💳 Manage Payments", callback_data="admin_payments_menu"
                ),
                InlineKeyboardButton(
                    "📢 Force-Sub Settings", callback_data="admin_force_sub_menu"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📺 Dumb Channels", callback_data="admin_dumb_channels"
                ),
                InlineKeyboardButton(
                    "⏱ Edit Dumb Channel Timeout", callback_data="admin_dumb_timeout"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📊 Usage Dashboard", callback_data="admin_usage_dashboard"
                ),
                InlineKeyboardButton(
                    "📢 Broadcast Message", callback_data="admin_broadcast"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    myfiles_txt, callback_data="admin_myfiles_settings"
                ),
            ]
        )
    else:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🖼 Manage Thumbnail", callback_data="admin_thumb_menu"
                ),
                InlineKeyboardButton(
                    "📋 Templates", callback_data="admin_templates_menu"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📺 Dumb Channels", callback_data="admin_dumb_channels"
                ),
                InlineKeyboardButton("⚙️ General Settings", callback_data="admin_general_settings_menu"),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "📊 Usage Dashboard", callback_data="admin_usage_dashboard"
                ),
                InlineKeyboardButton("👀 View Settings", callback_data="admin_view"),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔒 Access & Limits", callback_data="admin_access_limits"
                ),
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    myfiles_txt, callback_data="admin_myfiles_settings"
                ),
            ]
        )

    keyboard.append(
        [InlineKeyboardButton(pro_btn_text, callback_data="pro_setup_menu")]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                "🩺 System Health & Statuses",
                callback_data="admin_system_health",
            )
        ]
    )

    return InlineKeyboardMarkup(keyboard)


async def get_admin_access_limits_menu():
    buttons = []

    if Config.PUBLIC_MODE:
        config = await db.get_public_config()
        prem_enabled = config.get("premium_system_enabled", False)
        deluxe_enabled = config.get("premium_deluxe_enabled", False)
        trial_enabled = config.get("premium_trial_enabled", False)
        myfiles_enabled = await db.get_setting("myfiles_enabled", default=False)

        def _status(s): return "✅ ON" if s else "❌ OFF"

        buttons.append([InlineKeyboardButton("━━━ 🔧 System Toggles ━━━", callback_data="noop")])
        buttons.append([
            InlineKeyboardButton(f"💎 Premium: {_status(prem_enabled)}", callback_data="admin_quick_toggle_premium")
        ])
        if prem_enabled:
            row = []
            row.append(InlineKeyboardButton(f"👑 Deluxe: {_status(deluxe_enabled)}", callback_data="admin_quick_toggle_deluxe"))
            row.append(InlineKeyboardButton(f"⏳ Trial: {_status(trial_enabled)}", callback_data="admin_quick_toggle_trial"))
            buttons.append(row)
        buttons.append([
            InlineKeyboardButton(f"📁 MyFiles: {_status(myfiles_enabled)}", callback_data="admin_quick_toggle_myfiles")
        ])
        buttons.append([InlineKeyboardButton("━━━ ⚙️ Configuration ━━━", callback_data="noop")])
        buttons.append([InlineKeyboardButton("🛠️ Feature Toggles", callback_data="admin_feature_toggles")])
        buttons.append([InlineKeyboardButton("📋 Per-Plan Settings", callback_data="admin_per_plan_limits")])
        buttons.append([InlineKeyboardButton("🌍 Global Daily Egress Limit", callback_data="admin_global_daily_egress")])
    else:
        buttons.append([InlineKeyboardButton("🛠️ Feature Toggles", callback_data="admin_feature_toggles")])
        buttons.append([InlineKeyboardButton("🌍 Set Global Daily Egress Limit", callback_data="admin_global_daily_egress")])

    buttons.append([InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")])
    return InlineKeyboardMarkup(buttons)
