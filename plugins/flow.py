# --- Imports ---
import asyncio
import datetime
import math
import os
import re

from bson.objectid import ObjectId
from pyrogram import Client, ContinuePropagation, StopPropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from plugins.process import process_file
from plugins.user_setup import track_tool_usage
from tools.AudioMetadataEditor import render_audio_menu
from utils.auth import auth_filter
from utils.media.detect import analyze_filename, auto_match_tmdb, template_key_for
from utils.state import clear_session, get_data, get_state, mark_for_db_persist, set_state, update_data
from utils.tasks import spawn as _spawn_task
from utils.telegram.log import get_logger
from utils.tmdb import tmdb

logger = get_logger("plugins.flow")
logger.info("Loading plugins.flow...")

file_sessions = {}
_file_session_timestamps = {}

batch_sessions = {}

batch_tasks = {}

batch_status_msgs = {}

_processing_callbacks = {}
_expiry_warnings = {}

import time as _time


def _touch_file_session(msg_id):
    """Track when a file_session entry was last accessed."""
    _file_session_timestamps[msg_id] = _time.time()

def cleanup_stale_file_sessions(max_age_seconds: int = 7200):
    """Remove file_sessions entries older than max_age_seconds (default 2 hours)."""
    now = _time.time()
    stale = [mid for mid, ts in _file_session_timestamps.items() if now - ts > max_age_seconds]
    for mid in stale:
        file_sessions.pop(mid, None)
        _file_session_timestamps.pop(mid, None)
    return len(stale)

def cleanup_stale_debounce_entries(max_age_seconds: int = 300):
    """Remove debounce entries older than max_age_seconds."""
    now = _time.time()
    stale_keys = [k for k, v in _processing_callbacks.items() if now - v > max_age_seconds]
    for k in stale_keys:
        _processing_callbacks.pop(k, None)
    return len(stale_keys)

def _on_session_expired(user_id):
    """Called by state.py when a session naturally expires."""
    task = _expiry_warnings.pop(user_id, None)
    if task:
        task.cancel()
    batch_sessions.pop(user_id, None)
    task = batch_tasks.pop(user_id, None)
    if task:
        task.cancel()
    batch_status_msgs.pop(user_id, None)

import contextlib

from utils.state import register_expire_callback

register_expire_callback(_on_session_expired)

async def _persist_session_to_db(user_id: int):
    """Save critical session data to DB for crash recovery."""
    from db import db as _db
    data = get_data(user_id)
    if not data:
        return
    persist_data = {}
    for key in ("state", "type", "title", "year", "season", "episode", "quality",
                "tmdb_id", "poster", "language", "is_subtitle", "dumb_channel",
                "dest_folder", "send_as", "general_name", "original_name"):
        if key in data:
            persist_data[key] = data[key]
    if persist_data:
        await _db.save_flow_session(user_id, persist_data)
        mark_for_db_persist(user_id)

async def _clear_persisted_session(user_id: int):
    """Clear persisted session from DB."""
    from db import db as _db
    await _db.clear_flow_session(user_id)

async def _schedule_expiry_warning(client, user_id: int, delay_seconds: int = 3300):
    """Warn user 5 minutes before session expiry, then confirm cancellation on actual expiry."""
    try:
        await asyncio.sleep(delay_seconds)
        state = get_state(user_id)
        if not state:
            _expiry_warnings.pop(user_id, None)
            return

        warning_msg = await client.send_message(
            user_id,
            "⚠️ Your renaming session will expire in **5 minutes** due to inactivity.\n"
            "Send a file or press Cancel to avoid losing your progress.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel Session", callback_data="cancel_rename")]
            ])
        )

        # Wait the remaining 5 minutes
        await asyncio.sleep(300)

        # Check if session is still active (user may have interacted)
        state = get_state(user_id)
        if not state:
            # Session was already ended by user action
            with contextlib.suppress(Exception):
                await warning_msg.edit_text(
                    "✅ Your session was already ended.",
                    reply_markup=None
                )
            _expiry_warnings.pop(user_id, None)
            return

        # Session is still active — expire it now
        clear_session(user_id)
        await _clear_persisted_session(user_id)
        _expiry_warnings.pop(user_id, None)

        with contextlib.suppress(Exception):
            await warning_msg.edit_text(
                "❌ **Session Expired**\n\n"
                "Your renaming session has been cancelled due to inactivity.\n"
                "Send a file or use /start to begin a new session.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Start New Session", callback_data="force_start_renaming")]
                ])
            )

    except asyncio.CancelledError:
        _expiry_warnings.pop(user_id, None)
    except Exception as e:
        logger.debug(f"Expiry warning error for {user_id}: {e}")
        _expiry_warnings.pop(user_id, None)

def _start_expiry_timer(client, user_id: int):
    """Start or restart the expiry warning timer."""
    old_task = _expiry_warnings.pop(user_id, None)
    if old_task:
        old_task.cancel()
    _expiry_warnings[user_id] = asyncio.create_task(_schedule_expiry_warning(client, user_id))

def _debounce_callback(user_id: int, callback_id: str) -> bool:
    """Returns True if this callback should be skipped (duplicate rapid-fire)."""
    key = f"{user_id}:{callback_id}"
    now = _time.time()
    last = _processing_callbacks.get(key, 0)
    if now - last < 0.5:
        return True
    _processing_callbacks[key] = now
    # Periodic inline cleanup: prune entries older than 60s when dict gets large
    if len(_processing_callbacks) > 500:
        cleanup_stale_debounce_entries(60)
    return False

# === Helper Functions ===
def format_episode_str(episode):
    if isinstance(episode, list):
        return "".join([f"E{int(e):02d}" for e in episode])
    elif episode:
        return f"E{int(episode):02d}"
    return ""

@Client.on_callback_query(filters.regex(r"^(start_renaming|force_start_renaming|cancel_override)$"))

# --- Handlers ---
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

# === Helper Functions ===
async def manual_title_handler(client, message):
    user_id = message.from_user.id
    text = message.text.strip()

    match = re.search(r"^(.*?)(?:\s*\((\d{4})\))?$", text)
    title = match.group(1).strip() if match else text
    year = match.group(2) if match and match.group(2) else ""

    update_data(user_id, "title", title)
    update_data(user_id, "year", year)
    update_data(user_id, "poster", None)

    data = get_data(user_id)
    media_type = data.get("type")

    if media_type == "series":
        if data.get("is_subtitle"):
            await initiate_language_selection(client, user_id, message)
        else:
            await prompt_destination_folder(client, user_id, message, is_edit=False)
        from pyrogram import StopPropagation
        raise StopPropagation
    elif data.get("personal_type") == "photo":
        set_state(user_id, "awaiting_send_as")
        await message.reply_text(
            f"📸 **Photo Selected**\n\n**Title:** {title}\n**Year:** {year}\n\n"
            "How would you like to receive the output?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🖼 Send as Photo", callback_data="send_as_photo"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📁 Send as Document (File)",
                            callback_data="send_as_document",
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )
    else:
        await prompt_destination_folder(client, user_id, message, is_edit=False)
        from pyrogram import StopPropagation
        raise StopPropagation

async def search_handler(client, message, media_type):
    from utils.tmdb.gate import ensure_tmdb

    if not await ensure_tmdb(client, message, feature="Manual TMDb search"):
        return

    user_id = message.from_user.id
    query = message.text
    logger.debug(f"Searching {media_type} for: {query}")
    msg = await message.reply_text(f"🔍 Searching for '{query}'...")

    try:
        lang = await db.get_preferred_language(user_id)
        if media_type == "movie":
            results = await tmdb.search_movie(query, language=lang)
        else:
            results = await tmdb.search_tv(query, language=lang)
    except Exception as e:
        logger.error(f"TMDb search failed: {e}")
        with contextlib.suppress(MessageNotModified):
            await msg.edit_text(f"❌ Search Error: {e}")
        return

    if not results:
        with contextlib.suppress(MessageNotModified):
            await msg.edit_text(
                "❌ **No results found.**\n\n"
                "This could be a personal file, home video, or a regional/unknown series not listed on TMDb.\n"
                "You can enter the details manually by clicking below.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "✍️ Skip / Enter Manually", callback_data="manual_entry"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data="cancel_rename"
                            )
                        ],
                    ]
                ),
            )
        return

    buttons = []
    for item in results:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{item['title']} ({item['year']})",
                    callback_data=f"sel_tmdb_{media_type}_{item['id']}",
                )
            ]
        )

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")])

    with contextlib.suppress(MessageNotModified):
        await msg.edit_text(
            f"**Select {media_type.capitalize()}**\n\n"
            f"Found {len(results)} results for '{query}':",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=5)
async def handle_text_input(client, message):
    user_id = message.from_user.id

    if not Config.PUBLIC_MODE and not (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS):
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    state = get_state(user_id)
    logger.debug(f"Text input from {user_id}: {message.text} | State: {state}")

    if not state:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    if state == "awaiting_dest_folder_name":
        folder_name = message.text.strip()
        user_doc = await db.get_user(user_id)
        if Config.PUBLIC_MODE:
            plan = user_doc.get("premium_plan", "standard") if user_doc and user_doc.get("is_premium") else "free"
        else:
            plan = "global"

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        limits = config.get("myfiles_limits", {}).get(plan, {})
        folder_limit = limits.get("folder_limit", 5)

        if folder_limit != -1:
            query_filter = {"user_id": user_id, "type": "custom"} if Config.PUBLIC_MODE else {"type": "custom"}
            count = await db.folders.count_documents(query_filter)
            if count >= folder_limit:
                with contextlib.suppress(Exception):
                    await message.delete()
                msg_id = get_data(user_id).get("dest_msg_id")
                if msg_id:
                    with contextlib.suppress(Exception):
                        await client.edit_message_text(message.chat.id, msg_id, f"❌ You have reached your custom folder limit ({folder_limit}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Options", callback_data="sel_dest_page_1")]]))
                else:
                    await message.reply_text(f"❌ You have reached your custom folder limit ({folder_limit}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Options", callback_data="sel_dest_page_1")]]))
                set_state(user_id, "awaiting_destination_selection")
                return

        folder_id = ObjectId()
        await db.folders.insert_one({
            "_id": folder_id,
            "user_id": user_id,
            "name": folder_name,
            "type": "custom",
            "created_at": datetime.datetime.utcnow()
        })

        with contextlib.suppress(Exception):
            await message.delete()

        msg_id = get_data(user_id).get("dest_msg_id")

        # update destination selection and proceed to dumb channel selection
        update_data(user_id, "dest_folder", str(folder_id))

        if msg_id:
            with contextlib.suppress(Exception):
                await client.edit_message_text(message.chat.id, msg_id, f"✅ Folder **{folder_name}** created successfully and selected!")

            # Wait briefly then show dumb channel selection
            import asyncio
            await asyncio.sleep(1.5)

            # Use a dummy object with `.edit_text`
            class DummyMessage:
                async def edit_text(self, text, reply_markup=None):
                    await client.edit_message_text(message.chat.id, msg_id, text, reply_markup=reply_markup)

            await prompt_dumb_channel(client, user_id, DummyMessage(), is_edit=True)
        else:
            msg = await message.reply_text(f"✅ Folder **{folder_name}** created successfully and selected!")
            import asyncio
            await asyncio.sleep(1.5)
            await prompt_dumb_channel(client, user_id, msg, is_edit=True)
        from pyrogram import StopPropagation
        raise StopPropagation

    if state == "awaiting_search_movie":
        await search_handler(client, message, "movie")
        from pyrogram import StopPropagation
        raise StopPropagation
    elif state == "awaiting_search_series":
        await search_handler(client, message, "series")
        from pyrogram import StopPropagation
        raise StopPropagation
    elif state == "awaiting_manual_title":
        await manual_title_handler(client, message)
        from pyrogram import StopPropagation
        raise StopPropagation
    elif state == "awaiting_system_filename":
        template = message.text.strip()
        await db.update_template("system_filename", template, user_id=user_id)
        set_state(user_id, None)
        await message.reply_text(f"✅ System Filename template updated to:\n`{template}`")
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state == "awaiting_general_name":
        user_id = message.from_user.id
        session_data = get_data(user_id)
        file_msg_id = session_data.get("file_message_id")
        prompt_msg_id = session_data.get("rename_prompt_msg_id")

        valid_reply_ids = [file_msg_id, prompt_msg_id]

        if file_msg_id and (not message.reply_to_message or message.reply_to_message.id not in valid_reply_ids):
            warning_msg = await message.reply_text("⚠️ **Please reply directly to my prompt message** when sending the new name, so I know which file you are renaming.", quote=True)

            async def delete_warning():
                import asyncio
                await asyncio.sleep(5)
                try:
                    await warning_msg.delete()
                    await message.delete()
                except Exception:
                    pass
            import asyncio
            asyncio.create_task(delete_warning())
            return

        new_name = message.text.strip()
        update_data(user_id, "general_name", new_name)

        async def delayed_cleanup():
            import asyncio
            await asyncio.sleep(1)
            with contextlib.suppress(Exception):
                await message.delete()
            if prompt_msg_id:
                with contextlib.suppress(Exception):
                    await client.delete_messages(chat_id=user_id, message_ids=prompt_msg_id)
        import asyncio
        asyncio.create_task(delayed_cleanup())

        await prompt_destination_folder(client, user_id, message, is_edit=False)
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state and state.startswith("awaiting_audio_"):
        action = state.replace("awaiting_audio_", "")

        val = message.text.strip() if getattr(message, "text", None) else ""
        if action == "thumb":
            if val == "-":
                update_data(user_id, "audio_thumb_id", None)
            else:
                await message.reply_text(
                    "Please send a photo for the cover art, or send '-' to clear it."
                )
                return
        else:
            if val == "-":
                val = ""
            update_data(user_id, f"audio_{action}", val)

        set_state(user_id, "awaiting_audio_menu")
        await render_audio_menu(client, message, user_id)
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state == "awaiting_watermark_text":
        user_id = message.from_user.id
        text = message.text.strip()
        update_data(user_id, "watermark_content", text)
        set_state(user_id, "awaiting_watermark_position")

        await message.reply_text(
            "©️ **Image Watermarker**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Where should the watermark be placed?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("↖️ Top-Left", callback_data="wm_pos_topleft"),
                        InlineKeyboardButton("↗️ Top-Right", callback_data="wm_pos_topright"),
                    ],
                    [
                        InlineKeyboardButton("↙️ Bottom-Left", callback_data="wm_pos_bottomleft"),
                        InlineKeyboardButton("↘️ Bottom-Right", callback_data="wm_pos_bottomright"),
                    ],
                    [InlineKeyboardButton("⊹ Center", callback_data="wm_pos_center")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state == "awaiting_language_custom":
        lang = message.text.strip().lower()
        if len(lang) > 10 or not lang.replace("-", "").isalnum():
            await message.reply_text(
                "Invalid language code. Keep it short (e.g. 'en', 'pt-br')."
            )
            return

        update_data(user_id, "language", lang)
        await prompt_destination_folder(client, user_id, message, is_edit=False)
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state.startswith("awaiting_episode_correction_"):
        msg_id = int(state.split("_")[-1])
        if msg_id not in file_sessions:
            await message.reply_text("Session expired. Please start a new session.")
            clear_session(user_id)
            from pyrogram import StopPropagation
            raise StopPropagation
        if message.text.isdigit():
            file_sessions[msg_id]["episode"] = int(message.text)
            set_state(user_id, "awaiting_file_upload")
            asyncio.create_task(_persist_session_to_db(user_id))
            await update_confirmation_message(client, msg_id, user_id)
            await message.delete()
        else:
            await message.reply_text("Invalid number. Try again.")
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state.startswith("awaiting_season_correction_"):
        msg_id = int(state.split("_")[-1])
        if msg_id not in file_sessions:
            await message.reply_text("Session expired. Please start a new session.")
            clear_session(user_id)
            from pyrogram import StopPropagation
            raise StopPropagation
        if message.text.isdigit():
            file_sessions[msg_id]["season"] = int(message.text)
            set_state(user_id, "awaiting_file_upload")
            asyncio.create_task(_persist_session_to_db(user_id))
            await update_confirmation_message(client, msg_id, user_id)
            await message.delete()
        else:
            await message.reply_text("Invalid number. Try again.")
        from pyrogram import StopPropagation
        raise StopPropagation

    elif state.startswith("awaiting_search_correction_"):
        msg_id = int(state.split("_")[-1])
        if msg_id not in file_sessions:
            await message.reply_text("Session expired. Please start a new session.")
            clear_session(user_id)
            from pyrogram import StopPropagation
            raise StopPropagation
        else:
            fs = file_sessions[msg_id]
            query = message.text
            mtype = fs["type"]

            msg = await message.reply_text(f"🔍 Searching {mtype} for '{query}'...")

            try:
                lang = await db.get_preferred_language(user_id)
                if mtype == "series":
                    results = await tmdb.search_tv(query, language=lang)
                else:
                    results = await tmdb.search_movie(query, language=lang)
            except Exception as e:
                await msg.edit_text(f"Error: {e}")
                from pyrogram import StopPropagation
                raise StopPropagation from e

            if not results:
                with contextlib.suppress(MessageNotModified):
                    await msg.edit_text(
                        "No results found.",
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        "Back", callback_data=f"back_confirm_{msg_id}"
                                    )
                                ]
                            ]
                        ),
                    )
                from pyrogram import StopPropagation
                raise StopPropagation

            buttons = []
            for item in results:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            f"{item['title']} ({item['year']})",
                            callback_data=f"correct_tmdb_{msg_id}_{item['id']}",
                        )
                    ]
                )
            buttons.append(
                [InlineKeyboardButton("Cancel", callback_data=f"back_confirm_{msg_id}")]
            )

            with contextlib.suppress(MessageNotModified):
                await msg.edit_text(
                    f"Select correct {mtype}:",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            from pyrogram import StopPropagation
            raise StopPropagation

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
    if data.get("is_subtitle"):
        await initiate_language_selection(client, user_id, callback_query.message)
    else:
        await prompt_destination_folder(
            client, user_id, callback_query.message, is_edit=True
        )

async def process_ready_file(client, user_id, message_obj, session_data):
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

            from plugins.flow import process_ready_file
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
            from pyrogram import StopPropagation
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
    from utils.state import get_state
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

    from utils.state import get_state
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

    from utils.state import get_state
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

from pyrogram.types import ForceReply


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

async def process_batch(client, user_id):
    if user_id not in batch_sessions:
        return

    batch_dict = batch_sessions.pop(user_id)
    batch = batch_dict.get("items", [])
    if not batch:
        return

    if user_id in batch_status_msgs:
        try:
            await batch_status_msgs[user_id].delete()
        except Exception:
            pass
        finally:
            del batch_status_msgs[user_id]

    def get_sort_key(item):
        data = item["data"]
        is_series = data.get("type") == "series"

        if is_series:
            ep = data.get("episode", 0)
            ep_sort = ep[0] if isinstance(ep, list) else ep
            return (0, data.get("season", 0), ep_sort)
        else:
            return (1, data.get("original_name", "").lower(), 0)

    sorted_batch = sorted(batch, key=get_sort_key)

    for item in sorted_batch:
        message = item["message"]
        data = item["data"]
        is_auto = data.get("is_auto", False)

        msg = await message.reply_text("Processing file...", quote=True)
        file_sessions[msg.id] = data
        _touch_file_session(msg.id)

        if is_auto:
            await update_auto_detected_message(client, msg.id, user_id)
        else:
            await update_confirmation_message(client, msg.id, user_id)

import random
import time
import uuid

from db import db
from utils.auth import check_force_sub
from utils.auth.gate import check_and_send_welcome, send_force_sub_gate
from utils.media.archive import check_password_protected, extract_archive, is_archive
from utils.queue_manager import queue_manager
from utils.telegram.progress import progress_for_pyrogram


@Client.on_message(
    (filters.document | filters.video | filters.photo | filters.audio | filters.voice)
    & filters.private,
    group=5,
)
async def handle_file_upload(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state is None:
        user_mode = await db.get_workflow_mode(user_id if Config.PUBLIC_MODE else None)
        if user_mode == "quick_mode":

            state = "awaiting_general_file"
            set_state(user_id, state)
            update_data(user_id, "type", "general")

            file_name = "unknown_file.bin"
            if message.document:
                file_name = message.document.file_name
            elif message.video:
                file_name = message.video.file_name
            elif message.audio:
                file_name = message.audio.file_name
            elif message.photo:
                file_name = f"image_{message.id}.jpg"
            if not file_name:
                file_name = "unknown_file.bin"
            update_data(user_id, "original_name", file_name)
            update_data(user_id, "file_message_id", message.id)
            update_data(user_id, "file_chat_id", message.chat.id)
            set_state(user_id, "awaiting_general_send_as")
            await message.reply_text(
                f"📄 **File Received:** `{file_name}`\n\n"
                "How would you like to receive the output?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📁 Send as Document (File)", callback_data="gen_send_as_document")],
                    [InlineKeyboardButton("▶️ Send as Media (Video/Photo/Audio)", callback_data="gen_send_as_media")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
                ])
            )
            return

    if state == "awaiting_convert_file":
        if (
            not getattr(message, "photo", None)
            and not getattr(message, "video", None)
            and not getattr(message, "audio", None)
            and not getattr(message, "voice", None)
            and not getattr(message, "document", None)
        ):
            await message.reply_text("Please send an image, video, or audio file.")
            return

        file_name = "unknown_file.bin"
        file_kind = None  # "video" / "audio" / "image"

        if getattr(message, "video", None):
            file_name = message.video.file_name or "video.mp4"
            file_kind = "video"
        elif getattr(message, "audio", None):
            file_name = message.audio.file_name or "audio.mp3"
            file_kind = "audio"
        elif getattr(message, "voice", None):
            file_name = f"voice_{message.id}.ogg"
            file_kind = "audio"
        elif getattr(message, "photo", None):
            file_name = f"image_{message.id}.jpg"
            file_kind = "image"
        elif getattr(message, "document", None):
            file_name = message.document.file_name or "file.bin"
            mime = (message.document.mime_type or "").lower()
            if "video" in mime:
                file_kind = "video"
            elif "audio" in mime:
                file_kind = "audio"
            elif "image" in mime:
                file_kind = "image"
            else:
                # Fallback: sniff by extension.
                ext = os.path.splitext(file_name)[1].lower().lstrip(".")
                if ext in ("mp4", "mkv", "mov", "avi", "webm", "flv", "3gp", "ts", "m4v"):
                    file_kind = "video"
                elif ext in ("mp3", "m4a", "ogg", "opus", "flac", "wav", "wma", "aac"):
                    file_kind = "audio"
                elif ext in ("png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif", "ico", "avif"):
                    file_kind = "image"

        if not file_kind:
            await message.reply_text(
                "❌ Could not determine file type.\n\n"
                "> Please send a clear **image**, **video**, or **audio** file."
            )
            return

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)
        update_data(user_id, "file_kind", file_kind)
        # Default audio bitrate — changeable via the Audio Bitrate submenu.
        update_data(user_id, "audio_bitrate", "192")

        # Render the new mega-edition category menu (Video/Audio/Image root).
        from tools.FileConverter import render_category_menu
        await render_category_menu(message, user_id, edit=False)
        return

    if state == "awaiting_audio_thumb":
        if not getattr(message, "photo", None):
            await message.reply_text("Please send a photo for the cover art.")
            return

        update_data(user_id, "audio_thumb_id", message.photo.file_id)
        set_state(user_id, "awaiting_audio_menu")
        await render_audio_menu(client, message, user_id)
        from pyrogram import StopPropagation
        raise StopPropagation

    if state == "awaiting_watermark_image":
        if not getattr(message, "photo", None) and not getattr(
            message, "document", None
        ):
            await message.reply_text("Please send an image.")
            return

        file_name = f"image_{message.id}.jpg"
        if getattr(message, "document", None):
            file_name = message.document.file_name or "image.jpg"
            if "image" not in (message.document.mime_type or ""):
                await message.reply_text("Please send a valid image document.")
                return

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)

        await message.reply_text(
            "©️ **Image Watermarker**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> What type of watermark do you want to add?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📝 Text Watermark", callback_data="watermark_type_text"
                        ),
                        InlineKeyboardButton(
                            "🖼️ Image Watermark", callback_data="watermark_type_image"
                        ),
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )
        return

    if state == "awaiting_watermark_overlay":
        if not getattr(message, "photo", None) and not getattr(
            message, "document", None
        ):
            await message.reply_text(
                "Please send an image to use as the watermark overlay."
            )
            return

        file_id = (
            message.photo.file_id
            if getattr(message, "photo", None)
            else message.document.file_id
        )
        update_data(user_id, "watermark_content", file_id)
        set_state(user_id, "awaiting_watermark_position")

        await message.reply_text(
            "©️ **Image Watermarker**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Where should the watermark be placed?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("↖️ Top-Left", callback_data="wm_pos_topleft"),
                        InlineKeyboardButton("↗️ Top-Right", callback_data="wm_pos_topright"),
                    ],
                    [
                        InlineKeyboardButton("↙️ Bottom-Left", callback_data="wm_pos_bottomleft"),
                        InlineKeyboardButton("↘️ Bottom-Right", callback_data="wm_pos_bottomright"),
                    ],
                    [InlineKeyboardButton("⊹ Center", callback_data="wm_pos_center")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )
        from pyrogram import StopPropagation
        raise StopPropagation

    if state == "awaiting_audio_file":
        if (
            not getattr(message, "audio", None)
            and not getattr(message, "voice", None)
            and not getattr(message, "document", None)
        ):
            await message.reply_text("Please send an audio file.")
            return

        file_name = "audio.mp3"
        if getattr(message, "audio", None):
            file_name = message.audio.file_name or "audio.mp3"
            update_data(user_id, "audio_title", message.audio.title or "")
            update_data(user_id, "audio_artist", message.audio.performer or "")
        elif getattr(message, "document", None):
            file_name = message.document.file_name or "file.mp3"

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)

        set_state(user_id, "awaiting_audio_menu")
        await render_audio_menu(client, message, user_id)
        from pyrogram import StopPropagation
        raise StopPropagation

    # === VIDEO TRIMMER STATES ===
    if state == "awaiting_trim_file":
        if not getattr(message, "video", None) and not getattr(message, "document", None):
            await message.reply_text(
                "❌ Please send a **video file** to trim.\n\n"
                "> Supported: MP4, MKV, AVI, MOV, WebM"
            )
            return

        file_name = "video.mkv"
        if getattr(message, "video", None):
            file_name = message.video.file_name or "video.mp4"
        elif getattr(message, "document", None):
            file_name = message.document.file_name or "file.bin"

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)
        set_state(user_id, "awaiting_trim_start")

        await message.reply_text(
            "✂️ **Video Trimmer**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> 📄 **File:** `{file_name}`\n\n"
            "Send the **start timestamp** for the trim.\n"
            "**Format:** `HH:MM:SS` or `MM:SS`\n\n"
            "__Example:__ `00:01:30` or `1:30`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
        return

    if state == "awaiting_trim_start":
        if not getattr(message, "text", None):
            await message.reply_text("Please send a timestamp like `00:01:30` or `1:30`.")
            return

        from tools.VideoTrimmer import normalize_timestamp, validate_timestamp
        ts = message.text.strip()
        if not validate_timestamp(ts):
            await message.reply_text(
                "❌ Invalid timestamp format.\n\n"
                "> Use `HH:MM:SS` or `MM:SS`\n"
                "> Example: `00:01:30` or `1:30`"
            )
            return

        normalized = normalize_timestamp(ts)
        update_data(user_id, "trim_start", normalized)
        set_state(user_id, "awaiting_trim_end")

        await message.reply_text(
            "✂️ **Video Trimmer**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> ▶️ **Start:** `{normalized}`\n\n"
            "Now send the **end timestamp** for the trim.\n"
            "**Format:** `HH:MM:SS` or `MM:SS`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
        return

    if state == "awaiting_trim_end":
        if not getattr(message, "text", None):
            await message.reply_text("Please send a timestamp like `00:05:00` or `5:00`.")
            return

        from tools.VideoTrimmer import normalize_timestamp, validate_timestamp
        ts = message.text.strip()
        if not validate_timestamp(ts):
            await message.reply_text(
                "❌ Invalid timestamp format.\n\n"
                "> Use `HH:MM:SS` or `MM:SS`\n"
                "> Example: `00:05:00` or `5:00`"
            )
            return

        normalized = normalize_timestamp(ts)
        update_data(user_id, "trim_end", normalized)
        session_data = get_data(user_id)

        data = {
            "type": "trim",
            "original_name": session_data.get("original_name"),
            "file_message_id": session_data.get("file_message_id"),
            "file_chat_id": session_data.get("file_chat_id"),
            "trim_start": session_data.get("trim_start"),
            "trim_end": normalized,
            "is_auto": False,
        }

        try:
            msg = await client.get_messages(
                session_data.get("file_chat_id"), session_data.get("file_message_id")
            )
            data["file_message"] = msg
            reply_msg = await client.send_message(
                user_id,
                "✂️ **Video Trimmer**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"> ▶️ **Start:** `{session_data.get('trim_start')}`\n"
                f"> ⏹️ **End:** `{normalized}`\n\n"
                "> ⏳ Trimming video..."
            )
            from plugins.process import process_file
            _spawn_task(
                process_file(client, reply_msg, data),
                user_id=user_id,
                label=f"process_file:trim:{user_id}",
                key=reply_msg.id,
            )
        except Exception as e:
            logger.error(f"Failed to get message for trim mode: {e}")
            await client.send_message(user_id, f"❌ Error: `{e}`")

        clear_session(user_id)
        return

    # === MEDIA INFO STATE ===
    if state == "awaiting_mediainfo_file":
        if (
            not getattr(message, "video", None)
            and not getattr(message, "audio", None)
            and not getattr(message, "document", None)
            and not getattr(message, "photo", None)
        ):
            await message.reply_text("Please send a media file (video, audio, image, or document).")
            return

        file_name = "unknown_file.bin"
        if getattr(message, "video", None):
            file_name = message.video.file_name or "video.mp4"
        elif getattr(message, "audio", None):
            file_name = message.audio.file_name or "audio.mp3"
        elif getattr(message, "document", None):
            file_name = message.document.file_name or "file.bin"
        elif getattr(message, "photo", None):
            file_name = f"image_{message.id}.jpg"

        status_msg = await message.reply_text(
            "ℹ️ **Media Info**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> ⏳ Downloading and analyzing file..."
        )

        try:
            input_path = os.path.join(Config.DOWNLOAD_DIR, f"{user_id}_{message.id}_probe_input")
            downloaded = await client.download_media(message, file_name=input_path)
            if downloaded and os.path.exists(downloaded):
                from utils.media.ffmpeg_tools import probe_file
                probe_data, _ = await probe_file(downloaded)
                from tools.MediaInfo import format_media_info
                info_text = format_media_info(probe_data, file_name)
                await status_msg.edit_text(
                    info_text,
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🔄 Analyze Another", callback_data="media_info_menu")],
                         [InlineKeyboardButton("❌ Close", callback_data="help_close")]]
                    ),
                )
                with contextlib.suppress(Exception):
                    os.remove(downloaded)
            else:
                await status_msg.edit_text("❌ Failed to download file for analysis.")
        except Exception as e:
            logger.error(f"MediaInfo analysis failed: {e}")
            await status_msg.edit_text(f"❌ Analysis failed: `{e}`")

        clear_session(user_id)
        return

    # === VOICE NOTE CONVERTER STATE ===
    if state == "awaiting_voice_file":
        if (
            not getattr(message, "audio", None)
            and not getattr(message, "document", None)
            and not getattr(message, "voice", None)
        ):
            await message.reply_text(
                "❌ Please send an **audio file**.\n\n"
                "> Supported: MP3, FLAC, M4A, WAV, AAC, OGG"
            )
            return

        file_name = "audio.mp3"
        if getattr(message, "audio", None):
            file_name = message.audio.file_name or "audio.mp3"
        elif getattr(message, "document", None):
            file_name = message.document.file_name or "file.bin"
        elif getattr(message, "voice", None):
            file_name = "voice.ogg"

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)

        data = {
            "type": "voice_convert",
            "original_name": file_name,
            "file_message_id": message.id,
            "file_chat_id": message.chat.id,
            "file_message": message,
            "is_auto": False,
        }

        reply_msg = await client.send_message(
            user_id,
            "🎙️ **Voice Note Converter**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> ⏳ Converting to OGG Opus voice note..."
        )
        from plugins.process import process_file
        _spawn_task(
            process_file(client, reply_msg, data),
            user_id=user_id,
            label=f"process_file:voice:{user_id}",
            key=reply_msg.id,
        )
        clear_session(user_id)
        return

    # === VIDEO NOTE CONVERTER STATE ===
    if state == "awaiting_videonote_file":
        if not getattr(message, "video", None) and not getattr(message, "document", None):
            await message.reply_text(
                "❌ Please send a **video file**.\n\n"
                "> The video will be cropped to a square and converted."
            )
            return

        file_name = "video.mp4"
        if getattr(message, "video", None):
            file_name = message.video.file_name or "video.mp4"
        elif getattr(message, "document", None):
            file_name = message.document.file_name or "file.bin"

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)

        data = {
            "type": "video_note",
            "original_name": file_name,
            "file_message_id": message.id,
            "file_chat_id": message.chat.id,
            "file_message": message,
            "is_auto": False,
        }

        reply_msg = await client.send_message(
            user_id,
            "⭕ **Video Note Converter**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> ⏳ Cropping to square and converting..."
        )
        from plugins.process import process_file
        _spawn_task(
            process_file(client, reply_msg, data),
            user_id=user_id,
            label=f"process_file:videonote:{user_id}",
            key=reply_msg.id,
        )
        clear_session(user_id)
        return

    if state == "awaiting_general_file":
        file_name = "unknown_file.bin"
        if message.document:
            file_name = message.document.file_name
        elif message.video:
            file_name = message.video.file_name
        elif message.audio:
            file_name = message.audio.file_name
        elif message.photo:
            file_name = f"image_{message.id}.jpg"

        if not file_name:
            file_name = "unknown_file.bin"

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)

        set_state(user_id, "awaiting_general_send_as")
        await message.reply_text(
            f"📄 **File Received:** `{file_name}`\n\n"
            "How would you like to receive the output?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📁 Send as Document (File)",
                            callback_data="gen_send_as_document",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "▶️ Send as Media (Video/Photo/Audio)",
                            callback_data="gen_send_as_media",
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )
        return

    if not Config.PUBLIC_MODE:
        if not (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS):
            return
    else:
        config = await db.get_public_config()
        if not await check_force_sub(client, user_id):
            await send_force_sub_gate(client, message, config)
            return

        await check_and_send_welcome(client, message, config)

    if await db.is_user_blocked(user_id):
        await message.reply_text(
            "🚫 **Access Blocked**\n\nYou have been blocked from using this bot."
        )
        return

    media = message.document or message.video or message.audio or message.photo

    file_size = getattr(media, "file_size", 0) if media else 0

    if file_size > 0:
        if file_size > 4000 * 1024 * 1024:
            await message.reply_text(
                "❌ **File Too Large**\n\nTelegram's absolute maximum file size is 4GB. This file cannot be processed."
            )
            return

        if file_size > 2000 * 1000 * 1000:
            if getattr(client, "user_bot", None) is None:
                await message.reply_text(
                    "❌ **𝕏TV Pro™ Required**\n\nThis file is larger than 2GB. The 𝕏TV Pro™ Premium Userbot must be configured to process files of this size."
                )
                return

            if Config.PUBLIC_MODE and not (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS):
                config = await db.get_public_config()
                access_setting = config.get("xtv_pro_4gb_access", "all")

                if access_setting != "all":
                    user_doc = await db.get_user(user_id)
                    is_premium = user_doc and user_doc.get("is_premium", False)
                    plan_name = user_doc.get("premium_plan", "standard") if user_doc else "standard"

                    if not is_premium:
                        await message.reply_text("❌ **Premium Required**\n\nThis file is larger than 2GB. Please upgrade to a Premium plan to process files up to 4GB.")
                        return

                    if access_setting == "premium_deluxe" and plan_name != "deluxe":
                        await message.reply_text("❌ **Premium Deluxe Required**\n\nThis file is larger than 2GB. Only Premium Deluxe users can process files up to 4GB. Please upgrade your plan.")
                        return

        quota_ok, error_msg, _ = await db.check_daily_quota(user_id, file_size)
        if not quota_ok:
            await message.reply_text(f"🛑 **Quota Exceeded**\n\n{error_msg}")
            return

        import shutil
        total, used, free = shutil.disk_usage(Config.DOWNLOAD_DIR)
        required_space = file_size * 2.5
        if free < required_space:
            required_mb = required_space / (1024 * 1024)
            free_mb = free / (1024 * 1024)
            await message.reply_text(
                f"❌ **System Error: Insufficient Disk Space**\n\n"
                f"The server does not have enough storage space to process this file.\n"
                f"Required: ~{required_mb:.2f} MB\n"
                f"Available: {free_mb:.2f} MB"
            )
            return

        await db.reserve_quota(user_id, file_size)

    if state != "awaiting_file_upload":
        if state is None:
            await handle_auto_detection(client, message)
            return
        elif state == "awaiting_convert_file":
            pass
        else:
            state_labels = {
                "awaiting_type": "selecting a media type",
                "awaiting_search_movie": "searching for a movie",
                "awaiting_search_series": "searching for a series",
                "awaiting_manual_title": "entering a title manually",
                "awaiting_dumb_channel_selection": "selecting a channel",
                "awaiting_destination_selection": "selecting a destination folder",
                "awaiting_general_name": "entering a new filename",
                "awaiting_general_send_as": "choosing output format",
                "awaiting_language_custom": "entering a language code",
            }
            label = state_labels.get(state, "a different step")
            await message.reply_text(
                f"You're currently **{label}**.\n"
                "Please complete that step first, or cancel to start over.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel & Start Over", callback_data="cancel_rename")]
                ]),
                quote=True,
            )
            return

    if message.photo:
        file_name = f"image_{message.id}.jpg"
    else:
        file_name = (
            message.document.file_name if message.document else message.video.file_name
        )

    if not file_name:
        file_name = "unknown.mkv"

    if is_archive(file_name):
        await handle_archive_upload(client, message, user_id, file_name, state)
        return

    quality = "720p"
    if re.search(r"1080p", file_name, re.IGNORECASE):
        quality = "1080p"
    elif re.search(r"2160p|4k", file_name, re.IGNORECASE):
        quality = "2160p"
    elif re.search(r"480p", file_name, re.IGNORECASE):
        quality = "480p"

    episode = 1
    season = 1
    session_data = get_data(user_id)
    if session_data.get("type") == "series":
        match = re.search(r"[sS](\d{1,2})[eE](\d{1,2}(?:[eE]\d{1,2})*)", file_name)
        if match:
            season = int(match.group(1))
            ep_list = [int(e) for e in re.split(r"[eE]", match.group(2)) if e]
            episode = ep_list if len(ep_list) > 1 else ep_list[0]
        else:
            match = re.search(r"[eE](\d{1,2}(?:[eE]\d{1,2})*)", file_name)
            if match:
                ep_list = [int(e) for e in re.split(r"[eE]", match.group(1)) if e]
                episode = ep_list if len(ep_list) > 1 else ep_list[0]
            else:
                match = re.search(r"(?:\s|\.|-|^)(\d{1,2})x(\d{1,2})(?:\s|\.|-|$)", file_name, re.IGNORECASE)
                if match:
                    season = int(match.group(1))
                    episode = int(match.group(2))
                else:
                    match = re.search(r"season\s*(\d+).*?episode\s*(\d+)", file_name, re.IGNORECASE)
                    if match:
                        season = int(match.group(1))
                        episode = int(match.group(2))

    lang = (
        session_data.get("language", "en") if session_data.get("is_subtitle") else None
    )

    is_priority = False
    has_batch_pro = False
    if Config.PUBLIC_MODE:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                plan_features = plan_settings.get("features", {})
                is_priority = plan_features.get("priority_queue", False)
                # Check batch_processing_pro: global toggle AND per-plan
                global_toggles = await db.get_feature_toggles()
                has_batch_pro = global_toggles.get("batch_processing_pro", True) and plan_features.get("batch_processing_pro", False)
    else:
        # Private mode: check global toggle only
        global_toggles = await db.get_feature_toggles()
        has_batch_pro = global_toggles.get("batch_processing_pro", True)

    if user_id not in batch_sessions:
        batch_id = queue_manager.create_batch()
        batch_sessions[user_id] = {"batch_id": batch_id, "items": []}
        msg = await message.reply_text(
            "⏳ **Sorting Files...**\nPlease wait a moment.", quote=True
        )
        batch_status_msgs[user_id] = msg

    old_task = batch_tasks.pop(user_id, None)
    if old_task:
        old_task.cancel()

    if user_id not in batch_sessions:
        return

    batch_id = batch_sessions[user_id]["batch_id"]
    item_id = str(uuid.uuid4())

    quality_priority = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}

    sort_key = (
        (0, season, episode[0] if isinstance(episode, list) else episode)
        if session_data.get("type") == "series"
        else (1, quality_priority.get(quality, 4), 0)
    )
    display_name = (
        f"S{season:02d}{format_episode_str(episode)}"
        if session_data.get("type") == "series"
        else f"{quality}"
    )

    update_data(user_id, "batch_id", batch_id)

    queue_manager.add_to_batch(batch_id, item_id, sort_key, display_name, message.id, is_priority=is_priority)

    metadata = analyze_filename(file_name)
    data = {
        "file_message": message,
        "file_chat_id": message.chat.id,
        "file_message_id": message.id,
        "quality": quality,
        "episode": episode,
        "season": season,
        "original_name": file_name,
        "language": lang,
        "type": session_data.get("type"),
        "is_auto": False,
        "dumb_channel": session_data.get("dumb_channel"),
        "batch_id": batch_id,
        "item_id": item_id,
        "specials": metadata.get("specials", []),
        "codec": metadata.get("codec", ""),
        "audio": metadata.get("audio", ""),
        "has_batch_pro": has_batch_pro,
    }
    batch_sessions[user_id]["items"].append({"message": message, "data": data})

    async def wait_and_process():
        try:
            # Batch Pro users get faster collection, priority users fastest
            delay = 1.0 if is_priority else (3.0 if has_batch_pro else 5.0)
            await asyncio.sleep(delay)
            if batch_tasks.get(user_id) == asyncio.current_task():
                batch_tasks.pop(user_id, None)
            await process_batch(client, user_id)
        except asyncio.CancelledError:
            pass

    batch_tasks[user_id] = asyncio.create_task(wait_and_process())

async def handle_archive_upload(client, message, user_id, file_name, state):
    msg = await message.reply_text("📦 **Archive detected!**\n\nDownloading to inspect contents...")

    download_dir = Config.DOWNLOAD_DIR
    os.makedirs(download_dir, exist_ok=True)

    archive_path = os.path.join(download_dir, f"{user_id}_{message.id}_{file_name}")
    start_time = time.time()

    try:
        downloaded_path = await client.download_media(
            message,
            file_name=archive_path,
            progress=progress_for_pyrogram,
            progress_args=(
                "📥 **Downloading Archive...**",
                msg,
                start_time,
                "core"
            )
        )

        if not downloaded_path or not os.path.exists(downloaded_path):
            await msg.edit_text("❌ Failed to download archive.")
            return

        is_protected = await check_password_protected(downloaded_path)

        if is_protected:
            update_data(user_id, "archive_path", downloaded_path)
            update_data(user_id, "archive_msg_id", msg.id)
            update_data(user_id, "archive_state", state)
            set_state(user_id, "awaiting_archive_password")
            await msg.edit_text(
                "🔐 **Password Protected Archive**\n\n"
                "This archive requires a password. Please send me the password to extract it.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
                )
            )
            return

        await process_extracted_archive(client, user_id, downloaded_path, msg, state)

    except Exception as e:
        logger.error(f"Archive processing error: {e}")
        with contextlib.suppress(Exception):
            await msg.edit_text(f"❌ Error processing archive: {e}")

@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=4)
async def handle_password_input(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == "awaiting_archive_password":
        password = message.text.strip()
        data = get_data(user_id)
        archive_path = data.get("archive_path")
        msg_id = data.get("archive_msg_id")
        orig_state = data.get("archive_state")
        attempts = int(data.get("archive_password_attempts", 0)) + 1
        max_attempts = 3

        try:
            msg = await client.get_messages(user_id, msg_id)
            await msg.edit_text("⏳ **Attempting to extract with password...**")
            extract_ok = await process_extracted_archive(
                client, user_id, archive_path, msg, orig_state, password
            )
        except Exception as e:
            logger.error(f"Error handling password: {e}")
            await message.reply_text(f"Error: {e}")
            extract_ok = False

        # Retry loop: stay in awaiting_archive_password until success or max attempts.
        if extract_ok is False and attempts < max_attempts:
            update_data(user_id, "archive_password_attempts", attempts)
            remaining = max_attempts - attempts
            with contextlib.suppress(Exception):
                await message.reply_text(
                    f"❌ **Wrong password** or archive is corrupted.\n"
                    f"You have **{remaining}** attempt(s) left — send the password again or press Cancel."
                )
            raise StopPropagation

        # Either success, or too many wrong attempts — clean up session either way.
        update_data(user_id, "archive_path", None)
        update_data(user_id, "archive_msg_id", None)
        update_data(user_id, "archive_state", None)
        update_data(user_id, "archive_password_attempts", 0)
        if extract_ok is False:
            with contextlib.suppress(Exception):
                await message.reply_text(
                    "🚫 Too many failed attempts. Cancelling this archive."
                )
            clear_session(user_id)
        else:
            set_state(user_id, orig_state)

        raise StopPropagation

    raise ContinuePropagation

async def process_extracted_archive(client, user_id, archive_path, msg, state, password=None):
    await msg.edit_text("📦 **Extracting Archive...**\n\nPlease wait.")

    extract_dir = f"{archive_path}_extracted"
    success = await extract_archive(archive_path, extract_dir, password)

    if not success:
        # Don't delete the archive here: caller may want to retry the password.
        with contextlib.suppress(Exception):
            await msg.edit_text(
                "❌ **Extraction Failed!**\n\n"
                "The archive might be corrupted or the password was incorrect. "
                "Send the password again to retry, or press Cancel."
            )
        return False

    valid_exts = [".mkv", ".mp4", ".avi", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".srt", ".ass", ".vtt", ".mp3", ".flac", ".m4a", ".wav"]
    extracted_files = []

    for root, _dirs, files in os.walk(extract_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in valid_exts:
                extracted_files.append(os.path.join(root, file))

    if not extracted_files:
        await msg.edit_text("⚠️ **No media files found in archive.**\n\nSupported formats: MKV, MP4, AVI, PNG, JPG, etc.")
        if os.path.exists(archive_path):
            os.remove(archive_path)
        import shutil
        shutil.rmtree(extract_dir, ignore_errors=True)
        return True

    await msg.edit_text(f"✅ **Extraction Complete!**\n\nFound {len(extracted_files)} media file(s). Processing...")

    import shutil
    import uuid

    from plugins.process import process_file
    from utils.queue_manager import queue_manager

    for file_path in extracted_files:
        file_name = os.path.basename(file_path)

        metadata = analyze_filename(file_name)
        lang = await db.get_preferred_language(user_id)
        tmdb_data = await auto_match_tmdb(metadata, language=lang)

        if not tmdb_data:
            from utils.tmdb.gate import is_tmdb_available
            if not is_tmdb_available():
                await client.send_message(
                    user_id,
                    f"🔒 **TMDb disabled — skipping `{file_name}`**\n\n"
                    "Auto-detection needs a TMDb API key. Re-upload this file "
                    "via `/start` to rename it in General Mode instead.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Dismiss", callback_data="cancel_rename")]]),
                )
            else:
                await client.send_message(
                    user_id,
                    f"⚠️ **Detection Failed for `{file_name}`**\nSkipping.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Dismiss", callback_data="cancel_rename")]]),
                )
            continue

        quality = metadata["quality"]
        episode = metadata.get("episode", 1) or 1
        season = metadata.get("season", 1) or 1
        lang = metadata.get("language", "en")
        is_subtitle = metadata["is_subtitle"]

        default_dumb_channel = await db.get_default_dumb_channel(user_id)
        if tmdb_data and tmdb_data.get("type") == "movie":
            mov_ch = await db.get_movie_dumb_channel(user_id)
            if mov_ch:
                default_dumb_channel = mov_ch
        elif tmdb_data and tmdb_data.get("type") == "series":
            ser_ch = await db.get_series_dumb_channel(user_id)
            if ser_ch:
                default_dumb_channel = ser_ch

        if user_id not in batch_sessions:
            batch_id = queue_manager.create_batch()
            batch_sessions[user_id] = {"batch_id": batch_id, "items": []}
            bmsg = await client.send_message(user_id, "⏳ **Sorting Files...**\nPlease wait a moment.")
            batch_status_msgs[user_id] = bmsg

        old_task = batch_tasks.pop(user_id, None)
        if old_task:
            old_task.cancel()

        is_priority = False
        has_batch_pro = False
        if Config.PUBLIC_MODE:
            user_doc = await db.get_user(user_id)
            if user_doc and user_doc.get("is_premium"):
                plan_name = user_doc.get("premium_plan", "standard")
                config = await db.get_public_config()
                if config.get("premium_system_enabled", False):
                    plan_settings = config.get(f"premium_{plan_name}", {})
                    plan_features = plan_settings.get("features", {})
                    is_priority = plan_features.get("priority_queue", False)
                    global_toggles = await db.get_feature_toggles()
                    has_batch_pro = global_toggles.get("batch_processing_pro", True) and plan_features.get("batch_processing_pro", False)
        else:
            global_toggles = await db.get_feature_toggles()
            has_batch_pro = global_toggles.get("batch_processing_pro", True)

        batch_id = batch_sessions[user_id]["batch_id"]
        item_id = str(uuid.uuid4())

        quality_priority = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}
        is_series = tmdb_data and tmdb_data.get("type") == "series"
        sort_key = ((0, season, episode[0] if isinstance(episode, list) else episode) if is_series else (1, quality_priority.get(quality, 4), 0))
        display_name = f"S{season:02d}{format_episode_str(episode)}" if is_series else f"{quality}"

        from pyrogram.types import Message
        class DummyMessage:
            def __init__(self, original_msg):
                self.id = original_msg.id + random.randint(1000, 999999)
                self.chat = original_msg.chat
                self.from_user = original_msg.from_user
                self.document = None
                self.video = None
                self.audio = None
                self.photo = None

            async def reply_text(self, *args, **kwargs):
                kwargs.pop("quote", None)
                return await client.send_message(self.chat.id, *args, **kwargs)

            async def delete(self):
                pass

        dummy_msg = DummyMessage(msg)

        queue_manager.add_to_batch(batch_id, item_id, sort_key, display_name, dummy_msg.id, is_priority=is_priority)

        data = {
            "file_message": dummy_msg,
            "file_chat_id": dummy_msg.chat.id,
            "file_message_id": dummy_msg.id,
            "local_file_path": file_path,
            "original_name": file_name,
            "quality": quality,
            "episode": episode,
            "season": season,
            "language": lang,
            "tmdb_id": tmdb_data.get("tmdb_id") if tmdb_data else None,
            "title": tmdb_data.get("title") if tmdb_data else None,
            "year": tmdb_data.get("year") if tmdb_data else None,
            "poster": tmdb_data.get("poster") if tmdb_data else None,
            "type": tmdb_data.get("type") if tmdb_data else None,
            "is_subtitle": is_subtitle,
            "is_auto": True,
            "dumb_channel": default_dumb_channel,
            "batch_id": batch_id,
            "item_id": item_id,
            "extract_dir": extract_dir,
            "specials": metadata.get("specials", []),
            "codec": metadata.get("codec", ""),
            "audio": metadata.get("audio", ""),
            "has_batch_pro": has_batch_pro,
        }

        batch_sessions[user_id]["items"].append({"message": dummy_msg, "data": data})

    if os.path.exists(archive_path):
        os.remove(archive_path)

    async def wait_and_process():
        try:
            delay = 1.0 if is_priority else (3.0 if has_batch_pro else 5.0)
            await asyncio.sleep(delay)
            if batch_tasks.get(user_id) == asyncio.current_task():
                batch_tasks.pop(user_id, None)
            await process_batch(client, user_id)
        except asyncio.CancelledError:
            pass

    if user_id in batch_sessions and batch_sessions[user_id]["items"]:
        batch_tasks[user_id] = asyncio.create_task(wait_and_process())
    else:

        import shutil
        shutil.rmtree(extract_dir, ignore_errors=True)

    return True

async def handle_auto_detection(client, message):
    if message.photo:
        file_name = f"image_{message.id}.jpg"
    else:
        file_name = (
            message.document.file_name if message.document else message.video.file_name
        )

    if not file_name:
        file_name = "unknown_file.bin"

    if is_archive(file_name):
        await handle_archive_upload(client, message, message.from_user.id, file_name, None)
        return

    user_id = message.from_user.id
    metadata = analyze_filename(file_name)
    lang = await db.get_preferred_language(user_id)
    tmdb_data = await auto_match_tmdb(metadata, language=lang)

    if not tmdb_data:
        from utils.tmdb.gate import is_tmdb_available
        if not is_tmdb_available():
            await message.reply_text(
                "🔒 **TMDb disabled — use General Mode**\n\n"
                f"Auto-detection needs a TMDb API key, which the bot owner hasn't "
                f"configured. Send `{file_name}` via `/start` to rename it "
                "manually; file conversion, MyFiles, and YouTube tools keep "
                "working unchanged.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
                ),
            )
        else:
            await message.reply_text(
                f"⚠️ **Detection Failed**\n\nCould not automatically match `{file_name}` with TMDb.\n"
                "Please use /start to rename manually.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
                ),
            )
        return

    is_subtitle = metadata["is_subtitle"]

    quality = metadata["quality"]
    episode = metadata.get("episode", 1) or 1
    season = metadata.get("season", 1) or 1
    media_lang = metadata.get("language", "en")

    default_dumb_channel = await db.get_default_dumb_channel(user_id)
    if tmdb_data and tmdb_data.get("type") == "movie":
        mov_ch = await db.get_movie_dumb_channel(user_id)
        if mov_ch:
            default_dumb_channel = mov_ch
    elif tmdb_data and tmdb_data.get("type") == "series":
        ser_ch = await db.get_series_dumb_channel(user_id)
        if ser_ch:
            default_dumb_channel = ser_ch

    is_priority = False
    has_batch_pro = False
    if Config.PUBLIC_MODE:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                plan_features = plan_settings.get("features", {})
                is_priority = plan_features.get("priority_queue", False)
                global_toggles = await db.get_feature_toggles()
                has_batch_pro = global_toggles.get("batch_processing_pro", True) and plan_features.get("batch_processing_pro", False)
    else:
        global_toggles = await db.get_feature_toggles()
        has_batch_pro = global_toggles.get("batch_processing_pro", True)

    if user_id not in batch_sessions:
        batch_id = queue_manager.create_batch()
        batch_sessions[user_id] = {"batch_id": batch_id, "items": []}
        msg = await message.reply_text(
            "⏳ **Sorting Files...**\nPlease wait a moment.", quote=True
        )
        batch_status_msgs[user_id] = msg

    old_task = batch_tasks.pop(user_id, None)
    if old_task:
        old_task.cancel()

    if user_id not in batch_sessions:
        return

    batch_id = batch_sessions[user_id]["batch_id"]
    item_id = str(uuid.uuid4())

    quality_priority = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}
    is_series = tmdb_data and tmdb_data.get("type") == "series"

    sort_key = (
        (0, season, episode[0] if isinstance(episode, list) else episode)
        if is_series
        else (1, quality_priority.get(quality, 4), 0)
    )
    display_name = (
        f"S{season:02d}{format_episode_str(episode)}"
        if is_series
        else f"{quality}"
    )

    queue_manager.add_to_batch(batch_id, item_id, sort_key, display_name, message.id, is_priority=is_priority)

    data = {
        "file_message": message,
        "file_chat_id": message.chat.id,
        "file_message_id": message.id,
        "original_name": file_name,
        "quality": quality,
        "episode": episode,
        "season": season,
        "language": media_lang,
            "tmdb_id": tmdb_data.get("tmdb_id") if tmdb_data else None,
            "title": tmdb_data.get("title") if tmdb_data else None,
            "year": tmdb_data.get("year") if tmdb_data else None,
            "poster": tmdb_data.get("poster") if tmdb_data else None,
            "type": tmdb_data.get("type") if tmdb_data else None,
        "is_subtitle": is_subtitle,
        "is_auto": True,
        "dumb_channel": default_dumb_channel,
        "batch_id": batch_id,
        "item_id": item_id,
        "specials": metadata.get("specials", []),
        "codec": metadata.get("codec", ""),
        "audio": metadata.get("audio", ""),
        "has_batch_pro": has_batch_pro,
    }
    batch_sessions[user_id]["items"].append({"message": message, "data": data})

    async def wait_and_process():
        try:
            delay = 1.0 if is_priority else (3.0 if has_batch_pro else 5.0)
            await asyncio.sleep(delay)
            if batch_tasks.get(user_id) == asyncio.current_task():
                batch_tasks.pop(user_id, None)
            await process_batch(client, user_id)
        except asyncio.CancelledError:
            pass

    batch_tasks[user_id] = asyncio.create_task(wait_and_process())

async def update_auto_detected_message(client, msg_id, user_id):
    if msg_id not in file_sessions:
        return
    fs = file_sessions[msg_id]

    media_type = "TV Show" if fs["type"] == "series" else "Movie"
    if fs["is_subtitle"]:
        media_type += " (Subtitle)"

    text = (
        f"✅ **Detected {media_type}**\n\n"
        f"**Title:** {fs['title']} ({fs['year']})\n"
        f"**File:** `{fs['original_name']}`\n"
    )

    templates = await db.get_filename_templates(user_id)
    template_key = template_key_for(fs["type"], is_subtitle=fs["is_subtitle"])
    template = templates.get(template_key, Config.DEFAULT_FILENAME_TEMPLATES.get(template_key, ""))

    has_specials = "{Specials}" in template
    has_codec = "{Codec}" in template
    has_audio = "{Audio}" in template

    if has_specials and fs.get('specials'):
        specials_str = " | ".join(fs['specials'])
        text += f"**Detected Specials:** `{specials_str}`\n"

    if has_codec and fs.get('codec'):
        text += f"**Detected Codec:** `{fs['codec']}`\n"

    if has_audio and fs.get('audio'):
        text += f"**Detected Audio:** `{fs['audio']}`\n"

    if fs["is_subtitle"]:
        text += f"**Language:** `{fs['language']}`\n"
    else:
        text += f"**Quality:** `{fs['quality']}`\n"

    if fs["type"] == "series":
        text += f"**Season:** `{fs['season']}` | **Episode:** `{format_episode_str(fs['episode'])}`\n"

    buttons = []
    buttons.append([InlineKeyboardButton("✅ Accept", callback_data=f"confirm_{msg_id}")])

    dynamic_buttons = []
    dynamic_buttons.append(InlineKeyboardButton("Change Type", callback_data=f"change_type_{msg_id}"))

    if fs["type"] == "series":
        dynamic_buttons.append(InlineKeyboardButton("Change Show", callback_data=f"change_tmdb_{msg_id}"))
        dynamic_buttons.append(InlineKeyboardButton("S/E", callback_data=f"change_se_{msg_id}"))
    else:
        dynamic_buttons.append(InlineKeyboardButton("Change Movie", callback_data=f"change_tmdb_{msg_id}"))

    if not fs["is_subtitle"]:
        dynamic_buttons.append(InlineKeyboardButton("Quality", callback_data=f"qual_menu_{msg_id}"))

    if has_codec:
        dynamic_buttons.append(InlineKeyboardButton("📼 Change Codec", callback_data=f"ch_codec_{msg_id}"))
    if has_specials:
        dynamic_buttons.append(InlineKeyboardButton("🎬 Change Specials", callback_data=f"ch_specials_{msg_id}"))
    if has_audio:
        dynamic_buttons.append(InlineKeyboardButton("🔊 Change Audio", callback_data=f"ch_audio_{msg_id}"))

    current_row = []
    for btn in dynamic_buttons:
        current_row.append(btn)
        if len(current_row) == 2:
            buttons.append(current_row)
            current_row = []
    if current_row:
        buttons.append(current_row)

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_file_{msg_id}")])

    with contextlib.suppress(MessageNotModified):
        await client.edit_message_text(
            chat_id=user_id,
            message_id=msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

async def update_confirmation_message(client, msg_id, user_id):
    if msg_id not in file_sessions:
        return

    fs = file_sessions[msg_id]

    if fs.get("is_auto"):
        await update_auto_detected_message(client, msg_id, user_id)
        return

    sd = get_data(user_id)
    is_sub = sd.get("is_subtitle")
    media_type = sd.get("type")

    text = f"📄 **File:** `{fs['original_name']}`\n\n"

    templates = await db.get_filename_templates(user_id)
    template_key = template_key_for(media_type, is_subtitle=is_sub)
    template = templates.get(template_key, Config.DEFAULT_FILENAME_TEMPLATES.get(template_key, ""))

    has_specials = "{Specials}" in template
    has_codec = "{Codec}" in template
    has_audio = "{Audio}" in template

    if has_specials and fs.get('specials'):
        specials_str = " | ".join(fs['specials'])
        text += f"**Detected Specials:** `{specials_str}`\n"

    if has_codec and fs.get('codec'):
        text += f"**Detected Codec:** `{fs['codec']}`\n"

    if has_audio and fs.get('audio'):
        text += f"**Detected Audio:** `{fs['audio']}`\n"

    if is_sub:
        text += f"**Language:** `{fs.get('language')}`\n"
    else:
        text += f"**Detected Quality:** `{fs['quality']}`\n"

    if media_type == "series":
        text += f"**Season:** `{fs['season']}` | **Episode:** `{format_episode_str(fs['episode'])}`\n"

    buttons = []
    row1 = [InlineKeyboardButton("✅ Accept", callback_data=f"confirm_{msg_id}")]
    row2 = []

    if not is_sub:
        row2.append(
            InlineKeyboardButton("Change Quality", callback_data=f"qual_menu_{msg_id}")
        )

    if media_type == "series":
        row2.append(
            InlineKeyboardButton("Change Episode", callback_data=f"ep_change_{msg_id}")
        )
        row2.append(
            InlineKeyboardButton(
                "Change Season", callback_data=f"season_change_{msg_id}"
            )
        )

    row3 = []
    if has_codec:
        row3.append(InlineKeyboardButton("📼 Change Codec", callback_data=f"ch_codec_{msg_id}"))
    if has_specials:
        row3.append(InlineKeyboardButton("🎬 Change Specials", callback_data=f"ch_specials_{msg_id}"))
    if has_audio:
        row3.append(InlineKeyboardButton("🔊 Change Audio", callback_data=f"ch_audio_{msg_id}"))

    buttons.append(row1)
    if row2:
        buttons.append(row2)
    if row3:
        buttons.append(row3)

    buttons.append(
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_file_{msg_id}")]
    )

    with contextlib.suppress(MessageNotModified):
        await client.edit_message_text(
            chat_id=user_id,
            message_id=msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

@Client.on_callback_query(filters.regex(r"^confirm_(\d+)$"))
async def handle_confirm(client, callback_query):
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions.pop(msg_id)
    _file_session_timestamps.pop(msg_id, None)

    # Cancel expiry timer
    task = _expiry_warnings.pop(user_id, None)
    if task:
        task.cancel()

    if fs.get("is_auto"):
        full_data = fs
    else:
        sd = get_data(user_id)
        if not sd or not sd.get("type"):
            await callback_query.message.edit_text("Session expired. Please start a new session.")
            return
        full_data = sd.copy()
        full_data.update(fs)

    await process_file(client, callback_query.message, full_data)

@Client.on_callback_query(filters.regex(r"^qual_menu_(\d+)$"))
async def handle_quality_menu(client, callback_query):
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "Select Quality:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "480p", callback_data=f"set_qual_{msg_id}_480p"
                        ),
                        InlineKeyboardButton(
                            "720p", callback_data=f"set_qual_{msg_id}_720p"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "1080p", callback_data=f"set_qual_{msg_id}_1080p"
                        ),
                        InlineKeyboardButton(
                            "2160p", callback_data=f"set_qual_{msg_id}_2160p"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "← Back", callback_data=f"back_confirm_{msg_id}"
                        )
                    ],
                ]
            ),
        )

@Client.on_callback_query(filters.regex(r"^set_qual_(\d+)_(.+)$"))
async def handle_set_quality(client, callback_query):
    await callback_query.answer()
    data = callback_query.data.split("_")
    msg_id = int(data[2])
    qual = data[3]

    if msg_id in file_sessions:
        file_sessions[msg_id]["quality"] = qual
        await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^back_confirm_(\d+)$"))
async def handle_back_confirm(client, callback_query):
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^ep_change_(\d+)$"))
async def handle_ep_change_prompt(client, callback_query):
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    set_state(user_id, f"awaiting_episode_correction_{msg_id}")
    from pyrogram.errors import FloodWait
    try:
        await callback_query.message.edit_text(
            "**Enter Episode Number:**\n" "Send a number (e.g. 5)",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Cancel", callback_data=f"back_confirm_{msg_id}"
                        )
                    ]
                ]
            ),
        )
    except MessageNotModified:
        pass
    except FloodWait as e:
        logger.warning(f"FloodWait in handle_ep_change_prompt: sleeping for {e.value}s")
        await asyncio.sleep(e.value + 1)
        with contextlib.suppress(Exception):
            await callback_query.message.edit_text(
                "**Enter Episode Number:**\n" "Send a number (e.g. 5)",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data=f"back_confirm_{msg_id}"
                            )
                        ]
                    ]
                ),
            )
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^season_change_(\d+)$"))
async def handle_season_change_prompt(client, callback_query):
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    set_state(user_id, f"awaiting_season_correction_{msg_id}")
    from pyrogram.errors import FloodWait
    try:
        await callback_query.message.edit_text(
            "**Enter Season Number:**\n" "Send a number (e.g. 2)",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Cancel", callback_data=f"back_confirm_{msg_id}"
                        )
                    ]
                ]
            ),
        )
    except MessageNotModified:
        pass
    except FloodWait as e:
        logger.warning(f"FloodWait in handle_season_change_prompt: sleeping for {e.value}s")
        await asyncio.sleep(e.value + 1)
        with contextlib.suppress(Exception):
            await callback_query.message.edit_text(
                "**Enter Season Number:**\n" "Send a number (e.g. 2)",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "❌ Cancel", callback_data=f"back_confirm_{msg_id}"
                            )
                        ]
                    ]
                ),
            )
    except Exception as e:
        logger.warning(f"handle_season_change_prompt edit failed: {e}")

@Client.on_callback_query(filters.regex(r"^cancel_file_(\d+)$"))
async def handle_file_cancel(client, callback_query):
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])

    if msg_id in file_sessions:
        fs = file_sessions.pop(msg_id)
        _file_session_timestamps.pop(msg_id, None)
        if "file_message" in fs:
            media = fs["file_message"].document or fs["file_message"].video or fs["file_message"].audio or fs["file_message"].photo
            file_size = getattr(media, "file_size", 0) if media else 0
            if file_size > 0:
                await db.release_quota(callback_query.from_user.id, file_size)

    await callback_query.message.delete()

@Client.on_callback_query(filters.regex(r"^change_type_(\d+)$"))
async def handle_change_type(client, callback_query):
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        return

    fs = file_sessions[msg_id]
    current_type = fs["type"]
    is_sub = fs["is_subtitle"]

    if not is_sub and current_type == "movie":
        fs["type"] = "series"
        fs["is_subtitle"] = False
    elif not is_sub and current_type == "series":
        fs["type"] = "movie"
        fs["is_subtitle"] = True
        fs["language"] = "en"
    elif is_sub and current_type == "movie":
        fs["type"] = "series"
        fs["is_subtitle"] = True
    elif is_sub and current_type == "series":
        fs["type"] = "movie"
        fs["is_subtitle"] = False

    await update_auto_detected_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^change_tmdb_(\d+)$"))
async def handle_change_tmdb_init(client, callback_query):
    from utils.tmdb.gate import ensure_tmdb

    if not await ensure_tmdb(client, callback_query, feature="Change TMDb match"):
        return

    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    set_state(user_id, f"awaiting_search_correction_{msg_id}")
    fs = file_sessions[msg_id]
    mtype = fs["type"]

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            f"🔍 **Search {mtype.capitalize()}**\n\n" "Please enter the correct name:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "← Back", callback_data=f"back_confirm_{msg_id}"
                        )
                    ]
                ]
            ),
        )

@Client.on_callback_query(filters.regex(r"^change_se_(\d+)$"))
async def handle_change_se_menu(client, callback_query):
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "Select what to change:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Change Season", callback_data=f"season_change_{msg_id}"
                        ),
                        InlineKeyboardButton(
                            "Change Episode", callback_data=f"ep_change_{msg_id}"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "← Back", callback_data=f"back_confirm_{msg_id}"
                        )
                    ],
                ]
            ),
        )

@Client.on_callback_query(filters.regex(r"^correct_tmdb_(\d+)_(\d+)$"))
async def handle_correct_tmdb_selection(client, callback_query):
    from utils.tmdb.gate import ensure_tmdb

    if not await ensure_tmdb(client, callback_query, feature="Correct TMDb match"):
        return

    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")
    msg_id = int(data[2])
    tmdb_id = data[3]

    if msg_id not in file_sessions:
        return
    fs = file_sessions[msg_id]

    try:
        lang = await db.get_preferred_language(user_id)
        details = await tmdb.get_details(fs["type"], tmdb_id, language=lang)
    except Exception:
        return

    title = details.get("title") if fs["type"] == "movie" else details.get("name")
    year = (
        details.get("release_date")
        if fs["type"] == "movie"
        else details.get("first_air_date", "")
    )[:4]
    poster = (
        f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}"
        if details.get("poster_path")
        else None
    )

    fs["tmdb_id"] = tmdb_id
    fs["title"] = title
    fs["year"] = year
    fs["poster"] = poster

    set_state(callback_query.from_user.id, None)

    await callback_query.message.delete()
    await update_auto_detected_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^ch_codec_") & auth_filter)
async def handle_change_codec(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current = fs.get("codec", "")
    locked = bool(fs.get("codec_locked"))

    codecs = ["x264", "x265", "HEVC"]
    buttons = []

    row = []
    for c in codecs:
        text = f"✅ {c}" if c == current else c
        row.append(InlineKeyboardButton(text, callback_data=f"set_codec_{c}_{msg_id}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    none_text = "🚫 None (locked)" if locked else ("✅ None" if not current else "None")
    buttons.append([InlineKeyboardButton(none_text, callback_data=f"set_codec_none_{msg_id}")])

    buttons.append([InlineKeyboardButton("← Back", callback_data=f"back_confirm_{msg_id}")])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "📼 **Select Codec:**\nChoose a codec for the template. "
            "Pick **None** to lock — auto-fill won't overwrite it.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

@Client.on_callback_query(filters.regex(r"^set_codec_") & auth_filter)
async def handle_set_codec(client, callback_query):
    parts = callback_query.data.split("_")
    codec = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    if codec == "none":
        fs["codec"] = ""
        fs["codec_locked"] = True
    else:
        fs["codec"] = codec
        fs["codec_locked"] = False

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^ch_audio_") & auth_filter)
async def handle_change_audio(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current = fs.get("audio", "")
    locked = bool(fs.get("audio_locked"))

    audios = ["DUAL", "DL", "Dubbed", "Multi", "MicDub", "LineDub", "DTS", "AC3", "Atmos"]
    buttons = []

    row = []
    for a in audios:
        text = f"✅ {a}" if a == current else a
        row.append(InlineKeyboardButton(text, callback_data=f"set_audio_{a}_{msg_id}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    none_text = "🚫 None (locked)" if locked else ("✅ None" if not current else "None")
    buttons.append([InlineKeyboardButton(none_text, callback_data=f"set_audio_none_{msg_id}")])
    buttons.append([InlineKeyboardButton("← Back", callback_data=f"back_confirm_{msg_id}")])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "🔊 **Select Audio:**\nChoose an audio tag for the template. "
            "Pick **None** to lock — auto-fill won't overwrite it even if Dual/Multi streams are detected.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

@Client.on_callback_query(filters.regex(r"^set_audio_") & auth_filter)
async def handle_set_audio(client, callback_query):
    parts = callback_query.data.split("_")
    audio = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    if audio == "none":
        fs["audio"] = ""
        fs["audio_locked"] = True
    else:
        fs["audio"] = audio
        fs["audio_locked"] = False

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^ch_specials_") & auth_filter)
async def handle_change_specials(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current = fs.get("specials", [])
    locked = bool(fs.get("specials_locked"))

    specials_options = ["BluRay", "WEB-DL", "WEBRip", "HDR", "REMUX", "PROPER", "REPACK", "UNCUT", "BDRip"]
    buttons = []

    row = []
    for s in specials_options:
        text = f"✅ {s}" if s in current else s
        row.append(InlineKeyboardButton(text, callback_data=f"toggle_spc_{s}_{msg_id}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    lock_label = "🚫 None (locked)" if locked else "🚫 None (lock)"
    buttons.append([
        InlineKeyboardButton("❌ Clear All", callback_data=f"clear_spc_{msg_id}"),
        InlineKeyboardButton(lock_label, callback_data=f"lock_spc_{msg_id}"),
    ])
    buttons.append([InlineKeyboardButton("✅ Done", callback_data=f"back_confirm_{msg_id}")])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "🎬 **Select Specials:**\nToggle specials for the template (multiple allowed). "
            "Use **🚫 None (lock)** to prevent auto-fill from populating this field.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

@Client.on_callback_query(filters.regex(r"^toggle_spc_") & auth_filter)
async def handle_toggle_specials(client, callback_query):
    parts = callback_query.data.split("_")
    special = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current = fs.get("specials", [])

    if special in current:
        current.remove(special)
    else:
        current.append(special)

    fs["specials"] = current
    # Toggling any special means user is actively choosing — release lock.
    fs["specials_locked"] = False
    locked = False

    specials_options = ["BluRay", "WEB-DL", "WEBRip", "HDR", "REMUX", "PROPER", "REPACK", "UNCUT", "BDRip"]
    buttons = []
    row = []
    for s in specials_options:
        text = f"✅ {s}" if s in current else s
        row.append(InlineKeyboardButton(text, callback_data=f"toggle_spc_{s}_{msg_id}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    lock_label = "🚫 None (locked)" if locked else "🚫 None (lock)"
    buttons.append([
        InlineKeyboardButton("❌ Clear All", callback_data=f"clear_spc_{msg_id}"),
        InlineKeyboardButton(lock_label, callback_data=f"lock_spc_{msg_id}"),
    ])
    buttons.append([InlineKeyboardButton("✅ Done", callback_data=f"back_confirm_{msg_id}")])

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "🎬 **Select Specials:**\nToggle specials for the template (multiple allowed). "
            "Use **🚫 None (lock)** to prevent auto-fill from populating this field.",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

@Client.on_callback_query(filters.regex(r"^clear_spc_") & auth_filter)
async def handle_clear_specials(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    file_sessions[msg_id]["specials"] = []

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^lock_spc_") & auth_filter)
async def handle_lock_specials(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    fs["specials"] = []
    fs["specials_locked"] = True
    await callback_query.answer("🚫 Specials locked — auto-fill will skip this.", show_alert=False)
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^edit_system_filename$"))
async def edit_system_filename_template(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    set_state(user_id, "awaiting_system_filename")
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "⚙️ **System Filename Template**\n\n"
            "How should the bot save files internally to your MyFiles database?\n"
            "You can use these variables:\n"
            "`{title}` - The movie or series name\n"
            "`{year}` - The release year\n"
            "`{season}` - The season number (e.g. 01)\n"
            "`{episode}` - The episode number (e.g. 01)\n"
            "`{series_name}` - Alias for title, useful for series.\n\n"
            "**Examples:**\n"
            "`{title} ({year})` -> Inception (2010)\n"
            "`{series_name} S{season}E{episode}` -> The Rookie S01E01\n\n"
            "Please type your new template below:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            )
        )

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
