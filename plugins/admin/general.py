# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
General Settings admin domain (routing only).

Two tiny read-only/menu callbacks used from the non-public admin panel:
- admin_general_settings_menu → the submenu with Channel / Language / Workflow
- admin_view                  → summary view of current settings

The deeper sub-flows reachable from the General Settings submenu
(admin_general_channel, admin_general_language, admin_general_workflow
and their text states) stay in _legacy.py and their own decorated plugins
for now.
"""

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from database import db
from plugins.admin.core import is_admin


@Client.on_callback_query(filters.regex(r"^admin_general_settings_menu$"))
async def admin_general_settings_menu_cb(client, callback_query: CallbackQuery):
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        raise ContinuePropagation

    try:
        await callback_query.message.edit_text(
            f"⚙️ **Global General Settings**\n\n"
            "Select a setting to configure:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📢 Channel Username", callback_data="admin_general_channel"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🌍 Preferred Language", callback_data="admin_general_language"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⚙️ Workflow Mode", callback_data="admin_general_workflow"
                        )
                    ],
                    [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")],
                ]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^admin_view$"))
async def admin_view_cb(client, callback_query: CallbackQuery):
    await callback_query.answer()
    if not is_admin(callback_query.from_user.id):
        raise ContinuePropagation

    settings = await db.get_settings()
    templates = settings.get("templates", {}) if settings else {}
    thumb_mode = settings.get("thumbnail_mode", "none") if settings else "none"
    has_thumb = (
        "✅ Yes" if settings and settings.get("thumbnail_binary") else "❌ No"
    )

    mode_str = "Deactivated (None)"
    if thumb_mode == "auto":
        mode_str = "Auto-detect (Preview)"
    elif thumb_mode == "custom":
        mode_str = "Custom Thumbnail"

    text = f"👀 **Current Settings**\n\n"
    text += f"**Thumbnail Mode:** `{mode_str}`\n"
    text += f"**Custom Thumbnail Set:** {has_thumb}\n\n"
    text += "**Metadata Templates:**\n"
    if templates:
        for k, v in templates.items():
            if k == "caption":
                text += f"- **Caption:** `{v}`\n"
            else:
                text += f"- **{k.capitalize()}:** `{v}`\n"
    else:
        text += "No templates set.\n"
    text += "\n**Filename Templates:**\n"
    fn_templates = settings.get("filename_templates", {}) if settings else {}
    if fn_templates:
        for k, v in fn_templates.items():
            text += f"- **{k.capitalize()}:** `{v}`\n"
    else:
        text += "No filename templates set.\n"
    text += f"\n**Channel Variable:** `{settings.get('channel', Config.DEFAULT_CHANNEL) if settings else Config.DEFAULT_CHANNEL}`\n"
    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back to Admin Panel", callback_data="admin_main"
                        )
                    ]
                ]
            ),
        )
    except MessageNotModified:
        pass
