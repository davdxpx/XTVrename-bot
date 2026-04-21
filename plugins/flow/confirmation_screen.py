# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Auto-detection, confirmation screen, and change-detail menus.

This is where the user sees what the bot detected for a given file
and either accepts it (confirm_) or tweaks one field via a change
menu (qual_menu_, ep_change_, season_change_, change_type_,
change_tmdb_, change_se_, correct_tmdb_).

Two rendering entry points drive the UI:

 * ``update_auto_detected_message`` — for files that went through
   TMDb auto-detection; no per-field change buttons beyond the
   Codec/Specials/Audio picker triggers (those live in pickers.py).
 * ``update_confirmation_message`` — the classic "file info +
   Accept/Change" confirm screen the user sees in the manual flow.
"""

import asyncio
import contextlib
import uuid

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Config
from db import db
from plugins.flow.sessions import (
    _expiry_warnings,
    _file_session_timestamps,
    _persist_session_to_db,
    batch_sessions,
    batch_status_msgs,
    batch_tasks,
    file_sessions,
    format_episode_str,
)
from utils.media.archive import is_archive
from utils.media.detect import analyze_filename, auto_match_tmdb, template_key_for
from utils.queue_manager import queue_manager
from utils.state import clear_session, get_data, get_state, set_state, update_data
from utils.tasks import spawn as _spawn_task
from utils.telegram.log import get_logger
from utils.tmdb import tmdb

logger = get_logger("plugins.flow.confirmation_screen")


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
        from plugins.flow.archive import handle_archive_upload
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
        # Late import for process_batch: upload module also depends on
        # our update_confirmation_message, so we dodge the cycle.
        from plugins.flow.upload import process_batch
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
    from plugins.process import process_file

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
    from pyrogram.errors import FloodWait
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    set_state(user_id, f"awaiting_episode_correction_{msg_id}")
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
    from pyrogram.errors import FloodWait
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    set_state(user_id, f"awaiting_season_correction_{msg_id}")
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
