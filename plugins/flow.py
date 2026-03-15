from pyrogram.errors import MessageNotModified
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
import os

logger = get_logger("plugins.flow")
logger.info("Loading plugins.flow...")

file_sessions = {}

batch_sessions = {}

batch_tasks = {}

batch_status_msgs = {}


@Client.on_callback_query(filters.regex(r"^start_renaming$"))
async def handle_start_renaming(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    logger.info(f"Start renaming flow for {user_id}")
    clear_session(user_id)
    set_state(user_id, "awaiting_type")

    try:
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
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^type_general$"))
async def handle_type_general(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    logger.info(f"User {user_id} selected general type")

    update_data(user_id, "type", "general")
    update_data(user_id, "tmdb_id", None)

    set_state(user_id, "awaiting_general_file")

    try:
        await callback_query.message.edit_text(
            "📄 **General Mode**\n\n"
            "Please **send me the file** you want to rename.\n"
            "*(You can send any type of file: Documents, Videos, Audio, etc.)*",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^type_personal_(video|photo|file)$"))
async def handle_type_personal(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    personal_type = callback_query.data.split("_")[2]
    logger.info(f"User {user_id} selected personal type: {personal_type}")

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

    try:
        await callback_query.message.edit_text(
            f"✍️ **Personal {label} Details**\n\n"
            "Please enter the name you want to use for this file.\n"
            "Format: `Title (Year)` or just `Title`\n"
            "Example: `Family Vacation Hawaii (2024)`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^type_(movie|series)$"))
async def handle_type_selection(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    media_type = callback_query.data.split("_")[1]
    logger.info(f"User {user_id} selected type: {media_type}")

    update_data(user_id, "type", media_type)
    set_state(user_id, f"awaiting_search_{media_type}")

    try:
        await callback_query.message.edit_text(
            f"🔍 **Search {media_type.capitalize()}**\n\n"
            f"Please enter the name of the {media_type} (e.g. 'Zootopia' or 'The Rookie').",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^type_subtitles$"))
async def handle_type_subtitles(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    try:
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
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^type_sub_(movie|series)$"))
async def handle_subtitle_type_selection(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    media_type = callback_query.data.split("_")[2]
    logger.info(f"User {user_id} selected subtitle type: {media_type}")

    update_data(user_id, "type", media_type)
    update_data(user_id, "is_subtitle", True)
    set_state(user_id, f"awaiting_search_{media_type}")

    try:
        await callback_query.message.edit_text(
            f"🔍 **Search {media_type.capitalize()} (Subtitles)**\n\n"
            f"Please enter the name of the {media_type}.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


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
        set_state(user_id, "awaiting_season")
        await message.reply_text(
            "📺 **Series:** What Season is this? (e.g., `1` or `01`)",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
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
        await prompt_dumb_channel(client, user_id, message, is_edit=False)


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
        try:
            await msg.edit_text(f"❌ Search Error: {e}")
        except MessageNotModified:
            pass
        return

    if not results:
        try:
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
        except MessageNotModified:
            pass
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

    try:
        await msg.edit_text(
            f"**Select {media_type.capitalize()}**\n\n"
            f"Found {len(results)} results for '{query}':",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except MessageNotModified:
        pass


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
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
        return

    await prompt_dumb_channel(client, user_id, message)


async def episode_handler(client, message):
    user_id = message.from_user.id
    text = message.text

    if not text.isdigit():
        await message.reply_text("Please enter a valid number for the episode.")
        return

    episode = int(text)
    update_data(user_id, "episode", episode)

    await initiate_language_selection(client, user_id, message)


@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=2)
async def handle_text_input(client, message):
    user_id = message.from_user.id

    if not Config.PUBLIC_MODE:
        if not (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS):
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

    elif state == "awaiting_general_name":
        user_id = message.from_user.id
        new_name = message.text.strip()
        update_data(user_id, "general_name", new_name)

        await prompt_dumb_channel(client, user_id, message, is_edit=False)

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
        return

    elif state == "awaiting_watermark_text":
        user_id = message.from_user.id
        text = message.text.strip()
        update_data(user_id, "watermark_content", text)
        set_state(user_id, "awaiting_watermark_position")

        await message.reply_text(
            "📍 **Select Watermark Position**\n\nWhere should the watermark be placed?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Top-Left", callback_data="wm_pos_topleft"
                        ),
                        InlineKeyboardButton(
                            "Top-Right", callback_data="wm_pos_topright"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "Bottom-Left", callback_data="wm_pos_bottomleft"
                        ),
                        InlineKeyboardButton(
                            "Bottom-Right", callback_data="wm_pos_bottomright"
                        ),
                    ],
                    [InlineKeyboardButton("Center", callback_data="wm_pos_center")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )
        return

    elif state == "awaiting_language_custom":
        lang = message.text.strip().lower()
        if len(lang) > 10 or not lang.replace("-", "").isalnum():
            await message.reply_text(
                "Invalid language code. Keep it short (e.g. 'en', 'pt-br')."
            )
            return

        update_data(user_id, "language", lang)
        await prompt_dumb_channel(client, user_id, message, is_edit=False)

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
            mtype = fs["type"]

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
                try:
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
                except MessageNotModified:
                    pass
                return

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

            try:
                await msg.edit_text(
                    f"Select correct {mtype}:",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            except MessageNotModified:
                pass


@Client.on_callback_query(filters.regex(r"^manual_entry$"))
async def handle_manual_entry(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    logger.info(f"User {user_id} selected manual entry.")

    update_data(user_id, "tmdb_id", None)

    media_type = get_data(user_id).get("type", "movie")

    set_state(user_id, "awaiting_manual_title")
    try:
        await callback_query.message.edit_text(
            f"✍️ **Manual Entry ({media_type.capitalize()})**\n\n"
            "Please enter the exact title and year you want to use.\n"
            "Format: `Title (Year)`\n"
            "Example: `My Family Vacation (2023)`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^send_as_(photo|document)$"))
async def handle_send_as_preference(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    user_id = callback_query.from_user.id
    pref = callback_query.data.split("_")[2]

    update_data(user_id, "send_as", pref)
    await prompt_dumb_channel(client, user_id, callback_query.message, is_edit=True)


@Client.on_callback_query(filters.regex(r"^sel_tmdb_(movie|series)_(\d+)$"))
async def handle_tmdb_selection(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
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

    if media_type == "series":
        set_state(user_id, "awaiting_season")
        try:
            await callback_query.message.edit_text(
                f"**Selected Series:** {title} ({year})\n\n"
                "Please enter the **Season Number** (e.g. 1, 2, ...):",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
                ),
            )
        except MessageNotModified:
            pass
    else:
        data = get_data(user_id)
        if data.get("is_subtitle"):
            await initiate_language_selection(client, user_id, callback_query.message)
        else:
            await prompt_dumb_channel(
                client, user_id, callback_query.message, is_edit=True
            )


async def prompt_dumb_channel(client, user_id, message_obj, is_edit=False):
    channels = await db.get_dumb_channels(user_id)
    if not channels:
        set_state(user_id, "awaiting_file_upload")
        text = "✅ **Ready!**\n\nNow, **send me the file(s)** you want to rename."
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
        )
        if is_edit:
            try:
                await message_obj.edit_text(text, reply_markup=reply_markup)
            except MessageNotModified:
                pass
        else:
            await message_obj.reply_text(text, reply_markup=reply_markup)
        return

    set_state(user_id, "awaiting_dumb_channel_selection")
    text = "📺 **Dumb Channel Selection**\n\nWhere should the files from this session be sent?"
    buttons = []
    for ch_id, ch_name in channels.items():
        buttons.append(
            [
                InlineKeyboardButton(
                    f"Send to {ch_name}", callback_data=f"sel_dumb_{ch_id}"
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                "❌ Don't send to Dumb Channel", callback_data="sel_dumb_none"
            )
        ]
    )
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")])

    if is_edit:
        try:
            await message_obj.edit_text(
                text, reply_markup=InlineKeyboardMarkup(buttons)
            )
        except MessageNotModified:
            pass
    else:
        await message_obj.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^sel_dumb_(.*)$"))
async def handle_dumb_selection(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    ch_id = callback_query.data.split("_")[2]

    if ch_id != "none":
        update_data(user_id, "dumb_channel", ch_id)
    else:
        update_data(user_id, "dumb_channel", None)

    session_data = get_data(user_id)

    if session_data.get("type") == "general":
        data = {
            "type": "general",
            "original_name": session_data.get("original_name"),
            "file_message_id": session_data.get("file_message_id"),
            "file_chat_id": session_data.get("file_chat_id"),
            "is_auto": False,
            "dumb_channel": session_data.get("dumb_channel"),
            "send_as": session_data.get("send_as"),
            "general_name": session_data.get("general_name"),
        }

        meta = analyze_filename(session_data.get("original_name"))
        data.update(meta)

        try:
            msg = await client.get_messages(
                session_data.get("file_chat_id"), session_data.get("file_message_id")
            )
            data["file_message"] = msg
            await callback_query.message.delete()
            reply_msg = await client.send_message(user_id, "Processing file...")
            from plugins.process import process_file

            asyncio.create_task(process_file(client, reply_msg, data))
        except Exception as e:
            logger.error(f"Failed to get message for general mode: {e}")
            await client.send_message(user_id, f"Error: {e}")

        clear_session(user_id)
        return

    set_state(user_id, "awaiting_file_upload")
    try:
        await callback_query.message.edit_text(
            f"✅ **Ready!**\n\n" f"Now, **send me the file(s)** you want to rename.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


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
        try:
            await message_obj.edit_text(
                text, reply_markup=InlineKeyboardMarkup(buttons)
            )
        except MessageNotModified:
            pass
    else:
        await message_obj.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^lang_"))
async def handle_language_callback(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")[1]

    if data == "custom":
        set_state(user_id, "awaiting_language_custom")
        try:
            await callback_query.message.edit_text(
                "✍️ **Enter Custom Language Code**\n\n"
                "Please type the language code (e.g. `por`, `hin`, `jpn`, `pt-br`):",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
                ),
            )
        except MessageNotModified:
            pass
        return

    update_data(user_id, "language", data)
    await prompt_dumb_channel(client, user_id, callback_query.message, is_edit=True)


@Client.on_callback_query(filters.regex(r"^gen_send_as_(document|media)$"))
async def handle_gen_send_as(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    pref = callback_query.data.split("_")[3]

    update_data(user_id, "send_as", pref)

    file_name = get_data(user_id).get("original_name", "unknown")

    try:
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
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^gen_prompt_rename$"))
async def handle_gen_prompt_rename(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    set_state(user_id, "awaiting_general_name")

    try:
        await callback_query.message.edit_text(
            "✏️ **Enter the new name for the file:**\n\n"
            "You can use variables like `{filename}`, `{Season_Episode}`, `{Quality}`, `{Year}`, `{Title}`.\n"
            "*(The extension is added automatically)*\n\n"
            "Example: `My File - {filename}`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^cancel_rename$"))
async def handle_cancel(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    try:
        await callback_query.message.edit_text(
            "**Current Task Cancelled** ❌\n\n"
            "Your progress has been cleared.\n"
            "You can simply send me a file anytime to start over, or use the buttons below.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🎬 Start Renaming Manually", callback_data="start_renaming"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📖 Help & Guide", callback_data="help_guide"
                        )
                    ],
                ]
            ),
        )
    except MessageNotModified:
        pass


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
            return (0, data.get("season", 0), data.get("episode", 0))
        else:
            return (1, data.get("original_name", "").lower(), 0)

    sorted_batch = sorted(batch, key=get_sort_key)

    for item in sorted_batch:
        message = item["message"]
        data = item["data"]
        is_auto = data.get("is_auto", False)

        msg = await message.reply_text("Processing file...", quote=True)
        file_sessions[msg.id] = data

        if is_auto:
            await update_auto_detected_message(client, msg.id, user_id)
        else:
            await update_confirmation_message(client, msg.id, user_id)


from utils.auth import check_force_sub
from database import db
from utils.queue_manager import queue_manager
import uuid


@Client.on_message(
    (filters.document | filters.video | filters.photo | filters.audio | filters.voice)
    & filters.private,
    group=2,
)
async def handle_file_upload(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == "awaiting_convert_file":
        if (
            not getattr(message, "photo", None)
            and not getattr(message, "video", None)
            and not getattr(message, "document", None)
        ):
            await message.reply_text("Please send an image or video file.")
            return

        file_name = "unknown_file.bin"
        is_video = False
        is_image = False

        if getattr(message, "video", None):
            file_name = message.video.file_name or "video.mp4"
            is_video = True
        elif getattr(message, "photo", None):
            file_name = f"image_{message.id}.jpg"
            is_image = True
        elif getattr(message, "document", None):
            file_name = message.document.file_name or "file.bin"
            mime = message.document.mime_type or ""
            if "video" in mime:
                is_video = True
            if "image" in mime:
                is_image = True

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)

        buttons = []
        if is_video:
            buttons.append(
                [
                    InlineKeyboardButton(
                        "Extract Audio (MP3)", callback_data="convert_to_mp3"
                    )
                ]
            )
            buttons.append(
                [InlineKeyboardButton("Convert to GIF", callback_data="convert_to_gif")]
            )
            buttons.append(
                [InlineKeyboardButton("Convert to MKV", callback_data="convert_to_mkv")]
            )
            buttons.append(
                [InlineKeyboardButton("Convert to MP4", callback_data="convert_to_mp4")]
            )
        elif is_image:
            ext = os.path.splitext(file_name)[1].lower() if file_name else ""
            img_buttons = []
            if ext != ".png":
                img_buttons.append(
                    InlineKeyboardButton(
                        "Convert to PNG", callback_data="convert_to_png"
                    )
                )
            if ext not in [".jpg", ".jpeg"]:
                img_buttons.append(
                    InlineKeyboardButton(
                        "Convert to JPG", callback_data="convert_to_jpg"
                    )
                )
            if ext != ".webp":
                img_buttons.append(
                    InlineKeyboardButton(
                        "Convert to WEBP", callback_data="convert_to_webp"
                    )
                )

            for i in range(0, len(img_buttons), 2):
                buttons.append(img_buttons[i : i + 2])
        else:
            await message.reply_text(
                "Could not determine file type. Please send a clear Image or Video."
            )
            return

        buttons.append(
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]
        )

        set_state(user_id, "awaiting_convert_format")
        await message.reply_text(
            f"🔀 **File Converter**\n\n"
            f"**File:** `{file_name}`\n\n"
            "Select the format you want to convert to:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if state == "awaiting_audio_thumb":
        if not getattr(message, "photo", None):
            await message.reply_text("Please send a photo for the cover art.")
            return

        update_data(user_id, "audio_thumb_id", message.photo.file_id)
        set_state(user_id, "awaiting_audio_menu")
        await render_audio_menu(client, message, user_id)
        return

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
            "© **Image Watermarker**\n\n"
            "Image received. What type of watermark do you want to add?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📝 Text Watermark", callback_data="watermark_type_text"
                        ),
                        InlineKeyboardButton(
                            "🖼 Image Watermark", callback_data="watermark_type_image"
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
            "📍 **Select Watermark Position**\n\nWhere should the watermark be placed?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Top-Left", callback_data="wm_pos_topleft"
                        ),
                        InlineKeyboardButton(
                            "Top-Right", callback_data="wm_pos_topright"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "Bottom-Left", callback_data="wm_pos_bottomleft"
                        ),
                        InlineKeyboardButton(
                            "Bottom-Right", callback_data="wm_pos_bottomright"
                        ),
                    ],
                    [InlineKeyboardButton("Center", callback_data="wm_pos_center")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )
        return

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
        if not await check_force_sub(client, user_id):
            config = await db.get_public_config()
            invite_link = config.get("force_sub_link") or config.get(
                "force_sub_channel", ""
            )

            await message.reply_text(
                f"⚠️ **Access Restricted**\n\n"
                f"You must join our community channel to use the **{config.get('bot_name', 'XTV Rename Bot')}**.\n\n"
                "**How to continue:**\n"
                "1️⃣ Click the button below to join the channel.\n"
                "2️⃣ Come back here.\n"
                "3️⃣ Send or forward your file again!\n",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📢 Join Our Community Channel", url=invite_link
                            )
                        ]
                    ]
                ),
            )
            return

    if await db.is_user_blocked(user_id):
        await message.reply_text(
            "🚫 **Access Blocked**\n\nYou have been blocked from using this bot."
        )
        return

    media = message.document or message.video
    if media:
        file_size = media.file_size

        # WE MOVED QUOTA CHECK OUT OF HERE AND INTO process_file()

        if file_size > 4000 * 1024 * 1024:
            await message.reply_text(
                "❌ **File Too Large**\n\nTelegram's absolute maximum file size is 4GB. This file cannot be processed."
            )
            return

        if file_size > 2000 * 1000 * 1000 and getattr(client, "user_bot", None) is None:
            await message.reply_text(
                "❌ **𝕏TV Pro™ Required**\n\nThis file is larger than 2GB. You must configure the 𝕏TV Pro™ Premium Userbot in the `/admin` panel to process files of this size."
            )
            return

    if state != "awaiting_file_upload":
        if state is None:
            await handle_auto_detection(client, message)
        elif state == "awaiting_convert_file":
            pass
        return

    if message.photo:
        file_name = f"image_{message.id}.jpg"
    else:
        file_name = (
            message.document.file_name if message.document else message.video.file_name
        )

    if not file_name:
        file_name = "unknown.mkv"

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

    lang = (
        session_data.get("language", "en") if session_data.get("is_subtitle") else None
    )

    if user_id not in batch_sessions:
        batch_id = queue_manager.create_batch()
        batch_sessions[user_id] = {"batch_id": batch_id, "items": []}
        msg = await message.reply_text(
            "⏳ **Sorting Files...**\nPlease wait a moment.", quote=True
        )
        batch_status_msgs[user_id] = msg

    if user_id in batch_tasks:
        batch_tasks[user_id].cancel()

    batch_id = batch_sessions[user_id]["batch_id"]
    item_id = str(uuid.uuid4())

    quality_priority = {"2160p": 0, "1080p": 1, "720p": 2, "480p": 3}

    sort_key = (
        (0, season, episode)
        if session_data.get("type") == "series"
        else (1, quality_priority.get(quality, 4), 0)
    )
    display_name = (
        f"S{season:02d}E{episode:02d}"
        if session_data.get("type") == "series"
        else f"{quality}"
    )

    update_data(user_id, "batch_id", batch_id)

    queue_manager.add_to_batch(batch_id, item_id, sort_key, display_name, message.id)

    data = {
        "file_message": message,
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
    }
    batch_sessions[user_id]["items"].append({"message": message, "data": data})

    async def wait_and_process():
        try:
            await asyncio.sleep(3.0)
            if batch_tasks.get(user_id) == asyncio.current_task():
                del batch_tasks[user_id]
            await process_batch(client, user_id)
        except asyncio.CancelledError:
            pass

    batch_tasks[user_id] = asyncio.create_task(wait_and_process())


async def handle_auto_detection(client, message):
    if message.photo:
        file_name = f"image_{message.id}.jpg"
    else:
        file_name = (
            message.document.file_name if message.document else message.video.file_name
        )

    if not file_name:
        file_name = "unknown_file.bin"

    metadata = analyze_filename(file_name)
    tmdb_data = await auto_match_tmdb(metadata)

    if not tmdb_data:
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
    lang = metadata.get("language", "en")

    user_id = message.from_user.id

    default_dumb_channel = await db.get_default_dumb_channel(user_id)

    if user_id not in batch_sessions:
        batch_id = queue_manager.create_batch()
        batch_sessions[user_id] = {"batch_id": batch_id, "items": []}
        msg = await message.reply_text(
            "⏳ **Sorting Files...**\nPlease wait a moment.", quote=True
        )
        batch_status_msgs[user_id] = msg

    if user_id in batch_tasks:
        batch_tasks[user_id].cancel()

    batch_id = batch_sessions[user_id]["batch_id"]
    item_id = str(uuid.uuid4())

    quality_priority = {"2160p": 0, "1080p": 1, "720p": 2, "480p": 3}

    sort_key = (
        (0, season, episode)
        if tmdb_data["type"] == "series"
        else (1, quality_priority.get(quality, 4), 0)
    )
    display_name = (
        f"S{season:02d}E{episode:02d}"
        if tmdb_data["type"] == "series"
        else f"{quality}"
    )

    queue_manager.add_to_batch(batch_id, item_id, sort_key, display_name, message.id)

    data = {
        "file_message": message,
        "original_name": file_name,
        "quality": quality,
        "episode": episode,
        "season": season,
        "language": lang,
        "tmdb_id": tmdb_data["tmdb_id"],
        "title": tmdb_data["title"],
        "year": tmdb_data["year"],
        "poster": tmdb_data["poster"],
        "type": tmdb_data["type"],
        "is_subtitle": is_subtitle,
        "is_auto": True,
        "dumb_channel": default_dumb_channel,
        "batch_id": batch_id,
        "item_id": item_id,
    }
    batch_sessions[user_id]["items"].append({"message": message, "data": data})

    async def wait_and_process():
        try:
            await asyncio.sleep(3.0)
            if batch_tasks.get(user_id) == asyncio.current_task():
                del batch_tasks[user_id]
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

    if fs["is_subtitle"]:
        text += f"**Language:** `{fs['language']}`\n"
    else:
        text += f"**Quality:** `{fs['quality']}`\n"

    if fs["type"] == "series":
        text += f"**Season:** `{fs['season']}` | **Episode:** `E{fs['episode']:02d}`\n"

    buttons = []

    buttons.append(
        [InlineKeyboardButton("✅ Accept", callback_data=f"confirm_{msg_id}")]
    )

    row2 = []
    row2.append(
        InlineKeyboardButton("Change Type", callback_data=f"change_type_{msg_id}")
    )
    if fs["type"] == "series":
        row2.append(
            InlineKeyboardButton("Change Show", callback_data=f"change_tmdb_{msg_id}")
        )
    else:
        row2.append(
            InlineKeyboardButton("Change Movie", callback_data=f"change_tmdb_{msg_id}")
        )
    buttons.append(row2)

    row3 = []
    if fs["type"] == "series":
        row3.append(InlineKeyboardButton("S/E", callback_data=f"change_se_{msg_id}"))
    if not fs["is_subtitle"]:
        row3.append(
            InlineKeyboardButton("Quality", callback_data=f"qual_menu_{msg_id}")
        )
    buttons.append(row3)

    buttons.append(
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_file_{msg_id}")]
    )

    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except MessageNotModified:
        pass


async def update_confirmation_message(client, msg_id, user_id):
    if msg_id not in file_sessions:
        return

    fs = file_sessions[msg_id]

    if fs.get("is_auto"):
        await update_auto_detected_message(client, msg_id, user_id)
        return

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
        row2.append(
            InlineKeyboardButton("Change Quality", callback_data=f"qual_menu_{msg_id}")
        )

    if sd.get("type") == "series":
        text += f"**Season:** `{fs['season']}` | **Episode:** `E{fs['episode']:02d}`\n"
        row2.append(
            InlineKeyboardButton("Change Episode", callback_data=f"ep_change_{msg_id}")
        )
        row2.append(
            InlineKeyboardButton(
                "Change Season", callback_data=f"season_change_{msg_id}"
            )
        )

    buttons.append(row1)
    if row2:
        buttons.append(row2)
    buttons.append(
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_file_{msg_id}")]
    )

    try:
        await client.edit_message_text(
            chat_id=user_id,
            message_id=msg_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^confirm_(\d+)$"))
async def handle_confirm(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    msg_id = int(callback_query.data.split("_")[1])
    user_id = callback_query.from_user.id

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions.pop(msg_id)

    if fs.get("is_auto"):
        full_data = fs
    else:
        sd = get_data(user_id)
        full_data = sd.copy()
        full_data.update(fs)

    await process_file(client, callback_query.message, full_data)


@Client.on_callback_query(filters.regex(r"^qual_menu_(\d+)$"))
async def handle_quality_menu(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])

    try:
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
                            "🔙 Back", callback_data=f"back_confirm_{msg_id}"
                        )
                    ],
                ]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^set_qual_(\d+)_(.+)$"))
async def handle_set_quality(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    data = callback_query.data.split("_")
    msg_id = int(data[2])
    qual = data[3]

    if msg_id in file_sessions:
        file_sessions[msg_id]["quality"] = qual
        await update_confirmation_message(client, msg_id, callback_query.from_user.id)


@Client.on_callback_query(filters.regex(r"^back_confirm_(\d+)$"))
async def handle_back_confirm(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


@Client.on_callback_query(filters.regex(r"^ep_change_(\d+)$"))
async def handle_ep_change_prompt(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
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


@Client.on_callback_query(filters.regex(r"^season_change_(\d+)$"))
async def handle_season_change_prompt(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
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


@Client.on_callback_query(filters.regex(r"^cancel_file_(\d+)$"))
async def handle_file_cancel(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    file_sessions.pop(msg_id, None)
    await callback_query.message.delete()


@Client.on_callback_query(filters.regex(r"^audio_editor_menu$"))
async def handle_audio_editor_menu(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_audio_file")

    try:
        await callback_query.message.edit_text(
            "🎵 **Audio Metadata Editor**\n\n"
            "Please **send me the audio file** (e.g., MP3, FLAC, M4A) you want to edit.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(
    filters.regex(r"^audio_edit_(title|artist|album|thumb|process)$")
)
async def handle_audio_edit_callbacks(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    action = callback_query.data.split("_")[2]

    if action == "process":
        await callback_query.message.delete()
        session_data = get_data(user_id)

        data = {
            "type": "audio",
            "original_name": session_data.get("original_name"),
            "file_message_id": session_data.get("file_message_id"),
            "file_chat_id": session_data.get("file_chat_id"),
            "audio_title": session_data.get("audio_title", ""),
            "audio_artist": session_data.get("audio_artist", ""),
            "audio_album": session_data.get("audio_album", ""),
            "audio_thumb_id": session_data.get("audio_thumb_id"),
        }

        try:
            msg = await client.get_messages(
                session_data.get("file_chat_id"), session_data.get("file_message_id")
            )
            data["file_message"] = msg
            reply_msg = await client.send_message(user_id, "Processing audio file...")
            from plugins.process import process_file

            asyncio.create_task(process_file(client, reply_msg, data))
        except Exception as e:
            logger.error(f"Failed to get message for audio mode: {e}")
            await client.send_message(user_id, f"Error: {e}")
        clear_session(user_id)
        return

    set_state(user_id, f"awaiting_audio_{action}")

    if action == "thumb":
        text = "🖼 **Send me the new cover art (photo) for this audio file:**"
    else:
        text = f"✏️ **Send me the new {action.capitalize()} for this audio file:**\n*(Send '-' to clear the current value)*"

    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="audio_menu_back")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^audio_menu_back$"))
async def handle_audio_menu_back(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    set_state(user_id, "awaiting_audio_menu")
    await render_audio_menu(client, callback_query.message, user_id)


async def render_audio_menu(client, message, user_id):
    from pyrogram.types import Message

    sd = get_data(user_id)
    title = sd.get("audio_title", "Not Set")
    artist = sd.get("audio_artist", "Not Set")
    album = sd.get("audio_album", "Not Set")
    thumb = "✅ Uploaded" if sd.get("audio_thumb_id") else "❌ Not Set"

    text = (
        f"🎵 **Audio Metadata Editor**\n\n"
        f"**File:** `{sd.get('original_name')}`\n\n"
        f"**Title:** `{title}`\n"
        f"**Artist:** `{artist}`\n"
        f"**Album:** `{album}`\n"
        f"**Cover Art:** {thumb}\n\n"
        "Click the buttons below to edit."
    )

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ Edit Title", callback_data="audio_edit_title"),
                InlineKeyboardButton(
                    "👤 Edit Artist", callback_data="audio_edit_artist"
                ),
            ],
            [
                InlineKeyboardButton("💿 Edit Album", callback_data="audio_edit_album"),
                InlineKeyboardButton(
                    "🖼 Edit Cover Art", callback_data="audio_edit_thumb"
                ),
            ],
            [
                InlineKeyboardButton(
                    "✅ Process File", callback_data="audio_edit_process"
                )
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
        ]
    )

    if isinstance(message, Message):
        await message.reply_text(text, reply_markup=markup)
    else:
        try:
            await message.edit_text(text, reply_markup=markup)
        except MessageNotModified:
            pass


@Client.on_callback_query(filters.regex(r"^file_converter_menu$"))
async def handle_file_converter_menu(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_convert_file")

    try:
        await callback_query.message.edit_text(
            "🔀 **File Converter**\n\n"
            "Please **send me the file** (Video or Image) you want to convert.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^convert_to_(.+)$"))
async def handle_convert_to(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    target_format = callback_query.data.split("_")[2]

    await callback_query.message.delete()
    session_data = get_data(user_id)

    data = {
        "type": "convert",
        "original_name": session_data.get("original_name"),
        "file_message_id": session_data.get("file_message_id"),
        "file_chat_id": session_data.get("file_chat_id"),
        "target_format": target_format,
        "is_auto": False,
    }

    try:
        msg = await client.get_messages(
            session_data.get("file_chat_id"), session_data.get("file_message_id")
        )
        data["file_message"] = msg
        reply_msg = await client.send_message(user_id, "Processing conversion...")
        from plugins.process import process_file

        asyncio.create_task(process_file(client, reply_msg, data))
    except Exception as e:
        logger.error(f"Failed to get message for convert mode: {e}")
        await client.send_message(user_id, f"Error: {e}")

    clear_session(user_id)


@Client.on_callback_query(filters.regex(r"^watermarker_menu$"))
async def handle_watermarker_menu(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_watermark_image")

    try:
        await callback_query.message.edit_text(
            "© **Image Watermarker**\n\n"
            "Please **send me the image** you want to watermark.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^watermark_type_(text|image)$"))
async def handle_watermark_type(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    wtype = callback_query.data.split("_")[2]

    update_data(user_id, "watermark_type", wtype)
    set_state(user_id, f"awaiting_watermark_{wtype}")

    if wtype == "text":
        msg = "📝 **Send me the text** you want to use as a watermark:"
    else:
        set_state(user_id, "awaiting_watermark_overlay")
        msg = (
            "🖼 **Send me the image (PNG/JPG)** you want to use as a watermark overlay:"
        )

    try:
        await callback_query.message.edit_text(
            msg,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^wm_pos_(.*)$"))
async def handle_watermark_position(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    pos = callback_query.data.split("_")[2]
    update_data(user_id, "watermark_position", pos)

    set_state(user_id, "awaiting_watermark_size")
    try:
        await callback_query.message.edit_text(
            "📏 **Select Watermark Size**\n\nHow large should the watermark be?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Small", callback_data="wm_size_small"),
                        InlineKeyboardButton("Medium", callback_data="wm_size_medium"),
                        InlineKeyboardButton("Large", callback_data="wm_size_large"),
                    ],
                    [
                        InlineKeyboardButton("10% width", callback_data="wm_size_10"),
                        InlineKeyboardButton("20% width", callback_data="wm_size_20"),
                    ],
                    [InlineKeyboardButton("30% width", callback_data="wm_size_30")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")],
                ]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^wm_size_(.*)$"))
async def handle_watermark_size(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    user_id = callback_query.from_user.id
    size = callback_query.data.split("_")[2]
    update_data(user_id, "watermark_size", size)

    session_data = get_data(user_id)
    data = {
        "type": "watermark",
        "watermark_type": session_data.get("watermark_type"),
        "watermark_content": session_data.get("watermark_content"),
        "watermark_position": session_data.get("watermark_position"),
        "watermark_size": session_data.get("watermark_size"),
        "original_name": session_data.get("original_name"),
        "file_message_id": session_data.get("file_message_id"),
        "file_chat_id": session_data.get("file_chat_id"),
        "is_auto": False,
    }

    try:
        msg = await client.get_messages(
            session_data.get("file_chat_id"), session_data.get("file_message_id")
        )
        data["file_message"] = msg
        await callback_query.message.delete()
        reply_msg = await client.send_message(user_id, "Processing watermark...")
        from plugins.process import process_file

        asyncio.create_task(process_file(client, reply_msg, data))
    except Exception as e:
        logger.error(f"Failed to get message for watermark mode: {e}")
        await client.send_message(user_id, f"Error: {e}")

    clear_session(user_id)


@Client.on_callback_query(filters.regex(r"^change_type_(\d+)$"))
async def handle_change_type(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
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
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])
    user_id = callback_query.from_user.id

    set_state(user_id, f"awaiting_search_correction_{msg_id}")
    fs = file_sessions[msg_id]
    mtype = fs["type"]

    try:
        await callback_query.message.edit_text(
            f"🔍 **Search {mtype.capitalize()}**\n\n" "Please enter the correct name:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 Back", callback_data=f"back_confirm_{msg_id}"
                        )
                    ]
                ]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^change_se_(\d+)$"))
async def handle_change_se_menu(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])

    try:
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
                            "🔙 Back", callback_data=f"back_confirm_{msg_id}"
                        )
                    ],
                ]
            ),
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^correct_tmdb_(\d+)_(\d+)$"))
async def handle_correct_tmdb_selection(client, callback_query):
    from utils.state import get_state

    if get_state(callback_query.from_user.id):
        if callback_query.data not in [
            "cancel",
            "admin_main",
            "user_main",
            "settings_main",
            "dumb_menu",
        ] and not callback_query.data.startswith("cancel"):
            await callback_query.answer(
                "⚠️ Session expired. Please start again.", show_alert=True
            )
            return
    await callback_query.answer()
    data = callback_query.data.split("_")
    msg_id = int(data[2])
    tmdb_id = data[3]

    if msg_id not in file_sessions:
        return
    fs = file_sessions[msg_id]

    try:
        details = await tmdb.get_details(fs["type"], tmdb_id)
    except:
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


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
