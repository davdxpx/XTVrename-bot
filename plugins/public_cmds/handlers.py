# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""plugins.public_cmds.handlers — /info, /settings, user_settings_callback.

Mode: BOTH (public + non-public). ``/info`` is PUBLIC-ONLY and gates
itself via ``is_public_mode()``. ``/settings`` and the callback router
serve both modes; mode-specific sub-menus are gated inside each branch
(Mirror-Leech credentials for example only appear in non-public mode).
"""

# --- Imports ---
import datetime
import io
import os
import platform
import time

import psutil
import pyrogram
from pyrogram import Client, ContinuePropagation, StopPropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_START_TIME, Config
from db import db
from plugins.ui.placeholder_reference import (
    FIELD_TO_SCOPE,
    reference_and_preview_buttons,
)
from utils.telegram.log import get_logger
from utils.template import (
    SCOPE_TOP_HINTS,
    allowed_fields_for,
    validate_template,
)

logger = get_logger("plugins.public_cmds.handlers")

user_sessions = {}

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"

_USER_METADATA_KEYS = {
    "title", "author", "artist", "video", "audio", "subtitle",
    "comment", "copyright", "description", "genre", "date",
    "album", "show", "network",
}


def _vars_line(scope: str) -> str:
    hints = SCOPE_TOP_HINTS.get(scope, ())
    return ", ".join(f"`{{{h}}}`" for h in hints)


def _ref_and_preview(field: str):
    return reference_and_preview_buttons(field, origin="u")


async def _user_legacy_sys_banner_line(user_id: int) -> str:
    templates = await db.get_all_templates(user_id)
    legacy = templates.get("system_filename")
    has_new = bool(templates.get("system_filename_movies") or templates.get("system_filename_series"))
    if legacy and not has_new:
        return (
            "ℹ️ **System Filename was split into Movies/Series.**\n"
            "Your existing template still applies to both until you override either.\n\n"
        )
    return ""

# === Helper Functions ===
def get_user_main_menu():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🖼 Thumbnail", callback_data="user_thumb_menu"),
                InlineKeyboardButton("📋 Templates", callback_data="user_templates_menu"),
            ],
            [
                InlineKeyboardButton("📺 Channels", callback_data="dumb_user_menu"),
                InlineKeyboardButton("⚙️ General", callback_data="user_general_settings_menu"),
            ],
            [InlineKeyboardButton("☁️ Mirror-Leech", callback_data="ml_cfg")],
            [
                InlineKeyboardButton("👀 View Current Config", callback_data="user_view"),
            ],
            [InlineKeyboardButton("❌ Close", callback_data="user_cancel")],
        ]
    )

def get_user_templates_menu():
    # System filename editing folded into the Filename Templates submenu
    # as its own Movies/Series rows, so it no longer needs a top-level
    # entry. Users who previously tapped the old entry now discover it
    # inside Filename Templates alongside the other rename templates.
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📝 Edit Filename Templates",
                    callback_data="user_filename_templates",
                )
            ],
            [
                InlineKeyboardButton(
                    "📝 Edit Caption Template", callback_data="user_caption"
                )
            ],
            [
                InlineKeyboardButton(
                    "📝 Edit Metadata Templates", callback_data="user_templates"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔤 Preferred Separator", callback_data="user_pref_separator"
                )
            ],
            [InlineKeyboardButton("← Back to Settings", callback_data="user_main")],
        ]
    )

def is_public_mode():
    return Config.PUBLIC_MODE

@Client.on_message(filters.command("info") & filters.private)

# --- Handlers ---
async def info_command(client, message):
    if not is_public_mode():
        return

    config = await db.get_public_config()
    bot_name = config.get("bot_name", "𝕏TV MediaStudio™")
    community_name = config.get("community_name", "Our Community")
    support_contact = config.get("support_contact", "@davdxpx")

    force_sub_channels = config.get("force_sub_channels", [])
    legacy_channel = config.get("force_sub_channel")
    channel_link = None

    if force_sub_channels:
        channel_link = force_sub_channels[0].get("link")
        if not channel_link and force_sub_channels[0].get("username"):
            channel_link = f"https://t.me/{force_sub_channels[0].get('username')}"
    elif legacy_channel:
        channel_link = config.get("force_sub_link")
        if not channel_link:
            try:
                chat_info = await client.get_chat(legacy_channel)
                channel_link = chat_info.invite_link or f"https://t.me/{chat_info.username}"
            except Exception:
                pass

    if not channel_link:
        channel_link = "Not configured"

    text = f"**ℹ️ {bot_name} Information**\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"

    text += "**💡 About This Bot**\n"
    text += "Your ultimate media processing tool. Easily rename, format, and organize your files with professional metadata injection and custom thumbnails.\n\n"



    # Calculate Uptime
    uptime_seconds = int(time.time() - BOT_START_TIME)
    uptime_str = f"{uptime_seconds // 86400}d {(uptime_seconds % 86400) // 3600}h"

    # Get system stats
    cpu_usage = psutil.cpu_percent()
    ram_usage = psutil.virtual_memory().percent

    text += "**📊 System Details**\n"
    text += f"• **Bot Version:** `{Config.VERSION} (Public Edition)`\n"
    text += f"• **MyFiles Engine:** `{Config.MYFILES_VERSION}`\n"
    text += f"• **Framework:** `Pyrofork v{pyrogram.__version__}`\n"
    text += f"• **Python:** `v{platform.python_version()}`\n"
    text += f"• **OS:** `{platform.system()} {platform.release()}`\n"
    text += f"• **Uptime:** `{uptime_str}`\n"
    text += f"• **Load:** `CPU {cpu_usage}% | RAM {ram_usage}%`\n"
    text += "• **Status:** `Online & Operational`\n"
    text += f"• **Community:** `{community_name}`\n\n"


    text += "**📞 Help & Support**\n"
    text += f"• **Support Contact:** {support_contact}\n"
    text += f"• **Community Link:** {channel_link}\n\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "**⚡ Powered by:** [𝕏TV](https://t.me/XTVglobal)\n"
    text += "**👨‍💻 Developed by:** [𝕏0L0™](https://t.me/davdxpx)\n"

    await message.reply_text(text, disable_web_page_preview=True)

@Client.on_message(filters.command("settings") & filters.private)
async def settings_panel(client, message):
    if not is_public_mode():
        return

    await message.reply_text(
        "⚙️ **Settings**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Manage your templates, thumbnails,\n"
        "channels, and general preferences.",
        reply_markup=get_user_main_menu(),
    )

import contextlib

from utils.telegram.logger import debug

debug("✅ Loaded handler: user_settings_callback")

@Client.on_callback_query(
    filters.regex(
        r"^(user_|edit_user_template_|edit_user_fn_template_|edit_user_sys_template_|prompt_user_.*|dumb_user_|set_lang_|set_user_workflow_|set_thumb_mode_|user_delete_msg)"
    )
)
async def user_settings_callback(client, callback_query):
    await callback_query.answer()
    if not is_public_mode():
        raise ContinuePropagation

    user_id = callback_query.from_user.id
    data = callback_query.data
    debug(f"User settings callback: {data} from user {user_id}")

    if data.startswith("dumb_user_"):
        if data.startswith("dumb_user_menu"):
            page = 1
            if "_" in data.replace("dumb_user_menu", ""):
                parts = data.split("_")
                if len(parts) >= 4:
                    with contextlib.suppress(Exception):
                        page = int(parts[3])

            channels = await db.get_dumb_channels(user_id)

            text = (
                "📺 **Manage Dumb Channels**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "> Configure your channels for auto-forwarding files.\n\n"
            )

            if not channels:
                text += "❌ __No Dumb Channels configured yet.__\n\n"

            buttons = [[InlineKeyboardButton("➕ Add New Dumb Channel", callback_data="dumbv2_start:user")]]

            if channels:
                import math
                ch_items = list(channels.items())
                total_channels = len(ch_items)
                items_per_page = 10
                total_pages = math.ceil(total_channels / items_per_page) if total_channels > 0 else 1
                page = max(1, min(page, total_pages))

                start_idx = (page - 1) * items_per_page
                end_idx = start_idx + items_per_page
                current_channels = ch_items[start_idx:end_idx]

                buttons.append([InlineKeyboardButton("─── Your Channels ───", callback_data="noop")])
                for ch_id, ch_name in current_channels:
                    buttons.append([
                        InlineKeyboardButton(f"📺 {ch_name}", callback_data=f"dumb_user_opt_{ch_id}")
                    ])

                if total_pages > 1:
                    nav = []
                    if page > 1:
                        nav.append(InlineKeyboardButton("⬅️", callback_data=f"dumb_user_menu_{page-1}"))
                    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
                    if page < total_pages:
                        nav.append(InlineKeyboardButton("➡️", callback_data=f"dumb_user_menu_{page+1}"))
                    buttons.append(nav)

            buttons.append([InlineKeyboardButton("← Back to Settings", callback_data="user_main")])

            with contextlib.suppress(MessageNotModified):
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            return

        elif data.startswith("dumb_user_opt_"):
            ch_id = data.replace("dumb_user_opt_", "")
            channels = await db.get_dumb_channels(user_id)
            if ch_id not in channels:
                await callback_query.answer("Channel not found.", show_alert=True)
                return

            ch_name = channels[ch_id]
            default_ch = await db.get_default_dumb_channel(user_id)
            movie_ch = await db.get_movie_dumb_channel(user_id)
            series_ch = await db.get_series_dumb_channel(user_id)

            is_def = "✅" if str(ch_id) == default_ch else "❌"
            is_mov = "✅" if str(ch_id) == movie_ch else "❌"
            is_ser = "✅" if str(ch_id) == series_ch else "❌"

            text = (
                f"⚙️ **Channel Settings**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"> **Name:** `{ch_name}`\n"
                f"> **ID:** `{ch_id}`\n\n"
                f"**Current Status:**\n"
                f"> 🔸 Standard Default: `{is_def}`\n"
                f"> 🎬 Movie Default: `{is_mov}`\n"
                f"> 📺 Series Default: `{is_ser}`\n\n"
                f"Select an action below to manage this channel."
            )

            buttons = [
                [InlineKeyboardButton("✏️ Rename Channel", callback_data=f"dumb_user_ren_{ch_id}")],
                [InlineKeyboardButton("🔸 Set Standard Default", callback_data=f"dumb_user_def_std_{ch_id}")],
                [InlineKeyboardButton("🎬 Set Movie Default", callback_data=f"dumb_user_def_mov_{ch_id}")],
                [InlineKeyboardButton("📺 Set Series Default", callback_data=f"dumb_user_def_ser_{ch_id}")],
                [InlineKeyboardButton("🗑 Delete Channel", callback_data=f"dumb_user_del_{ch_id}")],
                [InlineKeyboardButton("← Back to Dumb Channels", callback_data="dumb_user_menu")]
            ]

            with contextlib.suppress(MessageNotModified):
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            return

        elif data.startswith("dumb_user_ren_"):
            ch_id = data.replace("dumb_user_ren_", "")
            user_sessions[user_id] = {"state": f"awaiting_dumb_user_rename_{ch_id}", "msg_id": callback_query.message.id}
            with contextlib.suppress(MessageNotModified):
                await callback_query.message.edit_text(
                    "✏️ **Rename Channel**\n\n"
                    "Please enter the new name for this channel:\n\n"
                    "__(Send `disable` to cancel)__",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"dumb_user_opt_{ch_id}")]])
                )
            return

        elif data.startswith("dumb_user_def_std_"):
            ch_id = data.replace("dumb_user_def_std_", "")
            await db.set_default_dumb_channel(ch_id, user_id)
            await callback_query.answer("Standard Default channel set.", show_alert=True)
            callback_query.data = f"dumb_user_opt_{ch_id}"
            await user_settings_callback(client, callback_query)
            return

        elif data.startswith("dumb_user_def_mov_"):
            ch_id = data.replace("dumb_user_def_mov_", "")
            await db.set_movie_dumb_channel(ch_id, user_id)
            await callback_query.answer("Movie Default channel set.", show_alert=True)
            callback_query.data = f"dumb_user_opt_{ch_id}"
            await user_settings_callback(client, callback_query)
            return

        elif data.startswith("dumb_user_def_ser_"):
            ch_id = data.replace("dumb_user_def_ser_", "")
            await db.set_series_dumb_channel(ch_id, user_id)
            await callback_query.answer("Series Default channel set.", show_alert=True)
            callback_query.data = f"dumb_user_opt_{ch_id}"
            await user_settings_callback(client, callback_query)
            return

        elif data == "dumb_user_add":
            user_sessions[user_id] = {"state": "awaiting_dumb_user_add", "msg_id": callback_query.message.id}
            with contextlib.suppress(MessageNotModified):
                await callback_query.message.edit_text(
                    "➕ **Add Dumb Channel**\n\n"
                    "Please add me as an Administrator in the desired channel.\n"
                    "Then, forward any message from that channel to me, OR send the Channel ID (e.g. `-100...`) or Public Username.\n\n"
                    "__(Send `disable` to cancel)__",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "❌ Cancel", callback_data="dumb_user_menu"
                                )
                            ]
                        ]
                    ),
                )
            return

        elif data.startswith("dumb_user_del_"):
            ch_id = data.replace("dumb_user_del_", "")
            await db.remove_dumb_channel(ch_id, user_id)
            await callback_query.answer("Channel removed.", show_alert=True)
            callback_query.data = "dumb_user_menu"
            await globals()["user_settings_callback"](client, callback_query)
            return
        elif data == "dumb_user_set_default":
            channels = await db.get_dumb_channels(user_id)
            if not channels:
                await callback_query.answer("No channels configured.", show_alert=True)
                return
            buttons = []
            for ch_id, ch_name in channels.items():
                buttons.append(
                    [
                        InlineKeyboardButton(
                            f"⭐ {ch_name}", callback_data=f"dumb_user_def_{ch_id}"
                        )
                    ]
                )
            buttons.append(
                [InlineKeyboardButton("← Back to Dumb Channels", callback_data="dumb_user_menu")]
            )
            with contextlib.suppress(MessageNotModified):
                await callback_query.message.edit_text(
                    "Select default auto-detect channel:",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            return
        elif data.startswith("dumb_user_def_"):
            ch_id = data.replace("dumb_user_def_", "")
            await db.set_default_dumb_channel(ch_id, user_id)
            await callback_query.answer("Default channel set.", show_alert=True)
            callback_query.data = "dumb_user_menu"
            await globals()["user_settings_callback"](client, callback_query)
            return

    if data == "user_dumb_channels":
        callback_query.data = "dumb_user_menu"
        await globals()["user_settings_callback"](client, callback_query)
        return

    if data == "user_thumb_menu":
        thumb_mode = await db.get_thumbnail_mode(user_id)
        mode_str = "Deactivated (None)"
        if thumb_mode == "auto":
            mode_str = "Auto-detect (Preview)"
        elif thumb_mode == "custom":
            mode_str = "Custom Thumbnail"

        text = (
            "🖼 **Manage Thumbnail Preferences**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> **Choose how thumbnails should be handled for your processed files.**\n\n"
            f"**Current Mode:** `{mode_str}`\n\n"
            "**Options:**\n"
            "• **Auto-detect:** Uses the automatic preview image from TMDb.\n"
            "• **Custom:** Uses your uploaded personal thumbnail.\n"
            "• **Deactivated:** Skips applying any thumbnail."
        )

        buttons = [
            [
                InlineKeyboardButton(
                    "✅ Auto-detect" if thumb_mode == "auto" else "Auto-detect",
                    callback_data="set_thumb_mode_auto"
                ),
                InlineKeyboardButton(
                    "✅ Custom" if thumb_mode == "custom" else "Custom",
                    callback_data="set_thumb_mode_custom"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Deactivated (None)" if thumb_mode == "none" else "Deactivated (None)",
                    callback_data="set_thumb_mode_none"
                )
            ]
        ]

        if thumb_mode == "custom":
            buttons.append([
                InlineKeyboardButton("👀 View Custom Thumbnail", callback_data="user_thumb_view")
            ])
            buttons.append([
                InlineKeyboardButton("📤 Upload New Thumbnail", callback_data="user_thumb_set")
            ])
            buttons.append([
                InlineKeyboardButton("🗑 Remove Thumbnail", callback_data="user_thumb_remove")
            ])

        buttons.append([InlineKeyboardButton("← Back to Settings", callback_data="user_main")])

        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )

    elif data.startswith("set_thumb_mode_"):
        new_mode = data.replace("set_thumb_mode_", "")
        await db.update_thumbnail_mode(new_mode, user_id)
        await callback_query.answer(f"Thumbnail mode set to {new_mode.capitalize()}!", show_alert=True)
        callback_query.data = "user_thumb_menu"
        await globals()["user_settings_callback"](client, callback_query)
        return

    elif data == "user_thumb_view":
        thumb_bin, _ = await db.get_thumbnail(user_id)
        if thumb_bin:
            try:
                f = io.BytesIO(thumb_bin)
                f.name = "thumbnail.jpg"

                sent_msg = await client.send_photo(
                    user_id,
                    f,
                    caption="🖼 **Your Current Default Thumbnail**\n__(This message will auto-delete to keep the chat clean)__",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("✅ OK", callback_data="user_delete_msg")]]
                    )
                )

                import asyncio
                async def auto_delete():
                    await asyncio.sleep(30)
                    with contextlib.suppress(Exception):
                        await sent_msg.delete()

                asyncio.create_task(auto_delete())

                await callback_query.answer("Thumbnail sent! Check below.", show_alert=False)

            except Exception as e:
                logger.error(f"Failed to send thumbnail: {e}")
                await callback_query.answer("Error sending thumbnail!", show_alert=True)
        else:
            await callback_query.answer("No custom thumbnail currently uploaded!", show_alert=True)

    elif data == "user_delete_msg":
        with contextlib.suppress(Exception):
            await callback_query.message.delete()
        return

    elif data == "user_thumb_set":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📤 **Set Default Thumbnail**\n\n"
                "Click below to upload a new personal thumbnail. "
                "This will be embedded into your processed videos.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📤 Upload New", callback_data="prompt_user_thumb_set"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Thumbnail Settings", callback_data="user_thumb_menu"
                            )
                        ],
                    ]
                ),
            )
    elif data == "prompt_user_thumb_set":
        user_sessions[user_id] = {"state": "awaiting_user_thumb", "msg_id": callback_query.message.id}
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "🖼 **Send the new photo** to set as your personal thumbnail:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="user_thumb_menu"
                            )
                        ]
                    ]
                ),
            )
    elif data == "user_thumb_remove":
        await db.update_thumbnail(None, None, user_id)
        await db.update_thumbnail_mode("none", user_id)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "✅ **Thumbnail Removed & Deactivated**\n\nYour files will no longer use a default custom thumbnail and the thumbnail mode has been set to None.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Thumbnail Settings", callback_data="user_thumb_menu")]]
                ),
            )
    elif data == "user_templates_menu":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📋 **Templates Menu**\n\n" "Select a template category to edit:",
                reply_markup=get_user_templates_menu(),
            )
    elif data == "user_pref_separator":
        try:
            current_sep = await db.get_preferred_separator(user_id)
            sep_display = "Space" if current_sep == " " else current_sep
            await callback_query.message.edit_text(
                f"🔤 **Preferred Separator**\n\n"
                f"Choose the separator used when cleaning up filename templates.\n"
                f"Current: **{sep_display}**\n\n"
                f"Select your preferred separator below:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Dot (.)", callback_data="user_set_sep_."),
                            InlineKeyboardButton("Underscore (_)", callback_data="user_set_sep__"),
                        ],
                        [
                            InlineKeyboardButton("Space ( )", callback_data="user_set_sep_space"),
                        ],
                        [InlineKeyboardButton("← Back to Templates", callback_data="user_templates_menu")],
                    ]
                )
            )
        except MessageNotModified:
            pass
    elif data.startswith("user_set_sep_"):
        try:
            new_sep = data.split("_set_sep_")[1]
            if new_sep == "space":
                new_sep = " "

            await db.update_preferred_separator(new_sep, user_id)
            sep_display = "Space" if new_sep == " " else new_sep

            await callback_query.answer(f"Separator set to: {sep_display}", show_alert=True)

            await callback_query.message.edit_text(
                f"🔤 **Preferred Separator**\n\n"
                f"Choose the separator used when cleaning up filename templates.\n"
                f"Current: **{sep_display}**\n\n"
                f"Select your preferred separator below:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("Dot (.)", callback_data="user_set_sep_."),
                            InlineKeyboardButton("Underscore (_)", callback_data="user_set_sep__"),
                        ],
                        [
                            InlineKeyboardButton("Space ( )", callback_data="user_set_sep_space"),
                        ],
                        [InlineKeyboardButton("← Back to Templates", callback_data="user_templates_menu")],
                    ]
                )
            )
        except MessageNotModified:
            pass
    elif data == "user_templates":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Edit Metadata Templates**\n"
                f"{DIVIDER}\n\n"
                "Select a field to edit.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✏️ Title",   callback_data="edit_user_template_title"),
                            InlineKeyboardButton("✏️ Author",  callback_data="edit_user_template_author"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Artist",  callback_data="edit_user_template_artist"),
                            InlineKeyboardButton("✏️ Video",   callback_data="edit_user_template_video"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Audio",   callback_data="edit_user_template_audio"),
                            InlineKeyboardButton("✏️ Subtitle",callback_data="edit_user_template_subtitle"),
                        ],
                        [
                            InlineKeyboardButton("➡ More metadata fields", callback_data="user_templates_meta2"),
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Templates", callback_data="user_templates_menu"
                            )
                        ],
                    ]
                ),
            )
    elif data == "user_templates_meta2":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Edit Metadata Templates**\n"
                f"{DIVIDER}\n\n"
                "Extended metadata tags written to the output file.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✏️ Comment",     callback_data="edit_user_template_comment"),
                            InlineKeyboardButton("✏️ Copyright",   callback_data="edit_user_template_copyright"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Description", callback_data="edit_user_template_description"),
                            InlineKeyboardButton("✏️ Genre",       callback_data="edit_user_template_genre"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Date",        callback_data="edit_user_template_date"),
                            InlineKeyboardButton("✏️ Album",       callback_data="edit_user_template_album"),
                        ],
                        [
                            InlineKeyboardButton("✏️ Show",        callback_data="edit_user_template_show"),
                            InlineKeyboardButton("✏️ Network",     callback_data="edit_user_template_network"),
                        ],
                        [
                            InlineKeyboardButton("← Back", callback_data="user_templates"),
                        ],
                    ]
                ),
            )
    elif data == "user_caption":
        templates = await db.get_all_templates(user_id)
        current_caption = templates.get("caption", "{random}")
        vars_line = _vars_line("caption")
        rows = [
            [InlineKeyboardButton("✏️ Change", callback_data="prompt_user_caption")],
        ]
        rows.extend(_ref_and_preview("caption"))
        rows.append([
            InlineKeyboardButton(
                "← Back to Templates", callback_data="user_templates_menu"
            )
        ])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"🧾 **Edit Caption Template**\n"
                f"{DIVIDER}\n\n"
                f"Current: `{current_caption}`\n\n"
                f"Variables: {vars_line}\n"
                "Tap 📖 for the full list.\n\n"
                "> Send just `{random}` to keep the default anti-hash behaviour.",
                reply_markup=InlineKeyboardMarkup(rows),
            )
    elif data == "prompt_user_caption":
        user_sessions[user_id] = {"state": "awaiting_user_template_caption", "msg_id": callback_query.message.id}
        vars_line = _vars_line("caption")
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new caption template:**\n"
                f"{DIVIDER}\n\n"
                f"Variables: {vars_line}\n"
                "Tap 📖 for the full list.\n\n"
                "> Use `{random}` alone to keep the default anti-hash generator.",
                reply_markup=InlineKeyboardMarkup(
                    _ref_and_preview("caption")
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="user_templates_menu")]]
                ),
            )
    elif data == "user_view":
        settings = await db.get_settings(user_id)
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

        text = "👀 **Your Current Settings**\n\n"
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
                    [[InlineKeyboardButton("← Back to Settings", callback_data="user_main")]]
                ),
            )
    elif data == "user_filename_templates":
        banner = await _user_legacy_sys_banner_line(user_id)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Filename Templates**\n"
                f"{DIVIDER}\n\n"
                f"{banner}"
                "Select a template to edit.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("🎬 Movies",      callback_data="edit_user_fn_template_movies"),
                            InlineKeyboardButton("📺 Series",      callback_data="edit_user_fn_template_series"),
                        ],
                        [
                            InlineKeyboardButton("🎬 Movies Subs", callback_data="edit_user_fn_template_subtitles_movies"),
                            InlineKeyboardButton("📺 Series Subs", callback_data="edit_user_fn_template_subtitles_series"),
                        ],
                        [
                            InlineKeyboardButton("🎞 Personal Video", callback_data="edit_user_fn_template_personal_video"),
                            InlineKeyboardButton("🖼 Personal Photo", callback_data="edit_user_fn_template_personal_photo"),
                            InlineKeyboardButton("📁 Personal File",  callback_data="edit_user_fn_template_personal_file"),
                        ],
                        [
                            InlineKeyboardButton("⚙️ System (Movies)", callback_data="edit_user_sys_template_movies"),
                            InlineKeyboardButton("⚙️ System (Series)", callback_data="edit_user_sys_template_series"),
                        ],
                        [
                            InlineKeyboardButton("🧾 Caption", callback_data="user_caption"),
                        ],
                        [
                            InlineKeyboardButton(
                                "← Back to Templates", callback_data="user_templates_menu"
                            )
                        ],
                    ]
                ),
            )
    elif data.startswith("edit_user_fn_template_"):
        field = data.replace("edit_user_fn_template_", "")
        scope = FIELD_TO_SCOPE.get(field)
        if scope is None:
            await callback_query.answer("Unknown template field.", show_alert=True)
            return
        templates = await db.get_filename_templates(user_id)
        current_val = templates.get(field, "")
        default_val = Config.DEFAULT_FILENAME_TEMPLATES.get(field, "")
        stored_line = (
            f"Current: `{current_val}`"
            if current_val
            else f"Current: __not set — using default__ `{default_val}`"
        )
        vars_line = _vars_line(scope)
        label = field.replace("_", " ").title()
        rows = [
            [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_user_fn_template_{field}")],
        ]
        rows.extend(_ref_and_preview(field))
        rows.append([
            InlineKeyboardButton(
                "← Back to Filename Templates",
                callback_data="user_filename_templates",
            )
        ])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Edit Filename Template — {label}**\n"
                f"{DIVIDER}\n\n"
                f"{stored_line}\n\n"
                f"Variables: {vars_line}\n"
                "Tap 📖 for the full list.\n\n"
                "Note: File extension is added automatically.",
                reply_markup=InlineKeyboardMarkup(rows),
            )
    elif data.startswith("prompt_user_fn_template_"):
        field = data.replace("prompt_user_fn_template_", "")
        scope = FIELD_TO_SCOPE.get(field)
        user_sessions[user_id] = {"state": f"awaiting_user_fn_template_{field}", "msg_id": callback_query.message.id}
        vars_line = _vars_line(scope) if scope else ""
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new filename template for {field.replace('_', ' ').title()}:**\n"
                f"{DIVIDER}\n\n"
                + (f"Variables: {vars_line}\n" if vars_line else "")
                + "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    (_ref_and_preview(field) if scope else [])
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="user_filename_templates")]]
                ),
            )
    elif data.startswith("edit_user_sys_template_"):
        sub = data.replace("edit_user_sys_template_", "")
        if sub not in ("movies", "series"):
            return
        field = f"system_filename_{sub}"
        scope = FIELD_TO_SCOPE[field]
        templates = await db.get_all_templates(user_id)
        current_val = templates.get(field) or templates.get("system_filename", "")
        default_val = (
            Config.DEFAULT_SYSTEM_FILENAME_SERIES
            if sub == "series"
            else Config.DEFAULT_SYSTEM_FILENAME_MOVIES
        )
        stored_line = (
            f"Current: `{current_val}`"
            if current_val
            else f"Current: __not set — using default__ `{default_val}`"
        )
        vars_line = _vars_line(scope)
        label = "System Filename — " + ("Series" if sub == "series" else "Movies")
        rows = [
            [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_user_sys_template_{sub}")],
        ]
        rows.extend(_ref_and_preview(field))
        rows.append([
            InlineKeyboardButton(
                "← Back to Filename Templates",
                callback_data="user_filename_templates",
            )
        ])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"⚙️ **Edit {label}**\n"
                f"{DIVIDER}\n\n"
                f"{stored_line}\n\n"
                f"Variables: {vars_line}\n"
                "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(rows),
            )
    elif data.startswith("prompt_user_sys_template_"):
        sub = data.replace("prompt_user_sys_template_", "")
        if sub not in ("movies", "series"):
            return
        field = f"system_filename_{sub}"
        scope = FIELD_TO_SCOPE.get(field)
        user_sessions[user_id] = {"state": f"awaiting_user_sys_template_{sub}", "msg_id": callback_query.message.id}
        vars_line = _vars_line(scope) if scope else ""
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new system filename template for "
                f"{'Series' if sub == 'series' else 'Movies'}:**\n"
                f"{DIVIDER}\n\n"
                + (f"Variables: {vars_line}\n" if vars_line else "")
                + "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    (_ref_and_preview(field) if scope else [])
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="user_filename_templates")]]
                ),
            )
    elif data == "user_general_settings_menu":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "⚙️ **General Settings**\n\n"
                "Select a setting to configure:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📢 Channel Username", callback_data="user_general_channel"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🌍 Preferred Language", callback_data="user_general_language"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "⚙️ Workflow Mode", callback_data="user_general_workflow"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🎨 Preferences", callback_data="user_general_preferences"
                            )
                        ],
                        [InlineKeyboardButton("← Back to Settings", callback_data="user_main")],
                    ]
                ),
            )
    elif data == "user_general_workflow":
        current_mode = await db.get_workflow_mode(user_id)
        mode_str = "🧠 Smart Media Mode" if current_mode == "smart_media_mode" else "⚡ Quick Mode"
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"⚙️ **Personal Workflow Mode Settings**\n\n"
                f"Current Mode: `{mode_str}`\n\n"
                "**🧠 Smart Media Mode:** Auto-detects Series/Movies and fetches TMDb metadata.\n"
                "**⚡ Quick Mode:** Bypasses auto-detection and goes straight to general rename (great for personal files).\n\n"
                "Select your preferred mode:",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✅ Smart Media Mode" if current_mode == "smart_media_mode" else "🧠 Smart Media Mode",
                                callback_data="set_user_workflow_smart"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "✅ Quick Mode" if current_mode == "quick_mode" else "⚡ Quick Mode",
                                callback_data="set_user_workflow_quick"
                            )
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="user_general_settings_menu")],
                    ]
                ),
            )
    elif data == "user_general_preferences":
        from plugins.user_setup import send_user_tool_preferences_setup
        await send_user_tool_preferences_setup(client, user_id, callback_query)
        return
    elif data.startswith("set_user_workflow_"):
        new_mode = "smart_media_mode" if data.endswith("smart") else "quick_mode"
        await db.update_workflow_mode(new_mode, user_id)
        await callback_query.answer("Workflow Mode updated!", show_alert=True)

        class MockQuery:
            def __init__(self, msg, usr):
                self.message = msg
                self.from_user = usr
                self.data = "user_general_workflow"
            async def answer(self, *args, **kwargs): pass
        await globals()["user_settings_callback"](client, MockQuery(callback_query.message, callback_query.from_user))
    elif data == "user_general_channel":
        current_channel = await db.get_channel(user_id)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📢 **Channel Username Settings**\n\n"
                f"Current Channel Variable: `{current_channel}`\n\n"
                "Click below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_user_channel"
                            )
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="user_general_settings_menu")],
                    ]
                ),
            )
    elif data == "prompt_user_channel":
        user_sessions[user_id] = {"state": "awaiting_user_channel", "msg_id": callback_query.message.id}
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "⚙️ **Send the new Channel name variable to use in templates (e.g. `@MyChannel`):**",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="user_main")]]
                ),
            )
    elif data == "user_general_language":
        current_language = await db.get_preferred_language(user_id)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"🌍 **Preferred Language Settings**\n\n"
                f"Current Preferred Language: `{current_language}`\n\n"
                "This language code is used when fetching data from TMDb (e.g., `en-US`, `de-DE`, `es-ES`).\n\n"
                "Click below to change it.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✏️ Change", callback_data="prompt_user_language"
                            )
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="user_general_settings_menu")],
                    ]
                ),
            )
    elif data == "prompt_user_language":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "🌍 **Select your preferred language for TMDb Metadata:**\n\n"
                "__(Default is English)__",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("🇺🇸 English", callback_data="set_lang_en-US"),
                            InlineKeyboardButton("🇩🇪 German", callback_data="set_lang_de-DE"),
                        ],
                        [
                            InlineKeyboardButton("🇪🇸 Spanish", callback_data="set_lang_es-ES"),
                            InlineKeyboardButton("🇫🇷 French", callback_data="set_lang_fr-FR"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇳 Hindi", callback_data="set_lang_hi-IN"),
                            InlineKeyboardButton("🇮🇳 Tamil", callback_data="set_lang_ta-IN"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇳 Telugu", callback_data="set_lang_te-IN"),
                            InlineKeyboardButton("🇮🇳 Malayalam", callback_data="set_lang_ml-IN"),
                        ],
                        [
                            InlineKeyboardButton("🇯🇵 Japanese", callback_data="set_lang_ja-JP"),
                            InlineKeyboardButton("🇰🇷 Korean", callback_data="set_lang_ko-KR"),
                        ],
                        [
                            InlineKeyboardButton("🇨🇳 Chinese", callback_data="set_lang_zh-CN"),
                            InlineKeyboardButton("🇷🇺 Russian", callback_data="set_lang_ru-RU"),
                        ],
                        [
                            InlineKeyboardButton("🇮🇹 Italian", callback_data="set_lang_it-IT"),
                            InlineKeyboardButton("🇧🇷 Portuguese", callback_data="set_lang_pt-BR"),
                        ],
                        [InlineKeyboardButton("← Back to General Settings", callback_data="user_general_settings_menu")],
                    ]
                ),
            )
    elif data.startswith("set_lang_"):
        new_language = data.replace("set_lang_", "")
        await db.update_preferred_language(new_language, user_id)
        callback_query.data = "user_general_language"
        await globals()["user_settings_callback"](client, callback_query)
        return
    elif data == "user_cancel_language":
        user_sessions.pop(user_id, None)
        callback_query.data = "user_general_settings_menu"
        await globals()["user_settings_callback"](client, callback_query)
        return
    elif data == "user_cancel":
        user_sessions.pop(user_id, None)
        await callback_query.message.delete()
        return
    elif data == "user_main":
        user_sessions.pop(user_id, None)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "🛠 **Personal Settings Panel** 🛠\n\n"
                "Welcome to your personal settings.\n"
                "Here you can customize templates and thumbnails for your own files.",
                reply_markup=get_user_main_menu(),
            )
    elif data.startswith("edit_user_template_"):
        field = data.replace("edit_user_template_", "")
        if field not in _USER_METADATA_KEYS:
            await callback_query.answer("Unknown metadata template.", show_alert=True)
            return
        scope = FIELD_TO_SCOPE.get(field)
        templates = await db.get_all_templates(user_id)
        current_val = templates.get(field, "")
        default_val = Config.DEFAULT_TEMPLATES.get(field, "")
        stored_line = (
            f"Current: `{current_val}`"
            if current_val
            else f"Current: __not set — using default__ `{default_val}`"
        )
        vars_line = _vars_line(scope) if scope else ""
        rows = [
            [InlineKeyboardButton("✏️ Change", callback_data=f"prompt_user_template_{field}")],
        ]
        rows.extend(_ref_and_preview(field))
        rows.append([
            InlineKeyboardButton(
                "← Back to Metadata Templates", callback_data="user_templates"
            )
        ])
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"📝 **Edit {field.capitalize()} Metadata Template**\n"
                f"{DIVIDER}\n\n"
                f"{stored_line}\n\n"
                + (f"Variables: {vars_line}\n" if vars_line else "")
                + "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(rows),
            )
    elif data.startswith("prompt_user_template_"):
        field = data.replace("prompt_user_template_", "")
        if field not in _USER_METADATA_KEYS and field != "caption":
            return
        scope = FIELD_TO_SCOPE.get(field)
        user_sessions[user_id] = {"state": f"awaiting_user_template_{field}", "msg_id": callback_query.message.id}
        vars_line = _vars_line(scope) if scope else ""
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"✏️ **Send the new template text for {field.capitalize()}:**\n"
                f"{DIVIDER}\n\n"
                + (f"Variables: {vars_line}\n" if vars_line else "")
                + "Tap 📖 for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    (_ref_and_preview(field) if scope else [])
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="user_templates")]]
                ),
            )

@Client.on_message(filters.photo & filters.private, group=2)
async def handle_user_photo(client, message):
    if not is_public_mode():
        raise ContinuePropagation

    user_id = message.from_user.id
    if user_sessions.get(user_id) != "awaiting_user_thumb":
        raise ContinuePropagation

    msg = await message.reply_text("Processing thumbnail...")
    try:
        file_id = message.photo.file_id
        path = await client.download_media(
            message, file_name=f"downloads/{user_id}_thumb.jpg"
        )
        with open(path, "rb") as f:
            binary_data = f.read()
        await db.update_thumbnail(file_id, binary_data, user_id)
        await db.update_thumbnail_mode("custom", user_id)
        with contextlib.suppress(MessageNotModified):
            await msg.edit_text(
                "✅ Personal thumbnail updated successfully!\nYour thumbnail mode has been set to **Custom**.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Thumbnail Settings", callback_data="user_thumb_menu")]]
                ),
            )
        user_sessions.pop(user_id, None)
    except Exception as e:
        logger.error(f"Thumbnail upload failed: {e}")
        with contextlib.suppress(MessageNotModified):
            await msg.edit_text(f"❌ Error: {e}")

async def edit_or_reply(client, message, msg_id, text, reply_markup=None, disable_web_page_preview=False):
    with contextlib.suppress(Exception):
        await message.delete()
    if msg_id:
        try:
            return await client.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=text,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview
            )
        except Exception:
            pass
    return await message.reply_text(text, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)

@Client.on_message(
    (filters.text | filters.forwarded) & filters.private & ~filters.regex(r"^/"),
    group=2,
)
async def handle_user_text(client, message):
    if not is_public_mode():
        raise ContinuePropagation

    user_id = message.from_user.id
    state_obj = user_sessions.get(user_id)
    if not state_obj:
        raise ContinuePropagation

    state = state_obj if isinstance(state_obj, str) else state_obj.get("state")
    msg_id = None if isinstance(state_obj, str) else state_obj.get("msg_id")

    if state.startswith("awaiting_dumb_user_rename_"):
        ch_id = state.replace("awaiting_dumb_user_rename_", "")
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            user_sessions.pop(user_id, None)
            await edit_or_reply(client, message, msg_id, "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Channel Settings", callback_data=f"dumb_user_opt_{ch_id}")]]
                ),
            )
            return

        channels = await db.get_dumb_channels(user_id)
        if ch_id in channels:
            channels[ch_id] = val
            doc_id = db._get_doc_id(user_id)
            await db.settings.update_one({"_id": doc_id}, {"$set": {"dumb_channels": channels}}, upsert=True)
            await edit_or_reply(client, message, msg_id, f"✅ Channel renamed to **{val}**.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Channel Settings", callback_data=f"dumb_user_opt_{ch_id}")]]
                ),
            )
        user_sessions.pop(user_id, None)
        return

    if state == "awaiting_dumb_user_add":
        val = message.text.strip() if message.text else ""
        if val.lower() == "disable":
            user_sessions.pop(user_id, None)
            await edit_or_reply(client, message, msg_id, "Cancelled.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Dumb Channels", callback_data="dumb_user_menu")]]
                ),
            )
            return

        ch_id = None
        ch_name = "Custom Channel"
        if message.forward_from_chat:
            ch_id = message.forward_from_chat.id
            ch_name = message.forward_from_chat.title
        elif getattr(message, 'forward_origin', None) and getattr(message.forward_origin, 'chat', None):
            ch_id = message.forward_origin.chat.id
            ch_name = message.forward_origin.chat.title
        elif val:
            try:
                chat = await client.get_chat(val)
                ch_id = chat.id
                ch_name = chat.title or "Channel"
            except Exception as e:
                await edit_or_reply(client, message, msg_id, f"❌ Error finding channel: {e}\nTry forwarding a message instead.",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "❌ Cancel", callback_data="dumb_user_menu"
                                )
                            ]
                        ]
                    ),
                )
                return

        if ch_id:
            invite_link = None
            try:
                invite_link = await client.export_chat_invite_link(ch_id)
            except Exception as e:
                logger.warning(f"Could not export invite link for {ch_id}: {e}")

            await db.add_dumb_channel(
                ch_id, ch_name, invite_link=invite_link, user_id=user_id
            )
            await edit_or_reply(client, message, msg_id, f"✅ Added Dumb Channel: **{ch_name}** (`{ch_id}`)",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← Back to Dumb Channels", callback_data="dumb_user_menu")]]
                ),
            )
            user_sessions.pop(user_id, None)
        return

    if state.startswith("awaiting_user_template_"):
        field = state.replace("awaiting_user_template_", "")
        new_template = message.text or ""

        scope = FIELD_TO_SCOPE.get(field)
        if scope is None:
            await message.reply_text(f"❌ Unknown template field: `{field}`.")
            raise StopPropagation

        allowed = set(allowed_fields_for(scope))
        ok, err = validate_template(new_template, allowed_fields=allowed)
        if not ok:
            await message.reply_text(
                f"❌ **Invalid template**\n"
                f"{DIVIDER}\n\n{err}\n\n"
                f"You sent:\n`{new_template}`\n\n"
                "Tap 📖 below for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    reference_and_preview_buttons(field, origin="u")
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="user_templates")]]
                ),
            )
            raise StopPropagation

        await db.update_template(field, new_template, user_id)

        if field == "caption":
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Templates", callback_data="user_templates_menu")]]
            )
        else:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Templates", callback_data="user_templates")]]
            )

        await edit_or_reply(client, message, msg_id,
            f"✅ **Your {field.capitalize()} template updated**\n"
            f"{DIVIDER}\n\n`{new_template}`",
            reply_markup=reply_markup,
        )
        user_sessions.pop(user_id, None)
        raise StopPropagation

    elif state.startswith("awaiting_user_fn_template_"):
        field = state.replace("awaiting_user_fn_template_", "")
        new_template = message.text or ""

        scope = FIELD_TO_SCOPE.get(field)
        if scope is None:
            await message.reply_text(f"❌ Unknown filename template field: `{field}`.")
            raise StopPropagation

        allowed = set(allowed_fields_for(scope))
        ok, err = validate_template(new_template, allowed_fields=allowed)
        if not ok:
            await message.reply_text(
                f"❌ **Invalid filename template**\n"
                f"{DIVIDER}\n\n{err}\n\n"
                f"You sent:\n`{new_template}`\n\n"
                "Tap 📖 below for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    reference_and_preview_buttons(field, origin="u")
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="user_filename_templates")]]
                ),
            )
            raise StopPropagation

        await db.update_filename_template(field, new_template, user_id)

        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "← Back to Filename Templates",
                        callback_data="user_filename_templates",
                    )
                ]
            ]
        )
        await edit_or_reply(client, message, msg_id,
            f"✅ **Your filename template for {field.replace('_', ' ').title()} updated**\n"
            f"{DIVIDER}\n\n`{new_template}`",
            reply_markup=reply_markup,
        )
        user_sessions.pop(user_id, None)
        raise StopPropagation

    elif state.startswith("awaiting_user_sys_template_"):
        sub = state.replace("awaiting_user_sys_template_", "")
        if sub not in ("movies", "series"):
            raise ContinuePropagation
        field = f"system_filename_{sub}"
        new_template = message.text or ""

        scope = FIELD_TO_SCOPE[field]
        allowed = set(allowed_fields_for(scope))
        ok, err = validate_template(new_template, allowed_fields=allowed)
        if not ok:
            await message.reply_text(
                f"❌ **Invalid system filename template**\n"
                f"{DIVIDER}\n\n{err}\n\n"
                f"You sent:\n`{new_template}`\n\n"
                "Tap 📖 below for the full list.",
                reply_markup=InlineKeyboardMarkup(
                    reference_and_preview_buttons(field, origin="u")
                    + [[InlineKeyboardButton("❌ Cancel", callback_data="user_filename_templates")]]
                ),
            )
            raise StopPropagation

        await db.update_template(field, new_template, user_id)
        label = "Series" if sub == "series" else "Movies"
        await edit_or_reply(client, message, msg_id,
            f"✅ **Your System Filename ({label}) updated**\n"
            f"{DIVIDER}\n\n`{new_template}`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← Back to Filename Templates", callback_data="user_filename_templates")]]
            ),
        )
        user_sessions.pop(user_id, None)
        raise StopPropagation

    elif state == "awaiting_user_channel":
        new_channel = message.text
        await db.update_channel(new_channel, user_id)

        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back to Settings", callback_data="user_main")]]
        )
        await edit_or_reply(client, message, msg_id, f"✅ Your channel variable updated to:\n`{new_channel}`",
            reply_markup=reply_markup,
        )
        user_sessions.pop(user_id, None)

    else:
        raise ContinuePropagation

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
