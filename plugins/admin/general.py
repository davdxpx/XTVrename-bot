# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
General Settings admin domain.

Covers the General Settings submenu and its sub-flows:
- admin_general_settings_menu → the submenu with Channel / Language / Workflow
- admin_view                  → summary view of current settings
- admin_general_workflow / set_admin_workflow_* → workflow mode toggle
- admin_general_channel / prompt_admin_channel  → channel variable edit
- admin_general_language / prompt_admin_language / admin_set_lang_* → language selection
- admin_cancel → cancel / dismiss admin message

Text-input flows (awaiting_admin_channel) are registered with the shared
``text_dispatcher`` and handled here via ``handle_text``.
"""

import contextlib

from pyrogram import Client, ContinuePropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from plugins.admin.core import admin_sessions, is_admin


async def _render_workflow(callback_query: CallbackQuery):
    """Build and display the workflow mode settings."""
    current_mode = await db.get_workflow_mode(None)
    mode_str = "🧠 Smart Media Mode" if current_mode == "smart_media_mode" else "⚡ Quick Rename Mode"
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            f"⚙️ **Global Workflow Mode Settings**\n\n"
            f"Current Mode: `{mode_str}`\n\n"
            "**🧠 Smart Media Mode:** Auto-detects Series/Movies and fetches TMDb metadata.\n"
            "**⚡ Quick Rename Mode:** Bypasses auto-detection and goes straight to general rename (great for personal/general files).\n\n"
            "Select the default mode for all users:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Smart Media Mode" if current_mode == "smart_media_mode" else "🧠 Smart Media Mode",
                            callback_data="set_admin_workflow_smart"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "✅ Quick Rename Mode" if current_mode == "quick_rename_mode" else "⚡ Quick Rename Mode",
                            callback_data="set_admin_workflow_quick"
                        )
                    ],
                    [InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")],
                ]
            ),
        )


async def _render_language(callback_query: CallbackQuery):
    """Build and display the language settings."""
    current_language = await db.get_preferred_language(None)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            f"🌍 **Global Preferred Language Settings**\n\n"
            f"Current Preferred Language: `{current_language}`\n\n"
            "This language code is used when fetching data from TMDb (e.g., `en-US`, `de-DE`, `es-ES`).\n\n"
            "Click below to change it.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✏️ Change", callback_data="prompt_admin_language"
                        )
                    ],
                    [InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")],
                ]
            ),
        )


@Client.on_callback_query(
    filters.regex(
        r"^(admin_general_settings_menu$|admin_general_"
        r"|admin_view$|admin_cancel$"
        r"|set_admin_workflow_|admin_set_lang_"
        r"|prompt_admin_(?:channel|language)$)"
    )
)
async def general_settings_cb(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation
    await callback_query.answer()
    data = callback_query.data

    # --- General settings menu ---
    if data == "admin_general_settings_menu":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "⚙️ **Global General Settings**\n\n"
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
        return

    # --- Workflow mode ---
    if data == "admin_general_workflow":
        await _render_workflow(callback_query)
        return

    if data.startswith("set_admin_workflow_"):
        new_mode = "smart_media_mode" if data.endswith("smart") else "quick_rename_mode"
        await db.update_workflow_mode(new_mode, None)
        await callback_query.answer("Global Workflow Mode updated!", show_alert=True)
        await _render_workflow(callback_query)
        return

    # --- Channel username ---
    if data == "admin_general_channel":
        current_channel = await db.get_channel(None)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📢 **Global Channel Username Settings**\n\n"
                f"Current Channel Variable: `{current_channel}`\n\n"
                "Click below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_admin_channel"
                            )
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")],
                    ]
                ),
            )
        return

    if data == "prompt_admin_channel":
        admin_sessions[user_id] = {"state": "awaiting_admin_channel", "msg_id": callback_query.message.id}
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "⚙️ **Send the new Global Channel name variable to use in templates (e.g. `@MyChannel`):**",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_general_channel")]]
                ),
            )
        return

    # --- Preferred language ---
    if data == "admin_general_language":
        await _render_language(callback_query)
        return

    if data == "prompt_admin_language":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "🌍 **Select global preferred language for TMDb Metadata:**\n\n"
                "__(Default is English)__",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("🇺🇸 English", callback_data="admin_set_lang_en-US"),
                            InlineKeyboardButton("🇩🇪 German", callback_data="admin_set_lang_de-DE"),
                        ],
                        [
                            InlineKeyboardButton("🇪🇸 Spanish", callback_data="admin_set_lang_es-ES"),
                            InlineKeyboardButton("🇫🇷 French", callback_data="admin_set_lang_fr-FR"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇳 Hindi", callback_data="admin_set_lang_hi-IN"),
                            InlineKeyboardButton("🇮🇳 Tamil", callback_data="admin_set_lang_ta-IN"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇳 Telugu", callback_data="admin_set_lang_te-IN"),
                            InlineKeyboardButton("🇮🇳 Malayalam", callback_data="admin_set_lang_ml-IN"),
                        ],
                        [
                            InlineKeyboardButton("🇯🇵 Japanese", callback_data="admin_set_lang_ja-JP"),
                            InlineKeyboardButton("🇰🇷 Korean", callback_data="admin_set_lang_ko-KR"),
                        ],
                        [
                            InlineKeyboardButton("🇨🇳 Chinese", callback_data="admin_set_lang_zh-CN"),
                            InlineKeyboardButton("🇷🇺 Russian", callback_data="admin_set_lang_ru-RU"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇹 Italian", callback_data="admin_set_lang_it-IT"),
                            InlineKeyboardButton("🇧🇷 Portuguese", callback_data="admin_set_lang_pt-BR"),
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")],
                    ]
                ),
            )
        return

    if data.startswith("admin_set_lang_"):
        new_language = data.replace("admin_set_lang_", "")
        await db.update_preferred_language(new_language, None)
        await _render_language(callback_query)
        return

    # --- Cancel ---
    if data == "admin_cancel":
        admin_sessions.pop(user_id, None)
        await callback_query.message.delete()
        return

    # --- View settings ---
    if data == "admin_view":
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

        text = "👀 **Current Settings**\n\n"
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
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")]]
                ),
            )
        return


# ---------------------------------------------------------------------------
# Text-input state handler (registered with text_dispatcher)
# ---------------------------------------------------------------------------
async def handle_text(client, message, state, state_obj, msg_id):
    """Handle awaiting_admin_channel state."""
    from plugins.admin.core import edit_or_reply

    user_id = message.from_user.id
    new_channel = message.text
    await db.update_channel(new_channel, None)

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back to General Settings", callback_data="admin_general_settings_menu")]]
    )
    await edit_or_reply(client, message, msg_id,
        f"✅ Global channel variable updated to:\n`{new_channel}`",
        reply_markup=reply_markup,
    )
    admin_sessions.pop(user_id, None)


from plugins.admin.text_dispatcher import register as _register

_register("awaiting_admin_channel", handle_text)
