from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils.tmdb import tmdb
from utils.auth import auth_filter
from utils.state import set_state, get_state, update_data, get_data, clear_session
from plugins.process import process_file
from utils.detect import analyze_filename, auto_match_tmdb
from config import Config
from utils.log import get_logger
import asyncio
import re

logger = get_logger("plugins.flow")
logger.info("Loading plugins.flow...")

# Store for per-file processing data
file_sessions = {}

@Client.on_callback_query(filters.regex(r"^start_renaming$"))
async def handle_start_renaming(client, callback_query):
    user_id = callback_query.from_user.id
    logger.info(f"Start renaming flow for {user_id}")
    clear_session(user_id) # Reset
    set_state(user_id, "awaiting_type")

    await callback_query.message.edit_text(
        "**Select Media Type**\n\n"
        "What are you renaming today?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Movie", callback_data="type_movie"),
             InlineKeyboardButton("📺 Series", callback_data="type_series")],
            [InlineKeyboardButton("📹 Personal Video", callback_data="type_personal_video")],
            [InlineKeyboardButton("📸 Personal Photo", callback_data="type_personal_photo")],
            [InlineKeyboardButton("📁 Personal File", callback_data="type_personal_file")],
            [InlineKeyboardButton("📝 Subtitles", callback_data="type_subtitles")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^type_personal_(video|photo|file)$"))
async def handle_type_personal(client, callback_query):
    user_id = callback_query.from_user.id
    personal_type = callback_query.data.split("_")[2]
    logger.info(f"User {user_id} selected personal type: {personal_type}")

    # For personal files, we store type as "movie" to use standard, non-episodic filename logic
    update_data(user_id, "type", "movie")
    update_data(user_id, "tmdb_id", None) # No TMDb
    update_data(user_id, "personal_type", personal_type) # Track if it's photo/video/file

    set_state(user_id, "awaiting_manual_title")

    if personal_type == "video":
        label = "Video"
    elif personal_type == "photo":
        label = "Photo"
    else:
        label = "File"

    await callback_query.message.edit_text(
        f"✍️ **Personal {label} Details**\n\n"
        "Please enter the name you want to use for this file.\n"
        "Format: `Title (Year)` or just `Title`\n"
        "Example: `Family Vacation Hawaii (2024)`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
    )

@Client.on_callback_query(filters.regex(r"^type_(movie|series)$"))
async def handle_type_selection(client, callback_query):
    user_id = callback_query.from_user.id
    media_type = callback_query.data.split("_")[1]
    logger.info(f"User {user_id} selected type: {media_type}")

    update_data(user_id, "type", media_type)
    set_state(user_id, f"awaiting_search_{media_type}")

    await callback_query.message.edit_text(
        f"🔍 **Search {media_type.capitalize()}**\n\n"
        f"Please enter the name of the {media_type} (e.g. 'Zootopia' or 'The Rookie').",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
    )

@Client.on_callback_query(filters.regex(r"^type_subtitles$"))
async def handle_type_subtitles(client, callback_query):
    await callback_query.message.edit_text(
        "**Select Subtitle Type**\n\n"
        "Is this for a Movie or a Series?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Movie", callback_data="type_sub_movie"),
             InlineKeyboardButton("📺 Series", callback_data="type_sub_series")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^type_sub_(movie|series)$"))
async def handle_subtitle_type_selection(client, callback_query):
    user_id = callback_query.from_user.id
    media_type = callback_query.data.split("_")[2]
    logger.info(f"User {user_id} selected subtitle type: {media_type}")

    update_data(user_id, "type", media_type)
    update_data(user_id, "is_subtitle", True)
    set_state(user_id, f"awaiting_search_{media_type}")

    await callback_query.message.edit_text(
        f"🔍 **Search {media_type.capitalize()} (Subtitles)**\n\n"
        f"Please enter the name of the {media_type}.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
    )

async def manual_title_handler(client, message):
    user_id = message.from_user.id
    text = message.text.strip()

    match = re.search(r"^(.*?)(?:\s*\((\d{4})\))?$", text)
    title = match.group(1).strip() if match else text
    year = match.group(2) if match and match.group(2) else "Unknown"

    update_data(user_id, "title", title)
    update_data(user_id, "year", year)
    update_data(user_id, "poster", None) # No poster for manual entry

    data = get_data(user_id)
    media_type = data.get("type")

    if media_type == "series":
        set_state(user_id, "awaiting_season")
        await message.reply_text("📺 **Series:** What Season is this? (e.g., `1` or `01`)",
                                 reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]))
    elif data.get("personal_type") == "photo":
        set_state(user_id, "awaiting_send_as")
        await message.reply_text(
            f"📸 **Photo Selected**\n\n**Title:** {title}\n**Year:** {year}\n\n"
            "How would you like to receive the output?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 Send as Photo", callback_data="send_as_photo")],
                [InlineKeyboardButton("📁 Send as Document (File)", callback_data="send_as_document")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
            ])
        )
    else:
        set_state(user_id, "awaiting_file_upload")
        type_str = "photo/file" if data.get("personal_type") else "file"
        await message.reply_text(
            f"✅ **Ready!**\n\n**Title:** {title}\n**Year:** {year}\n\n"
            f"Now, **send me the {type_str}** you want to rename.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
        )

async def search_handler(client, message, media_type):
    query = message.text
    logger.info(f"Searching {media_type} for: {query}")
    msg = await message.reply_text(f"🔍 Searching for '{query}'...")

    try:
        if media_type == "movie":
            results = await tmdb.search_movie(query)
        else:
            results = await tmdb.search_tv(query)
    except Exception as e:
        logger.error(f"TMDb search failed: {e}")
        await msg.edit_text(f"❌ Search Error: {e}")
        return

    if not results:
        await msg.edit_text(
            "❌ **No results found.**\n\n"
            "This could be a personal file, home video, or a regional/unknown series not listed on TMDb.\n"
            "You can enter the details manually by clicking below.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✍️ Skip / Enter Manually", callback_data="manual_entry")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
            ])
        )
        return

    buttons = []
    for item in results:
        buttons.append([InlineKeyboardButton(
            f"{item['title']} ({item['year']})",
            callback_data=f"sel_tmdb_{media_type}_{item['id']}"
        )])

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")])

    await msg.edit_text(
        f"**Select {media_type.capitalize()}**\n\n"
        f"Found {len(results)} results for '{query}':",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def season_handler(client, message):
    user_id = message.from_user.id
    text = message.text

    if not text.isdigit():
        await message.reply_text("Please enter a valid number for the season.")
        return

    season = int(text)
    update_data(user_id, "season", season)

    data = get_data(user_id)
    title = data.get("title")

    if data.get("is_subtitle"):
        set_state(user_id, "awaiting_episode")
        await message.reply_text(
            f"**Season {season} Confirmed** for {title}.\n\n"
            "Please enter the **Episode Number** (e.g. 1, 2, ...):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
        )
        return

    set_state(user_id, "awaiting_file_upload")

    await message.reply_text(
        f"**Season {season} Confirmed** for {title}.\n\n"
        "Please **forward the file(s)** you want to rename.\n"
        "For series, I will auto-detect the episode number from the filename (e.g. S01E05).",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
    )

async def episode_handler(client, message):
    user_id = message.from_user.id
    text = message.text

    if not text.isdigit():
        await message.reply_text("Please enter a valid number for the episode.")
        return

    episode = int(text)
    update_data(user_id, "episode", episode)

    await initiate_language_selection(client, user_id, message)

# Group 2 - Runs AFTER start commands
# Ignore anything starting with / to avoid catching commands
@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=2)
async def handle_text_input(client, message):
    user_id = message.from_user.id

    if not (user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS):
        return

    state = get_state(user_id)
    logger.info(f"Text input from {user_id}: {message.text} | State: {state}")

    if not state:
        return

    if state == "awaiting_search_movie":
        await search_handler(client, message, "movie")
    elif state == "awaiting_search_series":
        await search_handler(client, message, "series")
    elif state == "awaiting_manual_title":
        await manual_title_handler(client, message)
    elif state == "awaiting_season":
        await season_handler(client, message)

    elif state == "awaiting_episode":
        await episode_handler(client, message)

    elif state == "awaiting_language_custom":
        lang = message.text.strip().lower()
        if len(lang) > 10 or not lang.replace("-", "").isalnum():
             await message.reply_text("Invalid language code. Keep it short (e.g. 'en', 'pt-br').")
             return

        update_data(user_id, "language", lang)
        set_state(user_id, "awaiting_file_upload")
        await message.reply_text(
            f"**Language Selected:** `{lang}`\n\n"
            "Please **forward the subtitle file(s)** (.srt, .ass, etc.).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Done / Cancel", callback_data="cancel_rename")]])
        )

    elif state.startswith("awaiting_episode_correction_"):
        msg_id = int(state.split("_")[-1])
        if msg_id in file_sessions:
            if message.text.isdigit():
                file_sessions[msg_id]["episode"] = int(message.text)
                set_state(user_id, "awaiting_file_upload")
                await update_confirmation_message(client, msg_id, user_id)
                await message.delete()
            else:
                await message.reply_text("Invalid number. Try again.")

    elif state.startswith("awaiting_season_correction_"):
        msg_id = int(state.split("_")[-1])
        if msg_id in file_sessions:
            if message.text.isdigit():
                file_sessions[msg_id]["season"] = int(message.text)
                set_state(user_id, "awaiting_file_upload")
                await update_confirmation_message(client, msg_id, user_id)
                await message.delete()
            else:
                await message.reply_text("Invalid number. Try again.")

    elif state.startswith("awaiting_search_correction_"):
        msg_id = int(state.split("_")[-1])
        if msg_id in file_sessions:
            fs = file_sessions[msg_id]
            query = message.text
            mtype = fs['type']

            msg = await message.reply_text(f"🔍 Searching {mtype} for '{query}'...")

            try:
                if mtype == "series":
                    results = await tmdb.search_tv(query)
                else:
                    results = await tmdb.search_movie(query)
            except Exception as e:
                await msg.edit_text(f"Error: {e}")
                return

            if not results:
                await msg.edit_text("No results found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data=f"back_confirm_{msg_id}")]]))
                return

            buttons = []
            for item in results:
                buttons.append([InlineKeyboardButton(
                    f"{item['title']} ({item['year']})",
                    callback_data=f"correct_tmdb_{msg_id}_{item['id']}"
                )])
            buttons.append([InlineKeyboardButton("Cancel", callback_data=f"back_confirm_{msg_id}")])

            await msg.edit_text(f"Select correct {mtype}:", reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^manual_entry$"))
async def handle_manual_entry(client, callback_query):
    user_id = callback_query.from_user.id
    logger.info(f"User {user_id} selected manual entry.")

    # Mark as manual entry
    update_data(user_id, "tmdb_id", None)

    media_type = get_data(user_id).get("type", "movie")

    set_state(user_id, "awaiting_manual_title")
    await callback_query.message.edit_text(
        f"✍️ **Manual Entry ({media_type.capitalize()})**\n\n"
        "Please enter the exact title and year you want to use.\n"
        "Format: `Title (Year)`\n"
        "Example: `My Family Vacation (2023)`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
    )

@Client.on_callback_query(filters.regex(r"^send_as_(photo|document)$"))
async def handle_send_as_preference(client, callback_query):
    user_id = callback_query.from_user.id
    pref = callback_query.data.split("_")[2]

    update_data(user_id, "send_as", pref)
    set_state(user_id, "awaiting_file_upload")

    label = "Photo" if pref == "photo" else "Document (File)"
    await callback_query.message.edit_text(
        f"✅ **Preference Saved: {label}**\n\n"
        "Now, **send me the photo** you want to rename.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
    )

@Client.on_callback_query(filters.regex(r"^sel_tmdb_(movie|series)_(\d+)$"))
async def handle_tmdb_selection(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")
    media_type = data[2]
    tmdb_id = data[3]

    try:
        details = await tmdb.get_details(media_type, tmdb_id)
        if not details:
            await callback_query.answer("Error fetching details!", show_alert=True)
            return
    except Exception as e:
        logger.error(f"TMDb details failed: {e}")
        await callback_query.answer("Error fetching details!", show_alert=True)
        return

    title = details.get("title") if media_type == "movie" else details.get("name")
    year = (details.get("release_date") if media_type == "movie" else details.get("first_air_date", ""))[:4]
    poster = f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}" if details.get("poster_path") else None

    update_data(user_id, "tmdb_id", tmdb_id)
    update_data(user_id, "title", title)
    update_data(user_id, "year", year)
    update_data(user_id, "poster", poster)

    if media_type == "series":
        set_state(user_id, "awaiting_season")
        await callback_query.message.edit_text(
            f"**Selected Series:** {title} ({year})\n\n"
            "Please enter the **Season Number** (e.g. 1, 2, ...):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
        )
    else:
        data = get_data(user_id)
        if data.get("is_subtitle"):
            await initiate_language_selection(client, user_id, callback_query.message)
        else:
            set_state(user_id, "awaiting_file_upload")
            await callback_query.message.edit_text(
                f"**Selected Movie:** {title} ({year})\n\n"
                "Please **forward the file(s)** you want to rename.\n"
                "You can forward multiple files.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Done / Cancel", callback_data="cancel_rename")]])
            )

async def initiate_language_selection(client, user_id, message_obj):
    set_state(user_id, "awaiting_language")
    buttons = [
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
         InlineKeyboardButton("🇩🇪 German", callback_data="lang_de")],
        [InlineKeyboardButton("🇫🇷 French", callback_data="lang_fr"),
         InlineKeyboardButton("🇪🇸 Spanish", callback_data="lang_es")],
        [InlineKeyboardButton("🇮🇹 Italian", callback_data="lang_it"),
         InlineKeyboardButton("✍️ Custom", callback_data="lang_custom")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
    ]

    text = "**Select Subtitle Language**\n\nChoose a language or select 'Custom' to type a code (e.g. por, rus)."

    if isinstance(message_obj, str):
        await client.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
    elif hasattr(message_obj, "edit_text"):
        await message_obj.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message_obj.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^lang_"))
async def handle_language_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")[1]

    if data == "custom":
        set_state(user_id, "awaiting_language_custom")
        await callback_query.message.edit_text(
            "✍️ **Enter Custom Language Code**\n\n"
            "Please type the language code (e.g. `por`, `hin`, `jpn`, `pt-br`):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
        )
        return

    update_data(user_id, "language", data)
    set_state(user_id, "awaiting_file_upload")

    await callback_query.message.edit_text(
        f"**Language Selected:** `{data}`\n\n"
        "Please **forward the subtitle file(s)** (.srt, .ass, etc.).",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Done / Cancel", callback_data="cancel_rename")]])
    )

@Client.on_callback_query(filters.regex(r"^cancel_rename$"))
async def handle_cancel(client, callback_query):
    user_id = callback_query.from_user.id
    clear_session(user_id)
    await callback_query.message.edit_text(
        "**Current Task Cancelled** ❌\n\n"
        "Your progress has been cleared.\n"
        "You can simply send me a file anytime to start over, or use the buttons below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Start Renaming Manually", callback_data="start_renaming")],
            [InlineKeyboardButton("📖 Help & Guide", callback_data="help_guide")]
        ])
    )

# --- File Handling ---

@Client.on_message((filters.document | filters.video | filters.photo) & filters.private, group=2)
async def handle_file_upload(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if not (user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS):
        return

    if state != "awaiting_file_upload":
        if state is None:
            await handle_auto_detection(client, message)
        return

    # Existing manual flow processing
    file_name = message.document.file_name if message.document else message.video.file_name
    if not file_name:
        file_name = "unknown.mkv"

    quality = "720p"
    if re.search(r"1080p", file_name, re.IGNORECASE): quality = "1080p"
    elif re.search(r"2160p|4k", file_name, re.IGNORECASE): quality = "2160p"
    elif re.search(r"480p", file_name, re.IGNORECASE): quality = "480p"

    episode = 1
    season = 1
    session_data = get_data(user_id)
    if session_data.get("type") == "series":
        season = session_data.get("season", 1)
        if session_data.get("is_subtitle"):
             episode = session_data.get("episode", 1)
        else:
            match = re.search(r"[sS]?\d{1,2}[eE](\d{1,2})", file_name)
            if match:
                episode = int(match.group(1))
            else:
                match = re.search(r"[eE](\d{1,2})", file_name)
                if match:
                    episode = int(match.group(1))

    msg = await message.reply_text("Processing file...", quote=True)

    # Store language if subtitle
    lang = session_data.get("language", "en") if session_data.get("is_subtitle") else None

    file_sessions[msg.id] = {
        "file_message": message,
        "quality": quality,
        "episode": episode,
        "season": season,
        "original_name": file_name,
        "language": lang
    }

    await update_confirmation_message(client, msg.id, user_id)

async def handle_auto_detection(client, message):
    msg = await message.reply_text("🔍 **Executing Transcoding Matrix...**\nRunning deep scan on filename...", quote=True)

    if message.photo:
        file_name = f"image_{message.id}.jpg"
    else:
        file_name = message.document.file_name if message.document else message.video.file_name

    if not file_name:
        file_name = "unknown_file.bin"

    # Analyze
    metadata = analyze_filename(file_name)
    tmdb_data = await auto_match_tmdb(metadata)

    if not tmdb_data:
        await msg.edit_text(
            f"⚠️ **Detection Failed**\n\nCould not automatically match `{file_name}` with TMDb.\n"
            "Please use /start to rename manually.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
        )
        return

    # Construct session data
    is_subtitle = metadata['is_subtitle']

    # Defaults
    quality = metadata['quality']
    episode = metadata.get('episode', 1) or 1
    season = metadata.get('season', 1) or 1
    lang = metadata.get('language', 'en')

    # Store in file_sessions (including TMDB info, effectively bypassing user session state)
    file_sessions[msg.id] = {
        "file_message": message,
        "original_name": file_name,
        "quality": quality,
        "episode": episode,
        "season": season,
        "language": lang,
        # Auto-detect fields that normally live in user session
        "tmdb_id": tmdb_data['tmdb_id'],
        "title": tmdb_data['title'],
        "year": tmdb_data['year'],
        "poster": tmdb_data['poster'],
        "type": tmdb_data['type'],
        "is_subtitle": is_subtitle,
        "is_auto": True # Flag to know this was auto-detected
    }

    await update_auto_detected_message(client, msg.id, message.from_user.id)

async def update_auto_detected_message(client, msg_id, user_id):
    if msg_id not in file_sessions: return
    fs = file_sessions[msg_id]

    media_type = "TV Show" if fs['type'] == "series" else "Movie"
    if fs['is_subtitle']: media_type += " (Subtitle)"

    text = (
        f"✅ **Detected {media_type}**\n\n"
        f"**Title:** {fs['title']} ({fs['year']})\n"
        f"**File:** `{fs['original_name']}`\n"
    )

    if fs['is_subtitle']:
        text += f"**Language:** `{fs['language']}`\n"
    else:
        text += f"**Quality:** `{fs['quality']}`\n"

    if fs['type'] == "series":
        text += f"**Season:** `{fs['season']}` | **Episode:** `E{fs['episode']:02d}`\n"

    buttons = []

    # Row 1: Accept
    buttons.append([InlineKeyboardButton("✅ Accept", callback_data=f"confirm_{msg_id}")])

    # Row 2: Changes
    row2 = []
    row2.append(InlineKeyboardButton("Change Type", callback_data=f"change_type_{msg_id}")) # Movie <-> Series
    if fs['type'] == "series":
        row2.append(InlineKeyboardButton("Change Show", callback_data=f"change_tmdb_{msg_id}"))
    else:
        row2.append(InlineKeyboardButton("Change Movie", callback_data=f"change_tmdb_{msg_id}"))
    buttons.append(row2)

    # Row 3: More Changes
    row3 = []
    if fs['type'] == "series":
        row3.append(InlineKeyboardButton("S/E", callback_data=f"change_se_{msg_id}")) # Helper menu for S/E
    if not fs['is_subtitle']:
        row3.append(InlineKeyboardButton("Quality", callback_data=f"qual_menu_{msg_id}"))
    buttons.append(row3)

    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_file_{msg_id}")])

    await client.edit_message_text(
        chat_id=user_id,
        message_id=msg_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def update_confirmation_message(client, msg_id, user_id):
    if msg_id not in file_sessions: return

    fs = file_sessions[msg_id]

    # Check if this is an auto-detect session to use the new UI?
    # Or keep consistent? The request asked for "Detected Movie..." UI.
    # If "is_auto" is present, use update_auto_detected_message?
    if fs.get("is_auto"):
        await update_auto_detected_message(client, msg_id, user_id)
        return

    # Fallback to existing logic for manual flow (re-implemented here because I overwrote the file)
    sd = get_data(user_id)
    is_sub = sd.get("is_subtitle")

    text = f"📄 **File:** `{fs['original_name']}`\n\n"

    if is_sub:
        text += f"**Language:** `{fs.get('language')}`\n"
    else:
        text += f"**Detected Quality:** `{fs['quality']}`\n"

    buttons = []
    row1 = [InlineKeyboardButton("✅ Accept", callback_data=f"confirm_{msg_id}")]
    row2 = []

    if not is_sub:
        row2.append(InlineKeyboardButton("Change Quality", callback_data=f"qual_menu_{msg_id}"))

    if sd.get("type") == "series":
        text += f"**Season:** `{fs['season']}` | **Episode:** `E{fs['episode']:02d}`\n"
        row2.append(InlineKeyboardButton("Change Episode", callback_data=f"ep_change_{msg_id}"))
        row2.append(InlineKeyboardButton("Change Season", callback_data=f"season_change_{msg_id}"))

    buttons.append(row1)
    if row2:
        buttons.append(row2)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_file_{msg_id}")])

    await client.edit_message_text(
        chat_id=user_id,
        message_id=msg_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^confirm_(\d+)$"))
async def handle_confirm(client, callback_query):
    msg_id = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions.pop(msg_id)

    if fs.get("is_auto"):
        # Use fs as the full data source
        full_data = fs
    else:
        sd = get_data(user_id)
        full_data = sd.copy()
        full_data.update(fs)

    await process_file(client, callback_query.message, full_data)

@Client.on_callback_query(filters.regex(r"^qual_menu_(\d+)$"))
async def handle_quality_menu(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])

    await callback_query.message.edit_text(
        "Select Quality:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("480p", callback_data=f"set_qual_{msg_id}_480p"),
             InlineKeyboardButton("720p", callback_data=f"set_qual_{msg_id}_720p")],
            [InlineKeyboardButton("1080p", callback_data=f"set_qual_{msg_id}_1080p"),
             InlineKeyboardButton("2160p", callback_data=f"set_qual_{msg_id}_2160p")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"back_confirm_{msg_id}")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^set_qual_(\d+)_(.+)$"))
async def handle_set_quality(client, callback_query):
    data = callback_query.data.split("_")
    msg_id = int(data[2])
    qual = data[3]

    if msg_id in file_sessions:
        file_sessions[msg_id]["quality"] = qual
        await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^back_confirm_(\d+)$"))
async def handle_back_confirm(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^ep_change_(\d+)$"))
async def handle_ep_change_prompt(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    set_state(user_id, f"awaiting_episode_correction_{msg_id}")
    await callback_query.message.edit_text(
        "**Enter Episode Number:**\n"
        "Send a number (e.g. 5)",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"back_confirm_{msg_id}")]])
    )

@Client.on_callback_query(filters.regex(r"^season_change_(\d+)$"))
async def handle_season_change_prompt(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    set_state(user_id, f"awaiting_season_correction_{msg_id}")
    await callback_query.message.edit_text(
        "**Enter Season Number:**\n"
        "Send a number (e.g. 2)",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"back_confirm_{msg_id}")]])
    )

@Client.on_callback_query(filters.regex(r"^cancel_file_(\d+)$"))
async def handle_file_cancel(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    file_sessions.pop(msg_id, None)
    await callback_query.message.delete()

# New Handlers for Auto-Detect Menu

@Client.on_callback_query(filters.regex(r"^change_type_(\d+)$"))
async def handle_change_type(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions: return

    # Cycle: Movie -> Series -> Subtitle (Movie) -> Subtitle (Series) -> Movie?
    # Or simplified: Movie <-> Series. And toggle Subtitle separately?
    # User said: "Change File Type (halt ob movie, series oder subtitle)"

    fs = file_sessions[msg_id]
    current_type = fs['type']
    is_sub = fs['is_subtitle']

    # Logic to cycle
    # 1. Movie -> Series
    # 2. Series -> Subtitle (Movie)
    # 3. Subtitle (Movie) -> Subtitle (Series)
    # 4. Subtitle (Series) -> Movie

    if not is_sub and current_type == "movie":
        fs['type'] = "series"
        fs['is_subtitle'] = False
    elif not is_sub and current_type == "series":
        fs['type'] = "movie"
        fs['is_subtitle'] = True
        fs['language'] = "en" # Default
    elif is_sub and current_type == "movie":
        fs['type'] = "series"
        fs['is_subtitle'] = True
    elif is_sub and current_type == "series":
        fs['type'] = "movie"
        fs['is_subtitle'] = False

    await update_auto_detected_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^change_tmdb_(\d+)$"))
async def handle_change_tmdb_init(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    # We need to trigger a search, but we need to know which file we are searching for.
    # We can use a temporary state like "awaiting_search_correction_{msg_id}"

    set_state(user_id, f"awaiting_search_correction_{msg_id}")
    fs = file_sessions[msg_id]
    mtype = fs['type']

    await callback_query.message.edit_text(
        f"🔍 **Search {mtype.capitalize()}**\n\n"
        "Please enter the correct name:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"back_confirm_{msg_id}")]])
    )

@Client.on_callback_query(filters.regex(r"^change_se_(\d+)$"))
async def handle_change_se_menu(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])

    await callback_query.message.edit_text(
        "Select what to change:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Change Season", callback_data=f"season_change_{msg_id}"),
             InlineKeyboardButton("Change Episode", callback_data=f"ep_change_{msg_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"back_confirm_{msg_id}")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^correct_tmdb_(\d+)_(\d+)$"))
async def handle_correct_tmdb_selection(client, callback_query):
    data = callback_query.data.split("_")
    msg_id = int(data[2])
    tmdb_id = data[3]

    if msg_id not in file_sessions: return
    fs = file_sessions[msg_id]

    # Fetch details
    try:
        details = await tmdb.get_details(fs['type'], tmdb_id)
    except:
        return

    title = details.get("title") if fs['type'] == "movie" else details.get("name")
    year = (details.get("release_date") if fs['type'] == "movie" else details.get("first_air_date", ""))[:4]
    poster = f"https://image.tmdb.org/t/p/w500{details.get('poster_path')}" if details.get("poster_path") else None

    fs['tmdb_id'] = tmdb_id
    fs['title'] = title
    fs['year'] = year
    fs['poster'] = poster

    # Clear state
    set_state(callback_query.from_user.id, None)

    # Delete the search result message and update original
    await callback_query.message.delete()
    await update_auto_detected_message(client, msg_id, callback_query.from_user.id)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
