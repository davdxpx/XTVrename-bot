# --- Imports ---
from pyrogram.errors import MessageNotModified
from pyrogram import Client, filters, StopPropagation, ContinuePropagation
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
from bson.objectid import ObjectId
import datetime
import os
import math

logger = get_logger("plugins.flow")
logger.info("Loading plugins.flow...")

file_sessions = {}

batch_sessions = {}

batch_tasks = {}

batch_status_msgs = {}

# === Helper Functions ===
def format_episode_str(episode):
    if isinstance(episode, list):
        return "".join([f"E{int(e):02d}" for e in episode])
    elif episode:
        return f"E{int(episode):02d}"
    return ""

@Client.on_callback_query(filters.regex(r"^start_renaming$"))

# --- Handlers ---
async def handle_start_renaming(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    logger.debug(f"Start renaming flow for {user_id}")
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
    await callback_query.answer()
    user_id = callback_query.from_user.id
    logger.debug(f"User {user_id} selected general type")

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
    await callback_query.answer()
    user_id = callback_query.from_user.id
    media_type = callback_query.data.split("_")[1]
    logger.debug(f"User {user_id} selected type: {media_type}")

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
    await callback_query.answer()
    user_id = callback_query.from_user.id
    media_type = callback_query.data.split("_")[2]
    logger.debug(f"User {user_id} selected subtitle type: {media_type}")

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

async def search_handler(client, message, media_type):
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

@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=2)
async def handle_text_input(client, message):
    user_id = message.from_user.id

    if not Config.PUBLIC_MODE:
        if not (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS):
            return

    state = get_state(user_id)
    logger.debug(f"Text input from {user_id}: {message.text} | State: {state}")

    if not state:
        return

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
                try:
                    await message.delete()
                except:
                    pass
                msg_id = get_data(user_id).get("dest_msg_id")
                if msg_id:
                    try:
                        await client.edit_message_text(message.chat.id, msg_id, f"❌ You have reached your custom folder limit ({folder_limit}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Options", callback_data="sel_dest_page_1")]]))
                    except:
                        pass
                else:
                    await message.reply_text(f"❌ You have reached your custom folder limit ({folder_limit}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Options", callback_data="sel_dest_page_1")]]))
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

        try:
            await message.delete()
        except:
            pass

        msg_id = get_data(user_id).get("dest_msg_id")

        # update destination selection and proceed to dumb channel selection
        update_data(user_id, "dest_folder", str(folder_id))

        if msg_id:
            try:
                await client.edit_message_text(message.chat.id, msg_id, f"✅ Folder **{folder_name}** created successfully and selected!")
            except:
                pass

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
        return

    if state == "awaiting_search_movie":
        await search_handler(client, message, "movie")
    elif state == "awaiting_search_series":
        await search_handler(client, message, "series")
    elif state == "awaiting_manual_title":
        await manual_title_handler(client, message)
    elif state == "awaiting_system_filename":
        template = message.text.strip()
        await db.update_template("system_filename", template, user_id=user_id)
        set_state(user_id, None)
        await message.reply_text(f"✅ System Filename template updated to:\n`{template}`")
        return

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
            try:
                await message.delete()
            except Exception:
                pass
            if prompt_msg_id:
                try:
                    await client.delete_messages(chat_id=user_id, message_ids=prompt_msg_id)
                except Exception:
                    pass
        import asyncio
        asyncio.create_task(delayed_cleanup())

        await prompt_destination_folder(client, user_id, message, is_edit=False)

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
        await prompt_destination_folder(client, user_id, message, is_edit=False)

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
                lang = await db.get_preferred_language(user_id)
                if mtype == "series":
                    results = await tmdb.search_tv(query, language=lang)
                else:
                    results = await tmdb.search_movie(query, language=lang)
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
    await callback_query.answer()
    user_id = callback_query.from_user.id
    logger.debug(f"User {user_id} selected manual entry.")

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
    user_id = callback_query.from_user.id
    pref = callback_query.data.split("_")[2]

    update_data(user_id, "send_as", pref)
    await prompt_destination_folder(client, user_id, callback_query.message, is_edit=True)

@Client.on_callback_query(filters.regex(r"^sel_tmdb_(movie|series)_(\d+)$"))
async def handle_tmdb_selection(client, callback_query):
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

import asyncio

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
                try:
                    await message_obj.delete()
                except Exception:
                    pass
            reply_msg = await client.send_message(user_id, "Processing file...")
            from plugins.process import process_file
            asyncio.create_task(process_file(client, reply_msg, data))
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
        try:
            await message_obj.edit_text(text, reply_markup=reply_markup)
        except MessageNotModified:
            pass
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
        try:
            await message_obj.edit_text(
                text, reply_markup=InlineKeyboardMarkup(buttons)
            )
        except MessageNotModified:
            pass
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
        try:
            await callback_query.message.edit_text(
                "📁 **Create New Folder**\n\nPlease enter a name for the new folder:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]])
            )
        except MessageNotModified:
            pass
        return

    dest = None
    if action == "root":
        dest = "root"
    elif action == "none":
        dest = "none"
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

    if session_data.get("type") == "general":
        if has_file:
            await process_ready_file(client, user_id, callback_query.message, session_data)
            return

    if has_file:
        await process_ready_file(client, user_id, callback_query.message, session_data)
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
        await client.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^lang_"))
async def handle_language_callback(client, callback_query):
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

from pyrogram.types import ForceReply

@Client.on_callback_query(filters.regex(r"^gen_prompt_rename$"))
async def handle_gen_prompt_rename(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    set_state(user_id, "awaiting_general_name")

    session_data = get_data(user_id)
    file_msg_id = session_data.get("file_message_id")
    file_chat_id = session_data.get("file_chat_id")

    try:
        await callback_query.message.delete()
    except Exception:
        pass

    orig_name = session_data.get("original_name", "Unknown File")
    text = (
        "✏️ **Enter the new name for this file:**\n\n"
        "You can use variables like `{filename}`, `{Season_Episode}`, `{Quality}`, `{Year}`, `{Title}`.\n"
        "*(The extension is added automatically)*\n\n"
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

    try:
        await callback_query.message.edit_text(
            "**Current Task Cancelled** ❌\n\n"
            "Your progress has been cleared.\n"
            "You can simply send me a file anytime to start over, or use the buttons below.",
            reply_markup=InlineKeyboardMarkup(buttons),
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

        if is_auto:
            await update_auto_detected_message(client, msg.id, user_id)
        else:
            await update_confirmation_message(client, msg.id, user_id)

from utils.auth import check_force_sub
from database import db
from utils.queue_manager import queue_manager
import uuid
from utils.gate import send_force_sub_gate, check_and_send_welcome
from utils.archive import is_archive, check_password_protected, extract_archive
from utils.progress import progress_for_pyrogram
import time
import random

@Client.on_message(
    (filters.document | filters.video | filters.photo | filters.audio | filters.voice)
    & filters.private,
    group=2,
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
            buttons.append(
                [InlineKeyboardButton("Convert to x264 (H.264)", callback_data="convert_to_x264")]
            )
            buttons.append(
                [InlineKeyboardButton("Convert to x265 (HEVC)", callback_data="convert_to_x265")]
            )
            buttons.append(
                [InlineKeyboardButton("Normalize Audio", callback_data="convert_to_audionorm")]
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
            return

    if message.photo:
        file_name = f"image_{message.id}.jpg"
    else:
        file_name = (
            message.document.file_name if message.document else message.video.file_name
        )

    if not file_name:
        file_name = "unknown.mkv"

    if await is_archive(file_name):
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
    if Config.PUBLIC_MODE:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                is_priority = plan_settings.get("features", {}).get("priority_queue", False)

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
    }
    batch_sessions[user_id]["items"].append({"message": message, "data": data})

    async def wait_and_process():
        try:
            # Give non-priority users a slightly longer collection window to allow Priority users
            # to jump into the processing loop faster.
            delay = 1.0 if is_priority else 3.0
            await asyncio.sleep(delay)
            if batch_tasks.get(user_id) == asyncio.current_task():
                del batch_tasks[user_id]
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
        try:
            await msg.edit_text(f"❌ Error processing archive: {e}")
        except:
            pass

@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"), group=1)
async def handle_password_input(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == "awaiting_archive_password":
        password = message.text.strip()
        data = get_data(user_id)
        archive_path = data.get("archive_path")
        msg_id = data.get("archive_msg_id")
        orig_state = data.get("archive_state")

        try:
            msg = await client.get_messages(user_id, msg_id)
            await msg.edit_text("⏳ **Attempting to extract with password...**")
            await process_extracted_archive(client, user_id, archive_path, msg, orig_state, password)
        except Exception as e:
            logger.error(f"Error handling password: {e}")
            await message.reply_text(f"Error: {e}")

        update_data(user_id, "archive_path", None)
        update_data(user_id, "archive_msg_id", None)
        update_data(user_id, "archive_state", None)
        set_state(user_id, orig_state)

        raise StopPropagation

    raise ContinuePropagation

async def process_extracted_archive(client, user_id, archive_path, msg, state, password=None):
    await msg.edit_text("📦 **Extracting Archive...**\n\nPlease wait.")

    extract_dir = f"{archive_path}_extracted"
    success = await extract_archive(archive_path, extract_dir, password)

    if not success:
        await msg.edit_text("❌ **Extraction Failed!**\n\nThe archive might be corrupted or the password was incorrect.")
        if os.path.exists(archive_path):
            os.remove(archive_path)
        return

    valid_exts = [".mkv", ".mp4", ".avi", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".srt", ".ass", ".vtt", ".mp3", ".flac", ".m4a", ".wav"]
    extracted_files = []

    for root, dirs, files in os.walk(extract_dir):
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
        return

    await msg.edit_text(f"✅ **Extraction Complete!**\n\nFound {len(extracted_files)} media file(s). Processing...")

    import shutil
    import uuid
    from utils.queue_manager import queue_manager
    from plugins.process import process_file

    for file_path in extracted_files:
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        metadata = analyze_filename(file_name)
        lang = await db.get_preferred_language(user_id)
        tmdb_data = await auto_match_tmdb(metadata, language=lang)

        if not tmdb_data:
            await client.send_message(user_id, f"⚠️ **Detection Failed for `{file_name}`**\nSkipping.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Dismiss", callback_data="cancel_rename")]]))
            continue

        quality = metadata["quality"]
        episode = metadata.get("episode", 1) or 1
        season = metadata.get("season", 1) or 1
        lang = metadata.get("language", "en")
        is_subtitle = metadata["is_subtitle"]

        default_dumb_channel = await db.get_default_dumb_channel(user_id)

        if user_id not in batch_sessions:
            batch_id = queue_manager.create_batch()
            batch_sessions[user_id] = {"batch_id": batch_id, "items": []}
            bmsg = await client.send_message(user_id, "⏳ **Sorting Files...**\nPlease wait a moment.")
            batch_status_msgs[user_id] = bmsg

        if user_id in batch_tasks:
            batch_tasks[user_id].cancel()

        is_priority = False
        if Config.PUBLIC_MODE:
            user_doc = await db.get_user(user_id)
            if user_doc and user_doc.get("is_premium"):
                plan_name = user_doc.get("premium_plan", "standard")
                config = await db.get_public_config()
                if config.get("premium_system_enabled", False):
                    plan_settings = config.get(f"premium_{plan_name}", {})
                    is_priority = plan_settings.get("features", {}).get("priority_queue", False)

        batch_id = batch_sessions[user_id]["batch_id"]
        item_id = str(uuid.uuid4())

        quality_priority = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}
        sort_key = ((0, season, episode[0] if isinstance(episode, list) else episode) if tmdb_data["type"] == "series" else (1, quality_priority.get(quality, 4), 0))
        display_name = f"S{season:02d}{format_episode_str(episode)}" if tmdb_data["type"] == "series" else f"{quality}"

        from pyrogram.types import Message
        import random
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
            "extract_dir": extract_dir,
            "specials": metadata.get("specials", []),
            "codec": metadata.get("codec", ""),
            "audio": metadata.get("audio", ""),
        }

        batch_sessions[user_id]["items"].append({"message": dummy_msg, "data": data})

    if os.path.exists(archive_path):
        os.remove(archive_path)

    async def wait_and_process():
        try:
            delay = 1.0 if is_priority else 3.0
            await asyncio.sleep(delay)
            if batch_tasks.get(user_id) == asyncio.current_task():
                del batch_tasks[user_id]
            await process_batch(client, user_id)
        except asyncio.CancelledError:
            pass

    if user_id in batch_sessions and batch_sessions[user_id]["items"]:
        batch_tasks[user_id] = asyncio.create_task(wait_and_process())
    else:

        import shutil
        shutil.rmtree(extract_dir, ignore_errors=True)

async def handle_auto_detection(client, message):
    if message.photo:
        file_name = f"image_{message.id}.jpg"
    else:
        file_name = (
            message.document.file_name if message.document else message.video.file_name
        )

    if not file_name:
        file_name = "unknown_file.bin"

    if await is_archive(file_name):
        await handle_archive_upload(client, message, message.from_user.id, file_name, None)
        return

    user_id = message.from_user.id
    metadata = analyze_filename(file_name)
    lang = await db.get_preferred_language(user_id)
    tmdb_data = await auto_match_tmdb(metadata, language=lang)

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
    media_lang = metadata.get("language", "en")

    default_dumb_channel = await db.get_default_dumb_channel(user_id)

    is_priority = False
    if Config.PUBLIC_MODE:
        user_doc = await db.get_user(user_id)
        if user_doc and user_doc.get("is_premium"):
            plan_name = user_doc.get("premium_plan", "standard")
            config = await db.get_public_config()
            if config.get("premium_system_enabled", False):
                plan_settings = config.get(f"premium_{plan_name}", {})
                is_priority = plan_settings.get("features", {}).get("priority_queue", False)

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

    quality_priority = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}

    sort_key = (
        (0, season, episode[0] if isinstance(episode, list) else episode)
        if tmdb_data["type"] == "series"
        else (1, quality_priority.get(quality, 4), 0)
    )
    display_name = (
        f"S{season:02d}{format_episode_str(episode)}"
        if tmdb_data["type"] == "series"
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
        "specials": metadata.get("specials", []),
        "codec": metadata.get("codec", ""),
        "audio": metadata.get("audio", ""),
    }
    batch_sessions[user_id]["items"].append({"message": message, "data": data})

    async def wait_and_process():
        try:
            delay = 1.0 if is_priority else 3.0
            await asyncio.sleep(delay)
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

    templates = await db.get_filename_templates(user_id)
    template_key = fs["type"] if not fs["is_subtitle"] else f"subtitles_{fs['type']}"
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
    media_type = sd.get("type")

    text = f"📄 **File:** `{fs['original_name']}`\n\n"

    templates = await db.get_filename_templates(user_id)
    template_key = media_type if not is_sub else f"subtitles_{media_type}"
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
        except Exception:
            pass
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^season_change_(\d+)$"))
async def handle_season_change_prompt(client, callback_query):
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
    await callback_query.answer()
    msg_id = int(callback_query.data.split("_")[2])

    if msg_id in file_sessions:
        fs = file_sessions.pop(msg_id)
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

@Client.on_callback_query(filters.regex(r"^ch_codec_") & auth_filter)
async def handle_change_codec(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current = fs.get("codec", "")

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

    text = f"✅ None" if not current else "None"
    buttons.append([InlineKeyboardButton(text, callback_data=f"set_codec_none_{msg_id}")])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"back_confirm_{msg_id}")])

    try:
        await callback_query.message.edit_text(
            "📼 **Select Codec:**\nChoose a codec for the template:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass

@Client.on_callback_query(filters.regex(r"^set_codec_") & auth_filter)
async def handle_set_codec(client, callback_query):
    parts = callback_query.data.split("_")
    codec = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    if codec == "none":
        file_sessions[msg_id]["codec"] = ""
    else:
        file_sessions[msg_id]["codec"] = codec

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^ch_audio_") & auth_filter)
async def handle_change_audio(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current = fs.get("audio", "")

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

    text = f"✅ None" if not current else "None"
    buttons.append([InlineKeyboardButton(text, callback_data=f"set_audio_none_{msg_id}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"back_confirm_{msg_id}")])

    try:
        await callback_query.message.edit_text(
            "🔊 **Select Audio:**\nChoose an audio tag for the template:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass

@Client.on_callback_query(filters.regex(r"^set_audio_") & auth_filter)
async def handle_set_audio(client, callback_query):
    parts = callback_query.data.split("_")
    audio = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    if audio == "none":
        file_sessions[msg_id]["audio"] = ""
    else:
        file_sessions[msg_id]["audio"] = audio

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^ch_specials_") & auth_filter)
async def handle_change_specials(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current = fs.get("specials", [])

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

    buttons.append([
        InlineKeyboardButton("❌ Clear All", callback_data=f"clear_spc_{msg_id}"),
        InlineKeyboardButton("✅ Done", callback_data=f"back_confirm_{msg_id}")
    ])

    try:
        await callback_query.message.edit_text(
            "🎬 **Select Specials:**\nToggle specials for the template (multiple allowed):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass

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

    buttons.append([
        InlineKeyboardButton("❌ Clear All", callback_data=f"clear_spc_{msg_id}"),
        InlineKeyboardButton("✅ Done", callback_data=f"back_confirm_{msg_id}")
    ])

    try:
        await callback_query.message.edit_text(
            "🎬 **Select Specials:**\nToggle specials for the template (multiple allowed):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass

@Client.on_callback_query(filters.regex(r"^clear_spc_") & auth_filter)
async def handle_clear_specials(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    file_sessions[msg_id]["specials"] = []

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)

@Client.on_callback_query(filters.regex(r"^edit_system_filename$"))
async def edit_system_filename_template(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id

    set_state(user_id, "awaiting_system_filename")
    try:
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
    except MessageNotModified:
        pass

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
