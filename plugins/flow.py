from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils.tmdb import tmdb
from utils.auth import auth_filter
from utils.state import set_state, get_state, update_data, get_data, clear_session
from plugins.process import process_file
from config import Config
from utils.log import get_logger
import asyncio
import re

logger = get_logger("plugins.flow")
logger.info("Loading plugins.flow...")

# Store for per-file processing data (keyed by Confirmation Message ID)
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
            [InlineKeyboardButton("📝 Subtitles", callback_data="type_subtitles")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
        ])
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
    await callback_query.answer("Subtitles feature coming soon!", show_alert=True)

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
        await msg.edit_text("❌ No results found. Please try again.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]))
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
    set_state(user_id, "awaiting_file_upload")

    data = get_data(user_id)
    title = data.get("title")

    await message.reply_text(
        f"**Season {season} Confirmed** for {title}.\n\n"
        "Please **forward the file(s)** you want to rename.\n"
        "For series, I will auto-detect the episode number from the filename (e.g. S01E05).",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
    )

# Use group=1 to ensure it runs even if other handlers match (though debug is -1)
# Removed auth_filter from here, check manually if needed, or ensure auth_filter is working.
# auth_filter is simple lambda, should work.
# Added logging.
@Client.on_message(filters.text & filters.private, group=1)
async def handle_text_input(client, message):
    user_id = message.from_user.id

    # Auth check again just in case
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
    elif state == "awaiting_season":
        await season_handler(client, message)

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

@Client.on_callback_query(filters.regex(r"^sel_tmdb_(movie|series)_(\d+)$"))
async def handle_tmdb_selection(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")
    media_type = data[2]
    tmdb_id = data[3]

    # Fetch details
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
        set_state(user_id, "awaiting_file_upload")
        await callback_query.message.edit_text(
            f"**Selected Movie:** {title} ({year})\n\n"
            "Please **forward the file(s)** you want to rename.\n"
            "You can forward multiple files.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Done / Cancel", callback_data="cancel_rename")]])
        )

@Client.on_callback_query(filters.regex(r"^cancel_rename$"))
async def handle_cancel(client, callback_query):
    user_id = callback_query.from_user.id
    clear_session(user_id)
    await callback_query.message.edit_text("Renaming cancelled. Use /start to begin again.")

# --- File Handling ---

@Client.on_message((filters.document | filters.video) & filters.private, group=1)
async def handle_file_upload(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    # Auth Check
    if not (user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS):
        return

    if state != "awaiting_file_upload":
        return

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
        match = re.search(r"[sS]?\d{1,2}[eE](\d{1,2})", file_name)
        if match:
            episode = int(match.group(1))
        else:
             match = re.search(r"[eE](\d{1,2})", file_name)
             if match:
                 episode = int(match.group(1))

    msg = await message.reply_text("Processing file...", quote=True)

    file_sessions[msg.id] = {
        "file_message": message,
        "quality": quality,
        "episode": episode,
        "season": season,
        "original_name": file_name
    }

    await update_confirmation_message(client, msg.id, user_id)

async def update_confirmation_message(client, msg_id, user_id):
    if msg_id not in file_sessions: return

    fs = file_sessions[msg_id]
    sd = get_data(user_id)

    text = f"📄 **File:** `{fs['original_name']}`\n\n"
    text += f"**Detected Quality:** `{fs['quality']}`\n"

    buttons = []
    row1 = [InlineKeyboardButton("✅ Accept", callback_data=f"confirm_{msg_id}")]
    row2 = [InlineKeyboardButton("Change Quality", callback_data=f"qual_menu_{msg_id}")]

    if sd.get("type") == "series":
        text += f"**Season:** `{fs['season']}` | **Episode:** `E{fs['episode']:02d}`\n"
        row2.append(InlineKeyboardButton("Change Episode", callback_data=f"ep_change_{msg_id}"))
        row2.append(InlineKeyboardButton("Change Season", callback_data=f"season_change_{msg_id}"))

    buttons.append(row1)
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
    sd = get_data(user_id)

    full_data = sd.copy()
    full_data.update(fs) # fs overrides common data (season)

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
