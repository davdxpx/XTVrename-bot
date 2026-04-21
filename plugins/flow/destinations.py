# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Destination folder + Dumb Channel + subtitle language + cancel.

These menus are the "where should this go?" part of the flow: once the
user has picked a type and a TMDb title (or manual entry), we ask for
a destination folder, then a dumb channel, then — for subtitles — a
language. The Cancel handler also lives here since it's the common
exit for all of these destination prompts.
"""

import asyncio
import contextlib
import math
import os

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import Config
from db import db
from plugins.flow.sessions import (
    _clear_persisted_session,
    _expiry_warnings,
    _persist_session_to_db,
)
from utils.state import (
    clear_session,
    get_data,
    get_state,
    set_state,
    update_data,
)
from utils.telegram.log import get_logger

logger = get_logger("plugins.flow.destinations")


async def prompt_destination_folder(client, user_id, message_obj, is_edit=False, page=1):
    folders = []
    query = {"type": "custom"}
    if Config.PUBLIC_MODE:
        query["user_id"] = user_id
    cursor = db.folders.find(query).sort("created_at", -1)
    async for folder in cursor:
        folders.append(folder)

    total_folders = len(folders)
    items_per_page = 5
    total_pages = math.ceil(total_folders / items_per_page) if total_folders > 0 else 1
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_folders = folders[start_idx:end_idx]

    buttons = []

    # Options for non-specific folders
    buttons.append([
        InlineKeyboardButton("🤖 Auto-Assign Folder", callback_data="sel_dest_auto"),
    ])
    buttons.append([
        InlineKeyboardButton("📁 Save to MyFiles (Root)", callback_data="sel_dest_root"),
    ])
    buttons.append([
        InlineKeyboardButton("🚫 Don't save to MyFiles", callback_data="sel_dest_none")
    ])
    buttons.append([
        InlineKeyboardButton("➕ Create New Folder", callback_data="sel_dest_create")
    ])

    if current_folders:
        buttons.append([InlineKeyboardButton("─── Your Folders ───", callback_data="noop")])
        for f in current_folders:
            buttons.append([
                InlineKeyboardButton(f"📁 {f['name']}", callback_data=f"sel_dest_f_{str(f['_id'])}")
            ])

        if total_pages > 1:
            nav = []
            if page > 1:
                nav.append(InlineKeyboardButton("⬅️", callback_data=f"sel_dest_page_{page-1}"))
            nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav.append(InlineKeyboardButton("➡️", callback_data=f"sel_dest_page_{page+1}"))
            buttons.append(nav)

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")])

    text = (
        "🗂 **Destination Folder**\n\n"
        "Where would you like to save the processed files?\n"
        "If you select a Dumb Channel in the next step, they will still be sent there regardless of this setting."
    )

    set_state(user_id, "awaiting_destination_selection")
    reply_markup = InlineKeyboardMarkup(buttons)

    if is_edit:
        with contextlib.suppress(MessageNotModified):
            await message_obj.edit_text(text, reply_markup=reply_markup)
    else:
        await client.send_message(user_id, text, reply_markup=reply_markup)


async def prompt_dumb_channel(client, user_id, message_obj, is_edit=False, page=1):
    channels = await db.get_dumb_channels(user_id)
    session_data = get_data(user_id)
    has_file = session_data and session_data.get("file_message_id")

    if not channels:
        if has_file:
            from plugins.flow.tmdb_selection import process_ready_file
            await process_ready_file(client, user_id, message_obj, session_data)
            return

        set_state(user_id, "awaiting_file_upload")
        asyncio.create_task(_persist_session_to_db(user_id))
        text = "✅ **Ready!**\n\nNow, **send me the file(s)** you want to rename."
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
        )
        if is_edit:
            with contextlib.suppress(MessageNotModified):
                await message_obj.edit_text(text, reply_markup=reply_markup)
            raise StopPropagation
        else:
            await client.send_message(user_id, text, reply_markup=reply_markup)
        return

    set_state(user_id, "awaiting_dumb_channel_selection")
    text = "📺 **Dumb Channel Selection**\n\nWhere should the files from this session be sent?"
    buttons = []

    channel_list = list(channels.items())
    total_channels = len(channel_list)
    items_per_page = 5
    total_pages = math.ceil(total_channels / items_per_page) if total_channels > 0 else 1
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_channels = channel_list[start_idx:end_idx]

    buttons.append(
        [
            InlineKeyboardButton(
                "❌ Don't send to Dumb Channel", callback_data="sel_dumb_none"
            )
        ]
    )

    for ch_id, ch_name in current_channels:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"📺 Send to {ch_name}", callback_data=f"sel_dumb_{ch_id}"
                )
            ]
        )

    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"sel_dumb_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"sel_dumb_page_{page+1}"))
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")])

    if is_edit:
        with contextlib.suppress(MessageNotModified):
            await message_obj.edit_text(
                text, reply_markup=InlineKeyboardMarkup(buttons)
            )
    else:
        await client.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^sel_dest_(.*)$"))
async def handle_dest_selection(client, callback_query):
    if not get_state(callback_query.from_user.id):
        return await callback_query.answer("⚠️ Session expired. Please start again.", show_alert=True)

    await callback_query.answer()
    user_id = callback_query.from_user.id
    action = callback_query.matches[0].group(1)

    if action.startswith("page_"):
        page = int(action.split("_")[1])
        await prompt_destination_folder(client, user_id, callback_query.message, is_edit=True, page=page)
        return

    if action == "create":
        set_state(user_id, "awaiting_dest_folder_name")
        update_data(user_id, "dest_msg_id", callback_query.message.id)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "📁 **Create New Folder**\n\nPlease enter a name for the new folder:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
            )
        return

    dest = None
    if action == "root":
        dest = "root"
    elif action == "none":
        dest = "none"
    elif action == "auto":
        dest = "auto"
    elif action.startswith("f_"):
        dest = action[2:]

    update_data(user_id, "dest_folder", dest)
    await prompt_dumb_channel(client, user_id, callback_query.message, is_edit=True)


@Client.on_callback_query(filters.regex(r"^sel_dumb_(.*)$"))
async def handle_dumb_selection(client, callback_query):
    from plugins.flow.tmdb_selection import process_ready_file

    if not get_state(callback_query.from_user.id):
        return await callback_query.answer("⚠️ Session expired. Please start again.", show_alert=True)

    user_id = callback_query.from_user.id
    action = callback_query.matches[0].group(1)

    if action.startswith("page_"):
        page = int(action.split("_")[1])
        await prompt_dumb_channel(client, user_id, callback_query.message, is_edit=True, page=page)
        return

    await callback_query.answer()
    ch_id = action

    if ch_id != "none":
        update_data(user_id, "dumb_channel", ch_id)
    else:
        update_data(user_id, "dumb_channel", None)

    session_data = get_data(user_id)

    has_file = session_data and session_data.get("file_message_id")

    if session_data.get("type") == "general" and has_file:
        await process_ready_file(client, user_id, callback_query.message, session_data)
        return

    if has_file:
        await process_ready_file(client, user_id, callback_query.message, session_data)
        return

    set_state(user_id, "awaiting_file_upload")
    asyncio.create_task(_persist_session_to_db(user_id))
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "✅ **Ready!**\n\n" "Now, **send me the file(s)** you want to rename.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )


async def initiate_language_selection(client, user_id, message_obj):
    set_state(user_id, "awaiting_language")
    buttons = [
        [
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
            InlineKeyboardButton("🇩🇪 German", callback_data="lang_de"),
        ],
        [
            InlineKeyboardButton("🇫🇷 French", callback_data="lang_fr"),
            InlineKeyboardButton("🇪🇸 Spanish", callback_data="lang_es"),
        ],
        [
            InlineKeyboardButton("🇮🇹 Italian", callback_data="lang_it"),
            InlineKeyboardButton("✍️ Custom", callback_data="lang_custom"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
    ]

    text = "**Select Subtitle Language**\n\nChoose a language or select 'Custom' to type a code (e.g. por, rus)."

    if isinstance(message_obj, str):
        await client.send_message(
            user_id, text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    elif hasattr(message_obj, "edit_text"):
        with contextlib.suppress(MessageNotModified):
            await message_obj.edit_text(
                text, reply_markup=InlineKeyboardMarkup(buttons)
            )
    else:
        await client.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^lang_"))
async def handle_language_callback(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")[1]

    if data == "custom":
        set_state(user_id, "awaiting_language_custom")
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "✍️ **Enter Custom Language Code**\n\n"
                "Please type the language code (e.g. `por`, `hin`, `jpn`, `pt-br`):",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
                ),
            )
        return

    update_data(user_id, "language", data)
    await prompt_destination_folder(client, user_id, callback_query.message, is_edit=True)


@Client.on_callback_query(filters.regex(r"^gen_send_as_(document|media)$"))
async def handle_gen_send_as(client, callback_query):
    if not get_state(callback_query.from_user.id):
        return await callback_query.answer("⚠️ Session expired. Please start again.", show_alert=True)
    await callback_query.answer()
    user_id = callback_query.from_user.id
    pref = callback_query.data.split("_")[3]

    update_data(user_id, "send_as", pref)

    file_name = get_data(user_id).get("original_name", "unknown")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            f"📄 **File:** `{file_name}`\n\n"
            f"**Output Format:** `{pref.capitalize()}`\n\n"
            "Click the button below to rename the file.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✏️ Rename", callback_data="gen_prompt_rename"
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )


@Client.on_callback_query(filters.regex(r"^gen_prompt_rename$"))
async def handle_gen_prompt_rename(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    set_state(user_id, "awaiting_general_name")

    session_data = get_data(user_id)
    file_msg_id = session_data.get("file_message_id")
    file_chat_id = session_data.get("file_chat_id")

    with contextlib.suppress(Exception):
        await callback_query.message.delete()

    orig_name = session_data.get("original_name", "Unknown File")
    text = (
        "✏️ **Enter the new name for this file:**\n\n"
        "You can use variables like `{filename}`, `{Season_Episode}`, `{Quality}`, `{Year}`, `{Title}`.\n"
        "__(The extension is added automatically)__\n\n"
        f"Original Name: `{orig_name}`"
    )

    prompt_msg = None
    if file_msg_id and file_chat_id:
        try:
            prompt_msg = await client.send_message(
                chat_id=user_id,
                text=text,
                reply_to_message_id=file_msg_id,
                reply_markup=ForceReply(selective=True, placeholder="Type new name here...")
            )
        except Exception:
            prompt_msg = await client.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
            )
    else:
        prompt_msg = await client.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
        )

    if prompt_msg:
        update_data(user_id, "rename_prompt_msg_id", prompt_msg.id)


@Client.on_callback_query(filters.regex(r"^cancel_rename$"))
async def handle_cancel(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    data = get_data(user_id)
    if data and data.get("archive_path"):
        archive_path = data.get("archive_path")
        if os.path.exists(archive_path):
            try:
                os.remove(archive_path)
            except Exception as e:
                logger.warning(f"Failed to remove archive on cancel: {e}")

    clear_session(user_id)
    await _clear_persisted_session(user_id)
    if user_id in _expiry_warnings:
        _expiry_warnings[user_id].cancel()
        del _expiry_warnings[user_id]
    toggles = await db.get_feature_toggles()
    show_other = toggles.get("audio_editor", True) or toggles.get("file_converter", True) or toggles.get("watermarker", True) or toggles.get("subtitle_extractor", True)

    if Config.PUBLIC_MODE and not show_other:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                pf = plan_settings.get("features", {})
                if pf.get("audio_editor", True) or pf.get("file_converter", True) or pf.get("watermarker", True) or pf.get("subtitle_extractor", True):
                    show_other = True

    buttons = [
        [InlineKeyboardButton("🎬 Start Renaming Manually", callback_data="start_renaming")]
    ]
    if show_other:
        buttons.append([InlineKeyboardButton("✨ Other Features", callback_data="other_features_menu")])
    buttons.append([InlineKeyboardButton("📖 Help & Guide", callback_data="help_guide")])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "**Current Task Cancelled** ❌\n\n"
            "Your progress has been cleared.\n"
            "You can simply send me a file anytime to start over, or use the buttons below.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
