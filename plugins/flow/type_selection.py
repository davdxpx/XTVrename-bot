# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Media-type entry points.

Reached from ``plugins/start.py`` and the session-expired "start new"
button; this module decides which branch of the rename flow the user
enters (general / movie / series / personal / subtitles) and stores
``type`` on the session so downstream steps know how to behave.
"""

import contextlib

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from plugins.flow.sessions import (
    _clear_persisted_session,
    _debounce_callback,
    _start_expiry_timer,
)
from plugins.user_setup import track_tool_usage
from utils.state import clear_session, get_state, set_state, update_data
from utils.telegram.log import get_logger

logger = get_logger("plugins.flow.type_selection")


@Client.on_callback_query(filters.regex(r"^(start_renaming|force_start_renaming|cancel_override)$"))
async def handle_start_renaming(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, 'rename')
    user_id = callback_query.from_user.id
    cb_data = callback_query.data

    if _debounce_callback(user_id, cb_data):
        await callback_query.answer()
        return
    await callback_query.answer()

    if cb_data == "cancel_override":
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "Keeping your current session. You can continue where you left off.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel Session", callback_data="cancel_rename")]]
                ),
            )
        return

    existing_state = get_state(user_id)
    if existing_state and cb_data != "force_start_renaming":
        state_labels = {
            "awaiting_type": "selecting media type",
            "awaiting_search_movie": "searching for a movie",
            "awaiting_search_series": "searching for a series",
            "awaiting_manual_title": "entering a title",
            "awaiting_file_upload": "waiting for file upload",
            "awaiting_destination_selection": "selecting a destination",
            "awaiting_general_name": "entering a filename",
            "awaiting_general_file": "uploading a file",
        }
        label = state_labels.get(existing_state, existing_state)
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                f"**Active Session Detected**\n\n"
                f"You have an active session: **{label}**.\n"
                "Starting a new session will cancel the current one.\n\n"
                "What would you like to do?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Start New Session", callback_data="force_start_renaming")],
                    [InlineKeyboardButton("← Keep Current", callback_data="cancel_override")],
                ]),
            )
        return

    logger.debug(f"Start renaming flow for {user_id}")
    clear_session(user_id)
    await _clear_persisted_session(user_id)
    set_state(user_id, "awaiting_type")
    _start_expiry_timer(client, user_id)

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "**Select Media Type**\n\n" "What are you renaming today?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📄 General Mode (Any File)", callback_data="type_general"
                        )
                    ],
                    [
                        InlineKeyboardButton("🎬 Movie", callback_data="type_movie"),
                        InlineKeyboardButton("📺 Series", callback_data="type_series"),
                    ],
                    [
                        InlineKeyboardButton(
                            "📹 Personal Video", callback_data="type_personal_video"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📸 Personal Photo", callback_data="type_personal_photo"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📁 Personal File", callback_data="type_personal_file"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📝 Subtitles", callback_data="type_subtitles"
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )


@Client.on_callback_query(filters.regex(r"^type_general$"))
async def handle_type_general(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    logger.debug(f"User {user_id} selected general type")

    update_data(user_id, "type", "general")
    update_data(user_id, "tmdb_id", None)

    set_state(user_id, "awaiting_general_file")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "📄 **General Mode**\n\n"
            "Please **send me the file** you want to rename.\n"
            "__(You can send any type of file: Documents, Videos, Audio, etc.)__",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )


@Client.on_callback_query(filters.regex(r"^type_personal_(video|photo|file)$"))
async def handle_type_personal(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    personal_type = callback_query.data.split("_")[2]
    logger.debug(f"User {user_id} selected personal type: {personal_type}")

    update_data(user_id, "type", "movie")
    update_data(user_id, "tmdb_id", None)
    update_data(user_id, "personal_type", personal_type)

    set_state(user_id, "awaiting_manual_title")

    if personal_type == "video":
        label = "Video"
    elif personal_type == "photo":
        label = "Photo"
    else:
        label = "File"

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            f"✍️ **Personal {label} Details**\n\n"
            "Please enter the name you want to use for this file.\n"
            "Format: `Title (Year)` or just `Title`\n"
            "Example: `Family Vacation Hawaii (2024)`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )


@Client.on_callback_query(filters.regex(r"^type_(movie|series)$"))
async def handle_type_selection(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    media_type = callback_query.data.split("_")[1]
    logger.debug(f"User {user_id} selected type: {media_type}")

    update_data(user_id, "type", media_type)
    set_state(user_id, f"awaiting_search_{media_type}")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            f"🔍 **Search {media_type.capitalize()}**\n\n"
            f"Please enter the name of the {media_type} (e.g. 'Zootopia' or 'The Rookie').",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )


@Client.on_callback_query(filters.regex(r"^type_subtitles$"))
async def handle_type_subtitles(client, callback_query):
    await callback_query.answer()
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "**Select Subtitle Type**\n\n" "Is this for a Movie or a Series?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🎬 Movie", callback_data="type_sub_movie"
                        ),
                        InlineKeyboardButton(
                            "📺 Series", callback_data="type_sub_series"
                        ),
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )


@Client.on_callback_query(filters.regex(r"^type_sub_(movie|series)$"))
async def handle_subtitle_type_selection(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    media_type = callback_query.data.split("_")[2]
    logger.debug(f"User {user_id} selected subtitle type: {media_type}")

    update_data(user_id, "type", media_type)
    update_data(user_id, "is_subtitle", True)
    set_state(user_id, f"awaiting_search_{media_type}")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            f"🔍 **Search {media_type.capitalize()} (Subtitles)**\n\n"
            f"Please enter the name of the {media_type}.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
