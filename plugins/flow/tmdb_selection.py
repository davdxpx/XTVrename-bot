# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""TMDb-pick / manual-entry / send-as / ready-file helpers.

Bridges the ``awaiting_search_*`` results back to the rest of the flow:
once the user picks a TMDb card (``sel_tmdb_``), enters data manually
(``manual_entry``), or chooses how to receive a photo (``send_as_*``),
the session is ready to continue with destination selection.

Also owns ``process_ready_file`` — the async shim that dispatches a
pre-uploaded file through the processor once every pre-condition (file
message, dumb channel, dest folder) is on the session. Several upload
branches call it so it lives here next to the selection handlers that
prep the session.
"""

import contextlib

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db import db
from utils.media.detect import analyze_filename
from utils.state import clear_session, get_data, set_state, update_data
from utils.tasks import spawn as _spawn_task
from utils.telegram.log import get_logger
from utils.tmdb import tmdb

logger = get_logger("plugins.flow.tmdb_selection")


@Client.on_callback_query(filters.regex(r"^manual_entry$"))
async def handle_manual_entry(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    logger.debug(f"User {user_id} selected manual entry.")

    update_data(user_id, "tmdb_id", None)

    media_type = get_data(user_id).get("type", "movie")

    set_state(user_id, "awaiting_manual_title")
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            f"✍️ **Manual Entry ({media_type.capitalize()})**\n\n"
            "Please enter the exact title and year you want to use.\n"
            "Format: `Title (Year)`\n"
            "Example: `My Family Vacation (2023)`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )


@Client.on_callback_query(filters.regex(r"^send_as_(photo|document)$"))
async def handle_send_as_preference(client, callback_query):
    from plugins.flow.destinations import prompt_destination_folder

    user_id = callback_query.from_user.id
    pref = callback_query.data.split("_")[2]

    update_data(user_id, "send_as", pref)
    await prompt_destination_folder(client, user_id, callback_query.message, is_edit=True)


@Client.on_callback_query(filters.regex(r"^sel_tmdb_(movie|series)_(\d+)$"))
async def handle_tmdb_selection(client, callback_query):
    from utils.tmdb.gate import ensure_tmdb

    if not await ensure_tmdb(client, callback_query, feature="TMDb title selection"):
        return

    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")
    media_type = data[2]
    tmdb_id = data[3]

    try:
        lang = await db.get_preferred_language(user_id)
        details = await tmdb.get_details(media_type, tmdb_id, language=lang)
        if not details:
            await callback_query.answer("Error fetching details!", show_alert=True)
            return
    except Exception as e:
        logger.error(f"TMDb details failed: {e}")
        await callback_query.answer("Error fetching details!", show_alert=True)
        return

    title = details.get("title") if media_type == "movie" else details.get("name")
    year = (
        details.get("release_date")
        if media_type == "movie"
        else details.get("first_air_date", "")
    )[:4]
    poster = (
        f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}"
        if details.get("poster_path")
        else None
    )

    update_data(user_id, "tmdb_id", tmdb_id)
    update_data(user_id, "title", title)
    update_data(user_id, "year", year)
    update_data(user_id, "poster", poster)

    data = get_data(user_id)

    from plugins.flow.destinations import (
        initiate_language_selection,
        prompt_destination_folder,
    )

    if data.get("is_subtitle"):
        await initiate_language_selection(client, user_id, callback_query.message)
    else:
        await prompt_destination_folder(
            client, user_id, callback_query.message, is_edit=True
        )


async def process_ready_file(client, user_id, message_obj, session_data):
    """Dispatch a pre-uploaded general-mode file through the processor.

    Called once the session has a dumb channel + dest folder + general
    filename. Sends the file into the processor and clears the session.
    Returns early for non-general types (auto-detection handles those).
    """
    if session_data.get("type") == "general":
        data = {
            "type": "general",
            "original_name": session_data.get("original_name"),
            "file_message_id": session_data.get("file_message_id"),
            "file_chat_id": session_data.get("file_chat_id"),
            "is_auto": False,
            "dumb_channel": session_data.get("dumb_channel"),
            "dest_folder": session_data.get("dest_folder"),
            "send_as": session_data.get("send_as"),
            "general_name": session_data.get("general_name"),
        }

        meta = analyze_filename(session_data.get("original_name"))

        if "type" in meta and data.get("type"):
            meta.pop("type")
        data.update(meta)

        try:
            msg = await client.get_messages(
                session_data.get("file_chat_id"), session_data.get("file_message_id")
            )
            data["file_message"] = msg
            if getattr(message_obj, "delete", None):
                with contextlib.suppress(Exception):
                    await message_obj.delete()
            reply_msg = await client.send_message(user_id, "Processing file...")
            from plugins.process import process_file
            _spawn_task(
                process_file(client, reply_msg, data),
                user_id=user_id,
                label=f"process_file:ready:{user_id}",
                key=reply_msg.id,
            )
        except Exception as e:
            logger.error(f"Failed to process ready file: {e}")
            await client.send_message(user_id, f"Error: {e}")

        clear_session(user_id)
        return
