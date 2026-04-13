# --- Imports ---
from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
from utils.log import get_logger
import math
import datetime
from bson.objectid import ObjectId

logger = get_logger("plugins.myfiles")

_mf_debounce = {}

def _debounce_mf(user_id: int, callback_id: str) -> bool:
    """Returns True if this callback should be skipped (rapid-fire duplicate)."""
    import time as _t
    key = f"{user_id}:{callback_id}"
    now = _t.time()
    last = _mf_debounce.get(key, 0)
    if now - last < 0.5:
        return True
    _mf_debounce[key] = now
    return False

# === Helper Functions ===

async def safe_edit_or_send(client, callback_query, text, markup, photo=None):
    """
    Handles transition between media messages and text messages gracefully.
    If it's a transition between text <-> media, or different aspect ratio medias,
    it uses a Send-Then-Delete approach.
    """
    try:
        if photo:
            # We are transitioning TO a photo message
            if callback_query.message.photo:
                # Editing photo to photo - wait, actually we are sending photo
                from pyrogram.types import InputMediaPhoto
                try:
                    await callback_query.message.edit_media(
                        media=InputMediaPhoto(photo, caption=text),
                        reply_markup=markup
                    )
                except MessageNotModified:
                    pass
                except Exception:
                    # Send then delete
                    new_msg = await client.send_photo(chat_id=callback_query.message.chat.id, photo=photo, caption=text, reply_markup=markup)
                    try:
                        await callback_query.message.delete()
                    except Exception:
                        pass
            else:
                # Text to Photo: Send new, then delete old
                new_msg = await client.send_photo(chat_id=callback_query.message.chat.id, photo=photo, caption=text, reply_markup=markup)
                try:
                    await callback_query.message.delete()
                except Exception:
                    pass
        else:
            # We are transitioning TO a text message
            if callback_query.message.photo:
                # Photo to Text: Send new, then delete old
                new_msg = await client.send_message(chat_id=callback_query.message.chat.id, text=text, reply_markup=markup)
                try:
                    await callback_query.message.delete()
                except Exception:
                    pass
            else:
                # Text to Text: Just edit
                try:
                    await callback_query.message.edit_text(text, reply_markup=markup)
                except MessageNotModified:
                    pass
    except Exception as e:
        logger.error(f"Error in safe_edit_or_send: {e}")

async def get_query_and_title(user_id: int, back_data: str):
    """
    Parses structural view callbacks and returns (filter_query, menu_title).
    Used to DRY up pagination and send-all logic.
    """
    if back_data == "myfiles_main":
        filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
        title = "🕒 **Recent Files**"
    elif back_data.startswith("myfiles_cat_"):
        folder_type = back_data.replace("myfiles_cat_", "")
        filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
        title = f"📁 **{folder_type.capitalize()} Folders**"
    elif back_data.startswith("myfiles_folder_"):
        folder_id = back_data.replace("myfiles_folder_", "")
        filter_query = {"user_id": user_id, "folder_id": ObjectId(folder_id)} if Config.PUBLIC_MODE else {"folder_id": ObjectId(folder_id)}
        folder = await db.folders.find_one({"_id": ObjectId(folder_id)})
        title = f"📁 **{folder['name'] if folder else 'Folder'}**"
    elif back_data.startswith("mf_sea_"):
        parts = back_data.replace("mf_sea_", "").split("_")
        folder_id = parts[0]
        season = parts[1]
        filter_query = {"user_id": user_id, "folder_id": ObjectId(folder_id)} if Config.PUBLIC_MODE else {"folder_id": ObjectId(folder_id)}
        folder = await db.folders.find_one({"_id": ObjectId(folder_id)})

        if season.isdigit():
            season_val = int(season)
            str_season_val = str(season_val)
            zfill_season_val = str_season_val.zfill(2)
            filter_query["$or"] = [
                {"season": season_val},
                {"season": str_season_val},
                {"season": zfill_season_val},
                {"season": f"S{str_season_val}"},
                {"season": f"S{zfill_season_val}"},
                {"season": f"s{str_season_val}"},
                {"season": f"s{zfill_season_val}"},
                {"guess_data.season": season_val},
                {"guess_data.season": {"$in": [season_val]}},
                {"tmdb_data.season": season_val},
                {"tmdb_data.season": str_season_val},
                {"tmdb_data.season": zfill_season_val},
                {"file_name": {"$regex": f"[sS]0?{season_val}\\b"}},
            ]
        else:
            filter_query["$and"] = [
                {"season": {"$exists": False}},
                {"guess_data.season": {"$exists": False}},
                {"tmdb_data.season": {"$exists": False}},
                {"file_name": {"$not": {"$regex": r"[sS]\d{1,2}"}}}
            ]

        title = f"📁 **{folder['name'] if folder else 'Folder'} - Season {season}**"
    else:
        filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
        title = "🕒 **Files**"

    return filter_query, title

async def set_myfiles_state(user_id: int, state_dict: dict):
    if not state_dict:
        await db.users.update_one({"user_id": user_id}, {"$unset": {"myfiles_state": ""}})
    else:
        await db.users.update_one({"user_id": user_id}, {"$set": {"myfiles_state": state_dict}}, upsert=True)

async def get_myfiles_state(user_id: int) -> dict:
    doc = await db.users.find_one({"user_id": user_id})
    if doc and "myfiles_state" in doc:
        return doc["myfiles_state"]
    return {}

async def get_myfiles_main_menu(user_id: int):
    config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})

    if Config.PUBLIC_MODE:
        perm_count = await db.files.count_documents({"user_id": user_id, "status": "permanent"})
        temp_count = await db.files.count_documents({"user_id": user_id, "status": "temporary"})

        user_doc = await db.get_user(user_id)
        plan = user_doc.get("premium_plan", "standard") if user_doc and user_doc.get("is_premium") else "free"

        limits = config.get("myfiles_limits", {}).get(plan, {})
        perm_limit = limits.get("permanent_limit", 50)

        limit_str = str(perm_limit) if perm_limit != -1 else "Unlimited"

        plan_emoji = {"free": "🆓", "standard": "⭐", "deluxe": "💎"}.get(plan, "")
        plan_label = f"{plan_emoji} {plan.capitalize()}"

        text = (
            "📁 **MyFiles**\n"
            "__Your personal media vault. Permanent files stick around — temp files vanish after use.__\n\n"
            f"**Plan** · `{plan_label}`\n"
            f"**Permanent Storage** · `{perm_count} / {limit_str}` files\n"
            f"**Temporary Storage** · `{temp_count}` files\n\n"
            "What are you looking for?"
        )
    else:
        perm_count = await db.files.count_documents({"status": "permanent"})
        temp_count = await db.files.count_documents({"status": "temporary"})

        limits = config.get("myfiles_limits", {}).get("global", {})
        perm_limit = limits.get("permanent_limit", -1)

        limit_str = str(perm_limit) if perm_limit != -1 else "Unlimited"

        text = (
            "📁 **Team MyFiles**\n"
            "__Global storage across all users.__\n\n"
            f"**Permanent Storage** · `{perm_count} / {limit_str}` files\n"
            f"**Temporary Storage** · `{temp_count}` files\n\n"
            "Browse by category:"
        )

    has_movies = await db.folders.count_documents({"user_id": user_id, "type": "movies"} if Config.PUBLIC_MODE else {"type": "movies"}) > 0
    has_series = await db.folders.count_documents({"user_id": user_id, "type": "series"} if Config.PUBLIC_MODE else {"type": "series"}) > 0
    has_music = await db.folders.count_documents({"user_id": user_id, "type": "music"} if Config.PUBLIC_MODE else {"type": "music"}) > 0

    buttons = [
        [InlineKeyboardButton("🕒 Recent Files", callback_data="myfiles_cat_recent")],
    ]

    media_row = []
    if has_movies:
        media_row.append(InlineKeyboardButton("🎬 Movies", callback_data="myfiles_cat_movies"))
    if has_series:
        media_row.append(InlineKeyboardButton("📺 Series", callback_data="myfiles_cat_series"))

    if media_row:
        buttons.append(media_row)

    if has_music:
        buttons.append([InlineKeyboardButton("🎵 Music", callback_data="myfiles_cat_music")])

    buttons.append([InlineKeyboardButton("📁 Custom Folders", callback_data="myfiles_cat_custom")])
    buttons.append([InlineKeyboardButton("⚙️ Settings", callback_data="myfiles_settings")])

    return text, InlineKeyboardMarkup(buttons)

async def build_files_list_keyboard(user_id: int, filter_query: dict, page: int, limit: int = 10, back_data: str = "myfiles_main"):
    skip = page * limit

    # Check multi-select mode and sorting preference
    state_dict = await get_myfiles_state(user_id)
    multi_select = state_dict.get("multi_select", False)
    selected_files = state_dict.get("selected_files", [])
    sort_order = state_dict.get("sort_order", "newest")

    if sort_order == "oldest":
        sort_tuple = [("created_at", 1)]
    elif sort_order == "a-z":
        sort_tuple = [("file_name", 1)]
    else:
        sort_tuple = [("created_at", -1)]

    cursor = db.files.find(filter_query).sort(sort_tuple).skip(skip).limit(limit)
    files = await cursor.to_list(length=limit)
    total_files = await db.files.count_documents(filter_query)

    buttons = []

    state_dict["current_view"] = back_data
    state_dict["current_page"] = page
    await set_myfiles_state(user_id, state_dict)

    # Sort toggle and multi-select toggle
    sort_label = "↕️ Sort: Newest"
    if sort_order == "oldest":
        sort_label = "↕️ Sort: Oldest"
    elif sort_order == "a-z":
        sort_label = "↕️ Sort: A-Z"

    ms_label = "✅ Multi-Select: ON" if multi_select else "☑️ Multi-Select: OFF"

    buttons.append([
        InlineKeyboardButton(sort_label, callback_data=f"mf_st"),
        InlineKeyboardButton(ms_label, callback_data=f"mf_ms")
    ])

    for f in files:
        f_id_str = str(f['_id'])
        name = f.get("file_name", "Unknown File")
        if len(name) > 30: name = name[:27] + "..."
        status_emoji = "📌" if f.get("status") == "permanent" else "⏳"

        if multi_select:
            prefix = "🔘 " if f_id_str in selected_files else "⚪️ "
            btn_text = f"{prefix}{name}"
            callback = f"mf_ms_sel_{f_id_str}"
        else:
            btn_text = f"{status_emoji} {name}"
            callback = f"myfiles_file_{f_id_str}"

        buttons.append([InlineKeyboardButton(btn_text, callback_data=callback)])

    nav_row = []
    total_pages = math.ceil(total_files / limit) if total_files > 0 else 1

    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"mf_pg_{page-1}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))

    nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))

    if skip + limit < total_files:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"mf_pg_{page+1}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))

    buttons.append(nav_row)

    # Action buttons for the folder/category itself
    if multi_select and selected_files:
        buttons.append([
            InlineKeyboardButton(f"📂 Move Selected ({len(selected_files)})", callback_data=f"mf_ms_mov"),
            InlineKeyboardButton(f"🗑 Delete Selected ({len(selected_files)})", callback_data=f"mf_ms_del")
        ])
        buttons.append([
            InlineKeyboardButton(f"🔗 Generate Share Link ({len(selected_files)})", callback_data=f"mf_ms_sha")
        ])

    buttons.append([
        InlineKeyboardButton("📤 Send All", callback_data=f"mf_sa")
    ])

    buttons.append([InlineKeyboardButton("← Back", callback_data=f"myfiles_leave_{back_data}")])
    return buttons, total_files

@Client.on_message(filters.text & filters.private, group=-2)
async def myfiles_text_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if not Config.PUBLIC_MODE and user_id != Config.CEO_ID and user_id not in Config.ADMIN_IDS:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    state_info = await get_myfiles_state(user_id)
    state = state_info.get("state")

    if not state:
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    if state == "awaiting_folder_name":
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
                await message.reply_text(f"❌ You have reached your custom folder limit ({folder_limit}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Folders", callback_data="myfiles_cat_custom")]]))
                await set_myfiles_state(user_id, {})
                return

        await db.folders.insert_one({
            "user_id": user_id,
            "name": folder_name,
            "type": "custom",
            "created_at": datetime.datetime.utcnow()
        })

        try:
            await message.delete()
        except Exception:
            pass

        prompt_msg_id = state_info.get("prompt_msg_id")
        confirm_text = f"✅ Folder **{folder_name}** created successfully."
        confirm_markup = InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Folders", callback_data="myfiles_cat_custom")]])
        if prompt_msg_id:
            try:
                await client.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=confirm_text, reply_markup=confirm_markup)
            except Exception:
                await client.send_message(message.chat.id, confirm_text, reply_markup=confirm_markup)
        else:
            await client.send_message(message.chat.id, confirm_text, reply_markup=confirm_markup)
        await set_myfiles_state(user_id, {})

        # Stop propagation to prevent flow.py from processing this text
        from pyrogram import StopPropagation
        raise StopPropagation

    if state.startswith("awaiting_rename_"):
        import re as _re
        import time as _time

        file_id = state.replace("awaiting_rename_", "")

        state_ts = state_info.get("timestamp", 0)
        if state_ts and _time.time() - state_ts > 600:
            await set_myfiles_state(user_id, {})
            await message.reply_text("Your rename session has expired. Please try again.")
            from pyrogram import StopPropagation
            raise StopPropagation

        new_name = message.text.strip()

        if not new_name:
            await message.reply_text("Name cannot be empty. Please enter a valid name.")
            from pyrogram import StopPropagation
            raise StopPropagation

        if len(new_name) > 255:
            await message.reply_text("Name is too long (max 255 characters). Please enter a shorter name.")
            from pyrogram import StopPropagation
            raise StopPropagation

        if _re.search(r'[<>:"/\\|?*\x00-\x1f]', new_name):
            await message.reply_text("Name contains invalid characters. Please avoid: < > : \" / \\ | ? *")
            from pyrogram import StopPropagation
            raise StopPropagation

        f = await db.files.find_one({"_id": ObjectId(file_id)})
        if not f:
            await message.reply_text("File no longer exists.")
            await set_myfiles_state(user_id, {})
            from pyrogram import StopPropagation
            raise StopPropagation

        await db.files.update_one({"_id": ObjectId(file_id)}, {"$set": {"file_name": new_name}})

        # Delete user's input message for clean chat
        try:
            await message.delete()
        except Exception:
            pass

        # Edit the bot's prompt message with confirmation
        prompt_msg_id = state_info.get("prompt_msg_id")
        prompt_chat_id = state_info.get("prompt_chat_id", message.chat.id)
        confirmation_text = f"✅ File renamed to `{new_name}`."
        confirmation_markup = InlineKeyboardMarkup([[InlineKeyboardButton("← Back to File", callback_data=f"myfiles_file_{file_id}")]])
        if prompt_msg_id:
            try:
                await client.edit_message_text(
                    chat_id=prompt_chat_id,
                    message_id=prompt_msg_id,
                    text=confirmation_text,
                    reply_markup=confirmation_markup,
                )
            except Exception:
                await client.send_message(message.chat.id, confirmation_text, reply_markup=confirmation_markup)
        else:
            await client.send_message(message.chat.id, confirmation_text, reply_markup=confirmation_markup)

        await set_myfiles_state(user_id, {})

        from pyrogram import StopPropagation
        raise StopPropagation

    from pyrogram import ContinuePropagation
    raise ContinuePropagation

# === Handlers ===
@Client.on_message(filters.command("myfiles") & filters.private)
async def myfiles_command(client: Client, message: Message):
    user_id = message.from_user.id
    if not Config.PUBLIC_MODE and user_id != Config.CEO_ID and user_id not in Config.ADMIN_IDS:
        return

    # Check if MyFiles system is enabled
    is_admin = (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS)
    if not is_admin:
        myfiles_enabled = await db.get_setting("myfiles_enabled", default=False)
        if not myfiles_enabled:
            await message.reply_text("📁 **MyFiles™** is currently disabled by the administrator.")
            return

    text, markup = await get_myfiles_main_menu(user_id)
    await message.reply_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^(myfiles_|mf_mov_|mf_df_|mf_pg_|mf_st|mf_ms|mf_sea_|mf_sa|settings_cat_|stg_)"))
async def myfiles_callback(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    # Check if MyFiles system is enabled (allow admins through)
    is_admin = (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS)
    if not is_admin and not data.startswith("stg_") and not data.startswith("settings_cat_"):
        myfiles_enabled = await db.get_setting("myfiles_enabled", default=False)
        if not myfiles_enabled:
            await callback_query.answer("MyFiles™ is currently disabled.", show_alert=True)
            return

    if _debounce_mf(user_id, data):
        try:
            await callback_query.answer()
        except Exception:
            pass
        return

    # Fast-dismiss loading spinner except where we specifically want an alert.
    # We will answer below if we need a custom text.
    try:
        if not (data.startswith("myfiles_send_") or data.startswith("mf_sa_") or data.startswith("myfiles_delfile_") or data.startswith("myfiles_del_folder_") or data.startswith("mf_mov_") or data.startswith("mf_df_") or data.startswith("mf_ms_mov_") or data.startswith("mf_ms_del_")):
            await callback_query.answer()
    except Exception:
        pass

    if data.startswith("mf_st"):
        state_dict = await get_myfiles_state(user_id)
        current_sort = state_dict.get("sort_order", "newest")
        if current_sort == "newest":
            next_sort = "oldest"
        elif current_sort == "oldest":
            next_sort = "a-z"
        else:
            next_sort = "newest"

        state_dict["sort_order"] = next_sort
        await set_myfiles_state(user_id, state_dict)

        page = state_dict.get("current_page", 0)
        back_data = state_dict.get("current_view", "myfiles_cat_recent")
        callback_query.data = f"mf_pg_{page}_{back_data}"
        await myfiles_callback(client, callback_query)
        return

    if data == "mf_ms":
        state_dict = await get_myfiles_state(user_id)
        multi_select = state_dict.get("multi_select", False)
        state_dict["multi_select"] = not multi_select
        if not multi_select:
            state_dict["selected_files"] = []

        await set_myfiles_state(user_id, state_dict)

        page = state_dict.get("current_page", 0)
        back_data = state_dict.get("current_view", "myfiles_cat_recent")
        callback_query.data = f"mf_pg_{page}_{back_data}"
        await myfiles_callback(client, callback_query)
        return

    if data.startswith("mf_ms_sel_"):
        f_id_str = data.replace("mf_ms_sel_", "")
        state_dict = await get_myfiles_state(user_id)
        selected_files = state_dict.get("selected_files", [])

        if f_id_str in selected_files:
            selected_files.remove(f_id_str)
        else:
            selected_files.append(f_id_str)

        state_dict["selected_files"] = selected_files
        await set_myfiles_state(user_id, state_dict)

        # Flicker-Free Multi-Select UX: Just update the keyboard
        page = state_dict.get("current_page", 0)
        back_data = state_dict.get("current_view", "myfiles_cat_recent")
        filter_query, _ = await get_query_and_title(user_id, back_data)

        # Build the new keyboard markup
        buttons, _ = await build_files_list_keyboard(user_id, filter_query, page=page, back_data=back_data)

        try:
            await callback_query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass

        return

    if data == "mf_ms_del":
        state_dict = await get_myfiles_state(user_id)
        selected_files = state_dict.get("selected_files", [])

        if not selected_files:
            await callback_query.answer("No files selected.", show_alert=True)
            return

        object_ids = [ObjectId(fid) for fid in selected_files]
        await db.files.delete_many({"_id": {"$in": object_ids}})

        state_dict["multi_select"] = False
        state_dict["selected_files"] = []
        await set_myfiles_state(user_id, state_dict)

        await callback_query.answer(f"Deleted {len(object_ids)} files.", show_alert=True)

        back_data = state_dict.get("current_view", "myfiles_cat_recent")
        callback_query.data = back_data if back_data != "myfiles_main" else "myfiles_cat_recent"
        await myfiles_callback(client, callback_query)
        return

    if data.startswith("myfiles_leave_"):
        back_data = data.replace("myfiles_leave_", "")
        state_dict = await get_myfiles_state(user_id)
        if state_dict.get("multi_select", False):
            state_dict["multi_select"] = False
            state_dict["selected_files"] = []
            await set_myfiles_state(user_id, state_dict)

        if back_data.startswith("mf_sea_"):
            parts = back_data.replace("mf_sea_", "").split("_")
            back_data = f"myfiles_folder_{parts[0]}"

        callback_query.data = back_data
        await myfiles_callback(client, callback_query)
        return

    if data == "mf_ms_sha":
        state_dict = await get_myfiles_state(user_id)
        selected_files = state_dict.get("selected_files", [])

        if not selected_files:
            await callback_query.answer("No files selected.", show_alert=True)
            return

        bot_me = await client.get_me()
        bot_username = bot_me.username

        user_doc = await db.get_user(user_id)
        if Config.PUBLIC_MODE:
            plan = user_doc.get("premium_plan", "standard") if user_doc and user_doc.get("is_premium") else "free"
            config = await db.get_public_config()
        else:
            plan = "global"
            config = await db.settings.find_one({"_id": "global_settings"})

        import uuid

        user_settings = await db.get_settings(user_id)
        use_anon = user_settings.get("link_anonymity", False) if user_settings else False

        if use_anon:
            group_id = f"{uuid.uuid4().hex[:16]}"
        else:
            group_id = f"{user_id}_{int(datetime.datetime.utcnow().timestamp())}"

        group_doc = {
            "group_id": group_id,
            "user_id": user_id,
            "files": selected_files,
            "created_at": datetime.datetime.utcnow()
        }

        # Add expiry if auto-expire links is enabled
        auto_expire = user_settings.get("privacy_auto_expire_links", False) if user_settings else False
        if auto_expire:
            dur = user_settings.get("privacy_link_expiry_duration", "24h") if user_settings else "24h"
            dur_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
            hours = dur_map.get(dur, 24)
            group_doc["expires_at"] = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)

        await db.db.file_groups.insert_one(group_doc)

        deep_link = f"https://t.me/{bot_username}?start=group_{group_id}"

        text = (
            f"📦 **Batch Share Link Generated**\n\n"
            f"**Files Included:** `{len(selected_files)}` files\n"
            f"**Link:**\n`{deep_link}`\n\n"
            f"> Anyone with this link can start the bot and receive these files."
        )

        back_data = state_dict.get("current_view", "myfiles_cat_recent")

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Open Link", url=deep_link)],
            [InlineKeyboardButton("← Back", callback_data=back_data)]
        ])

        await safe_edit_or_send(client, callback_query, text, markup)

        state_dict["multi_select"] = False
        state_dict["selected_files"] = []
        await set_myfiles_state(user_id, state_dict)
        return

    if data == "mf_ms_mov":
        state_dict = await get_myfiles_state(user_id)
        cursor = db.folders.find({"user_id": user_id, "type": "custom"}).sort("name", 1)
        folders = await cursor.to_list(length=None)

        text = "📂 **Batch Move Files**\n\nSelect a folder to move the selected files to:"
        buttons = [
            [InlineKeyboardButton("🧹 Remove from Folder", callback_data=f"mf_ms_domov_None")]
        ]

        for folder in folders:
            buttons.append([InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"mf_ms_domov_{str(folder['_id'])}")])

        back_data = state_dict.get("current_view", "myfiles_cat_recent")
        buttons.append([InlineKeyboardButton("← Back", callback_data=back_data)])

        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data.startswith("mf_ms_domov_"):
        folder_id = data.replace("mf_ms_domov_", "")

        state_dict = await get_myfiles_state(user_id)
        back_data = state_dict.get("current_view", "myfiles_cat_recent")
        selected_files = state_dict.get("selected_files", [])

        if not selected_files:
            await callback_query.answer("No files selected.", show_alert=True)
            return

        object_ids = [ObjectId(fid) for fid in selected_files]

        if folder_id == "None":
            await db.files.update_many({"_id": {"$in": object_ids}}, {"$set": {"folder_id": None}})
        else:
            await db.files.update_many({"_id": {"$in": object_ids}}, {"$set": {"folder_id": ObjectId(folder_id)}})

        # Clear selection and turn off multi-select
        state_dict["multi_select"] = False
        state_dict["selected_files"] = []
        await set_myfiles_state(user_id, state_dict)

        await callback_query.answer(f"Moved {len(object_ids)} files.", show_alert=True)

        if back_data == "myfiles_main":
            callback_query.data = "myfiles_cat_recent"
        else:
            callback_query.data = back_data

        await myfiles_callback(client, callback_query)
        return

    if not Config.PUBLIC_MODE and user_id != Config.CEO_ID and user_id not in Config.ADMIN_IDS:
        await callback_query.answer("Access Denied", show_alert=True)
        return

    # Only update last_menu if it's a structural navigation callback
    if data in ["myfiles_main", "myfiles_cat_recent", "myfiles_cat_movies", "myfiles_cat_series", "myfiles_cat_custom"] or data.startswith("myfiles_folder_") or data.startswith("myfiles_page_"):
        state_dict = await get_myfiles_state(user_id)
        state_dict["last_menu"] = data
        await set_myfiles_state(user_id, state_dict)

    if data == "myfiles_main":
        text, markup = await get_myfiles_main_menu(user_id)
        await safe_edit_or_send(client, callback_query, text, markup)
        return

    if data == "myfiles_settings":
        text = "⚙️ **Settings**\n\nSelect a category to configure:"

        buttons = [
            [InlineKeyboardButton("🎬 File Processing", callback_data="settings_cat_processing")],
            [InlineKeyboardButton("📁 MyFiles Preferences", callback_data="settings_cat_myfiles")],
            [InlineKeyboardButton("🔔 Notifications", callback_data="settings_cat_notifications")],
            [InlineKeyboardButton("🖥️ Display", callback_data="settings_cat_display")],
        ]

        user_doc = await db.get_user(user_id)
        is_premium = user_doc.get("is_premium", False) if user_doc else False
        plan = user_doc.get("premium_plan", "standard") if is_premium else "free"
        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        plan_features = config.get(f"premium_{plan}", {}).get("features", {})
        is_global_admin = (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS)

        if plan_features.get("privacy_settings", False) or plan == "global" or is_global_admin:
            buttons.append([InlineKeyboardButton("🔒 Privacy Settings", callback_data="settings_cat_privacy")])

        buttons.append([InlineKeyboardButton("🗑️ Clear Permanent Storage", callback_data="myfiles_clear_perm")])
        buttons.append([InlineKeyboardButton("← Back to MyFiles", callback_data="myfiles_main")])

        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data == "myfiles_toggle_grouping":
        if Config.PUBLIC_MODE:
            user_doc = await db.get_user(user_id)
            current = user_doc.get("group_series_by_season", True)
            await db.users.update_one({"user_id": user_id}, {"$set": {"group_series_by_season": not current}})
        else:
            config = await db.settings.find_one({"_id": "global_settings"})
            current = config.get("group_series_by_season", True)
            await db.settings.update_one({"_id": "global_settings"}, {"$set": {"group_series_by_season": not current}})

        await callback_query.answer("Grouping setting toggled.", show_alert=False)
        callback_query.data = "settings_cat_myfiles"
        await myfiles_callback(client, callback_query)
        return

    # === SETTINGS CATEGORY HANDLERS ===

    if data == "settings_cat_processing":
        s = await db.get_settings(user_id)
        quality = s.get("default_quality", "720p") if s else "720p"
        auto_tmdb = s.get("auto_tmdb_match", True) if s else True
        def_type = s.get("default_media_type", "auto") if s else "auto"
        preserve = s.get("preserve_original_filename", False) if s else False

        type_labels = {"auto": "Auto-Detect", "movie": "Movie", "series": "Series", "general": "General"}

        text = (
            "🎬 **File Processing Settings**\n\n"
            f"**Default Quality:** `{quality}`\n"
            f"**Auto TMDb Match:** {'ON' if auto_tmdb else 'OFF'}\n"
            f"**Default Media Type:** {type_labels.get(def_type, def_type)}\n"
            f"**Preserve Original Filename:** {'ON' if preserve else 'OFF'}"
        )
        buttons = [
            [InlineKeyboardButton(f"📐 Quality: {quality}", callback_data="stg_sel_default_quality")],
            [InlineKeyboardButton(f"🔍 Auto TMDb: {'✅ ON' if auto_tmdb else '❌ OFF'}", callback_data="stg_toggle_auto_tmdb_match")],
            [InlineKeyboardButton(f"📂 Default Type: {type_labels.get(def_type, def_type)}", callback_data="stg_sel_default_media_type")],
            [InlineKeyboardButton(f"📎 Preserve Filename: {'✅ ON' if preserve else '❌ OFF'}", callback_data="stg_toggle_preserve_original_filename")],
            [InlineKeyboardButton("← Back to Settings", callback_data="myfiles_settings")]
        ]
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data == "settings_cat_myfiles":
        s = await db.get_settings(user_id)
        auto_perm = s.get("myfiles_auto_permanent", True) if s else True

        grouping_enabled = True
        if Config.PUBLIC_MODE:
            user_doc = await db.get_user(user_id)
            grouping_enabled = user_doc.get("group_series_by_season", True)
        else:
            gconfig = await db.settings.find_one({"_id": "global_settings"})
            grouping_enabled = gconfig.get("group_series_by_season", True) if gconfig else True

        sort_order = s.get("myfiles_default_sort", "newest") if s else "newest"
        per_page = s.get("myfiles_files_per_page", 10) if s else 10
        notify_expiry = s.get("myfiles_notify_expiry", False) if s else False

        sort_labels = {"newest": "Newest First", "oldest": "Oldest First", "a-z": "A-Z"}

        text = (
            "📁 **MyFiles Preferences**\n\n"
            f"**Auto-Permanent:** {'ON' if auto_perm else 'OFF'} — Files auto-consume permanent storage slots\n"
            f"**Group by Season:** {'ON' if grouping_enabled else 'OFF'} — Group series files into virtual season folders\n"
            f"**Sort Order:** {sort_labels.get(sort_order, sort_order)}\n"
            f"**Files Per Page:** {per_page}\n"
            f"**Expiry Notification:** {'ON' if notify_expiry else 'OFF'}"
        )
        buttons = [
            [InlineKeyboardButton(f"📌 Auto-Permanent: {'✅ ON' if auto_perm else '❌ OFF'}", callback_data="myfiles_toggle_auto")],
            [InlineKeyboardButton(f"📺 Group by Season: {'✅ ON' if grouping_enabled else '❌ OFF'}", callback_data="myfiles_toggle_grouping")],
            [InlineKeyboardButton(f"🔀 Sort: {sort_labels.get(sort_order, sort_order)}", callback_data="stg_sel_myfiles_default_sort")],
            [InlineKeyboardButton(f"📄 Files/Page: {per_page}", callback_data="stg_sel_myfiles_files_per_page")],
            [InlineKeyboardButton(f"⏰ Expiry Alert: {'✅ ON' if notify_expiry else '❌ OFF'}", callback_data="stg_toggle_myfiles_notify_expiry")],
            [InlineKeyboardButton("← Back to Settings", callback_data="myfiles_settings")]
        ]
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data == "settings_cat_notifications":
        s = await db.get_settings(user_id)
        notify_complete = s.get("notify_process_complete", True) if s else True
        notify_batch = s.get("notify_batch_summary", True) if s else True
        notify_quota = s.get("notify_quota_warning", True) if s else True
        notify_digest = s.get("notify_daily_digest", False) if s else False

        text = (
            "🔔 **Notification Settings**\n\n"
            f"**Process Completion:** {'ON' if notify_complete else 'OFF'} — Notify when file processing finishes\n"
            f"**Batch Summary:** {'ON' if notify_batch else 'OFF'} — Show summary after batch processing\n"
            f"**Quota Warning:** {'ON' if notify_quota else 'OFF'} — Alert when approaching usage limits\n"
            f"**Daily Digest:** {'ON' if notify_digest else 'OFF'} — Daily summary of activity"
        )
        buttons = [
            [InlineKeyboardButton(f"✅ Process Complete: {'✅ ON' if notify_complete else '❌ OFF'}", callback_data="stg_toggle_notify_process_complete")],
            [InlineKeyboardButton(f"📊 Batch Summary: {'✅ ON' if notify_batch else '❌ OFF'}", callback_data="stg_toggle_notify_batch_summary")],
            [InlineKeyboardButton(f"⚠️ Quota Warning: {'✅ ON' if notify_quota else '❌ OFF'}", callback_data="stg_toggle_notify_quota_warning")],
            [InlineKeyboardButton(f"📅 Daily Digest: {'✅ ON' if notify_digest else '❌ OFF'}", callback_data="stg_toggle_notify_daily_digest")],
            [InlineKeyboardButton("← Back to Settings", callback_data="myfiles_settings")]
        ]
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data == "settings_cat_display":
        s = await db.get_settings(user_id)
        compact = s.get("display_compact_list", False) if s else False
        show_sizes = s.get("display_show_file_sizes", True) if s else True
        show_dates = s.get("display_show_dates", True) if s else True
        show_icons = s.get("display_show_type_icons", True) if s else True
        show_poster = s.get("display_show_poster", False) if s else False

        text = (
            "🖥️ **Display Settings**\n\n"
            f"**Compact List:** {'ON' if compact else 'OFF'} — Show condensed file listings\n"
            f"**Show File Sizes:** {'ON' if show_sizes else 'OFF'} — Display file size info\n"
            f"**Show Upload Dates:** {'ON' if show_dates else 'OFF'} — Display upload timestamps\n"
            f"**File Type Icons:** {'ON' if show_icons else 'OFF'} — Show type indicators\n"
            f"**Show Poster:** {'ON' if show_poster else 'OFF'} — Display movie/series poster in file details"
        )
        buttons = [
            [InlineKeyboardButton(f"📋 Compact List: {'✅ ON' if compact else '❌ OFF'}", callback_data="stg_toggle_display_compact_list")],
            [InlineKeyboardButton(f"📏 File Sizes: {'✅ ON' if show_sizes else '❌ OFF'}", callback_data="stg_toggle_display_show_file_sizes")],
            [InlineKeyboardButton(f"📅 Upload Dates: {'✅ ON' if show_dates else '❌ OFF'}", callback_data="stg_toggle_display_show_dates")],
            [InlineKeyboardButton(f"🏷️ Type Icons: {'✅ ON' if show_icons else '❌ OFF'}", callback_data="stg_toggle_display_show_type_icons")],
            [InlineKeyboardButton(f"🖼️ Show Poster: {'✅ ON' if show_poster else '❌ OFF'}", callback_data="stg_toggle_display_show_poster")],
            [InlineKeyboardButton("← Back to Settings", callback_data="myfiles_settings")]
        ]
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data == "settings_cat_privacy" or data == "myfiles_privacy_settings":
        user_doc = await db.get_user(user_id)
        is_premium = user_doc.get("is_premium", False) if user_doc else False
        plan = user_doc.get("premium_plan", "standard") if is_premium else "free"

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        plan_features = config.get(f"premium_{plan}", {}).get("features", {})
        privacy_feat = plan_features.get("privacy", {})

        is_global_admin = (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS)

        if not plan_features.get("privacy_settings", False) and plan != "global" and not is_global_admin:
            await callback_query.answer("Your current plan does not have access to Privacy Settings.", show_alert=True)
            return

        s = await db.get_settings(user_id)

        share_name = True
        if s and "share_display_name" in s:
            share_name = s["share_display_name"]
        elif is_premium:
            share_name = False

        hide_forward = s.get("hide_forward_tags", False) if s else False
        link_anon = s.get("link_anonymity", False) if s else False
        hide_user = s.get("privacy_hide_username", False) if s else False
        auto_expire = s.get("privacy_auto_expire_links", False) if s else False
        expire_dur = s.get("privacy_link_expiry_duration", "24h") if s else "24h"

        text = "🔒 **Privacy Settings**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        buttons = []
        has_plan_features = False

        if privacy_feat.get("hide_display_name", False) or plan == "global" or is_global_admin:
            has_plan_features = True
            text += f"> 👤 **Display Name:** {'✅ ON' if share_name else '❌ OFF'}\n> __Show your name on shared files__\n"
            buttons.append([InlineKeyboardButton(f"👤 Display Name: {'✅ ON' if share_name else '❌ OFF'}", callback_data="myfiles_toggle_share_name")])

        if privacy_feat.get("hide_forward_tags", False) or plan == "global" or is_global_admin:
            has_plan_features = True
            text += f"> 🏷️ **Forward Tags:** {'✅ Hidden' if hide_forward else '❌ Visible'}\n> __Remove 'Forwarded from' on shares__\n"
            buttons.append([InlineKeyboardButton(f"🏷️ Forward Tags: {'✅ Hidden' if hide_forward else '❌ Visible'}", callback_data="myfiles_toggle_hide_fwd")])

        if privacy_feat.get("link_anonymity", False) or plan == "global" or is_global_admin:
            has_plan_features = True
            text += f"> 🔗 **Link Anonymity:** {'✅ ON' if link_anon else '❌ OFF'}\n> __Use anonymous hash in share links__\n"
            buttons.append([InlineKeyboardButton(f"🔗 Link Anonymity: {'✅ ON' if link_anon else '❌ OFF'}", callback_data="myfiles_toggle_link_anon")])

        if has_plan_features:
            text += "\n━━━━━━━━━━━━━━━━━━━━\n\n"

        text += f"> 🙈 **Hide Username:** {'✅ ON' if hide_user else '❌ OFF'}\n> __Hide username on shared content__\n"
        buttons.append([InlineKeyboardButton(f"🙈 Hide Username: {'✅ ON' if hide_user else '❌ OFF'}", callback_data="stg_toggle_privacy_hide_username")])

        text += f"> ⏳ **Auto-Expire Links:** {'✅ ON' if auto_expire else '❌ OFF'}\n> __Share links expire automatically__\n"
        buttons.append([InlineKeyboardButton(f"⏳ Auto-Expire: {'✅ ON' if auto_expire else '❌ OFF'}", callback_data="stg_toggle_privacy_auto_expire_links")])

        if auto_expire:
            dur_labels = {"1h": "1 Hour", "6h": "6 Hours", "24h": "24 Hours", "7d": "7 Days", "30d": "30 Days"}
            text += f"> ⏱️ **Expiry Duration:** `{dur_labels.get(expire_dur, expire_dur)}`\n"
            buttons.append([InlineKeyboardButton(f"⏱️ Expiry: {dur_labels.get(expire_dur, expire_dur)}", callback_data="stg_sel_privacy_link_expiry_duration")])

        buttons.append([InlineKeyboardButton("← Back to Settings", callback_data="myfiles_settings")])
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    # === GENERIC SETTINGS TOGGLE HANDLER ===
    if data.startswith("stg_toggle_"):
        key = data.replace("stg_toggle_", "")
        toggle_defaults = {
            "auto_tmdb_match": True, "preserve_original_filename": False,
            "myfiles_notify_expiry": False,
            "notify_process_complete": True, "notify_batch_summary": True,
            "notify_quota_warning": True, "notify_daily_digest": False,
            "display_compact_list": False, "display_show_file_sizes": True,
            "display_show_dates": True, "display_show_type_icons": True,
            "display_show_poster": False,
            "privacy_hide_username": False, "privacy_auto_expire_links": False,
        }
        if key not in toggle_defaults:
            await callback_query.answer("Unknown setting.", show_alert=True)
            return

        current = await db.get_setting(key, toggle_defaults[key], user_id)
        await db.update_setting(key, not current, user_id)
        await callback_query.answer("Setting updated.", show_alert=False)

        cat_map = {
            "auto_tmdb_match": "settings_cat_processing",
            "preserve_original_filename": "settings_cat_processing",
            "myfiles_notify_expiry": "settings_cat_myfiles",
            "notify_process_complete": "settings_cat_notifications",
            "notify_batch_summary": "settings_cat_notifications",
            "notify_quota_warning": "settings_cat_notifications",
            "notify_daily_digest": "settings_cat_notifications",
            "display_compact_list": "settings_cat_display",
            "display_show_file_sizes": "settings_cat_display",
            "display_show_dates": "settings_cat_display",
            "display_show_type_icons": "settings_cat_display",
            "display_show_poster": "settings_cat_display",
            "privacy_hide_username": "settings_cat_privacy",
            "privacy_auto_expire_links": "settings_cat_privacy",
        }
        callback_query.data = cat_map.get(key, "myfiles_settings")
        await myfiles_callback(client, callback_query)
        return

    # === GENERIC SETTINGS SELECT HANDLER ===
    if data.startswith("stg_sel_"):
        key = data.replace("stg_sel_", "")
        select_options = {
            "default_quality": {"480p": "480p", "720p": "720p", "1080p": "1080p", "2160p": "2160p (4K)", "original": "Original"},
            "default_media_type": {"auto": "Auto-Detect", "movie": "Movie", "series": "Series", "general": "General"},
            "myfiles_default_sort": {"newest": "Newest First", "oldest": "Oldest First", "a-z": "A-Z"},
            "myfiles_files_per_page": {"5": "5", "8": "8", "10": "10", "15": "15", "20": "20"},
            "privacy_link_expiry_duration": {"1h": "1 Hour", "6h": "6 Hours", "24h": "24 Hours", "7d": "7 Days", "30d": "30 Days"},
        }
        if key not in select_options:
            await callback_query.answer("Unknown setting.", show_alert=True)
            return

        options = select_options[key]
        current = await db.get_setting(key, list(options.keys())[0] if key != "myfiles_files_per_page" else "10", user_id)

        buttons = []
        for val, label in options.items():
            marker = " ✓" if str(current) == str(val) else ""
            buttons.append([InlineKeyboardButton(f"{label}{marker}", callback_data=f"stg_opt_{key}_{val}")])

        cat_back = {
            "default_quality": "settings_cat_processing", "default_media_type": "settings_cat_processing",
            "myfiles_default_sort": "settings_cat_myfiles", "myfiles_files_per_page": "settings_cat_myfiles",
            "privacy_link_expiry_duration": "settings_cat_privacy",
        }
        buttons.append([InlineKeyboardButton("← Back", callback_data=cat_back.get(key, "myfiles_settings"))])

        label_title = key.replace("_", " ").title()
        text = f"⚙️ **Select {label_title}**\n\nCurrent: `{options.get(str(current), current)}`"
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    # === GENERIC SETTINGS OPTION SELECT HANDLER ===
    if data.startswith("stg_opt_"):
        remainder = data.replace("stg_opt_", "")
        known_keys = [
            "default_quality", "default_media_type", "myfiles_default_sort",
            "myfiles_files_per_page", "privacy_link_expiry_duration",
        ]
        key = None
        value = None
        for k in known_keys:
            if remainder.startswith(k + "_"):
                key = k
                value = remainder[len(k) + 1:]
                break
        if not key:
            await callback_query.answer("Unknown option.", show_alert=True)
            return

        if key == "myfiles_files_per_page":
            value = int(value)

        await db.update_setting(key, value, user_id)
        await callback_query.answer("Setting updated.", show_alert=False)

        cat_back = {
            "default_quality": "settings_cat_processing", "default_media_type": "settings_cat_processing",
            "myfiles_default_sort": "settings_cat_myfiles", "myfiles_files_per_page": "settings_cat_myfiles",
            "privacy_link_expiry_duration": "settings_cat_privacy",
        }
        callback_query.data = cat_back.get(key, "myfiles_settings")
        await myfiles_callback(client, callback_query)
        return

    if data == "myfiles_toggle_link_anon":
        user_doc = await db.get_user(user_id)
        is_premium = user_doc.get("is_premium", False) if user_doc else False
        plan = user_doc.get("premium_plan", "standard") if is_premium else "free"

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        plan_features = config.get(f"premium_{plan}", {}).get("features", {})
        privacy_feat = plan_features.get("privacy", {})
        is_global_admin = (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS)
        if not privacy_feat.get("link_anonymity", False) and plan != "global" and not is_global_admin:
            await callback_query.answer("Your current plan does not have access to this setting.", show_alert=True)
            return

        user_settings = await db.get_settings(user_id)
        link_anon = False
        if user_settings and "link_anonymity" in user_settings:
            link_anon = user_settings["link_anonymity"]

        await db.settings.update_one({"_id": db._get_doc_id(user_id)}, {"$set": {"link_anonymity": not link_anon}}, upsert=True)
        await callback_query.answer("Privacy setting updated", show_alert=False)
        callback_query.data = "myfiles_privacy_settings"
        await myfiles_callback(client, callback_query)
        return

    if data == "myfiles_toggle_share_name":
        user_doc = await db.get_user(user_id)
        is_premium = user_doc.get("is_premium", False) if user_doc else False
        plan = user_doc.get("premium_plan", "standard") if is_premium else "free"

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        plan_features = config.get(f"premium_{plan}", {}).get("features", {})
        is_global_admin = (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS)
        if not plan_features.get("privacy_settings", False) and plan != "global" and not is_global_admin:
            await callback_query.answer("Your current plan does not have access to Privacy Settings.", show_alert=True)
            return

        user_settings = await db.get_settings(user_id)
        share_name = True
        if user_settings and "share_display_name" in user_settings:
            share_name = user_settings["share_display_name"]
        elif is_premium:
            share_name = False

        await db.settings.update_one({"_id": db._get_doc_id(user_id)}, {"$set": {"share_display_name": not share_name}}, upsert=True)
        await callback_query.answer("Privacy setting updated", show_alert=False)
        callback_query.data = "myfiles_privacy_settings"
        await myfiles_callback(client, callback_query)
        return

    if data == "myfiles_toggle_hide_fwd":
        user_doc = await db.get_user(user_id)
        is_premium = user_doc.get("is_premium", False) if user_doc else False
        plan = user_doc.get("premium_plan", "standard") if is_premium else "free"

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        plan_features = config.get(f"premium_{plan}", {}).get("features", {})
        is_global_admin = (user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS)
        if not plan_features.get("privacy_settings", False) and plan != "global" and not is_global_admin:
            await callback_query.answer("Your current plan does not have access to Privacy Settings.", show_alert=True)
            return

        user_settings = await db.get_settings(user_id)
        hide_forward = False
        if user_settings and "hide_forward_tags" in user_settings:
            hide_forward = user_settings["hide_forward_tags"]

        await db.settings.update_one({"_id": db._get_doc_id(user_id)}, {"$set": {"hide_forward_tags": not hide_forward}}, upsert=True)
        await callback_query.answer("Privacy setting updated", show_alert=False)
        callback_query.data = "myfiles_privacy_settings"
        await myfiles_callback(client, callback_query)
        return

    if data == "myfiles_toggle_auto":
        user_settings = await db.get_settings(user_id)
        auto_perm = True
        if user_settings and "myfiles_auto_permanent" in user_settings:
            auto_perm = user_settings["myfiles_auto_permanent"]

        await db.settings.update_one({"_id": db._get_doc_id(user_id)}, {"$set": {"myfiles_auto_permanent": not auto_perm}}, upsert=True)
        await callback_query.answer("Setting updated", show_alert=False)
        callback_query.data = "settings_cat_myfiles"
        await myfiles_callback(client, callback_query)
        return

    if data == "myfiles_clear_perm":
        text = "⚠️ **Warning**\n\nAre you sure you want to delete ALL your permanent files? This cannot be undone."
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Delete All", callback_data="myfiles_confirm_clear_perm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="myfiles_settings")]
        ])
        await safe_edit_or_send(client, callback_query, text, markup)
        return

    if data == "myfiles_confirm_clear_perm":
        await db.files.delete_many({"user_id": user_id, "status": "permanent"})
        await callback_query.answer("Permanent storage cleared.", show_alert=True)
        callback_query.data = "myfiles_settings"
        await myfiles_callback(client, callback_query)
        return

    if data == "myfiles_cat_recent":
        filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=0, back_data="myfiles_main")
        text = f"🕒 **Recent Files** ({total} total)\n\n📌 = Permanent | ⏳ = Temporary"
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data in ["myfiles_cat_movies", "myfiles_cat_series", "myfiles_cat_music", "myfiles_cat_custom"]:
        f_type = data.split("_")[-1]

        folder_query = {"user_id": user_id, "type": f_type} if Config.PUBLIC_MODE else {"type": f_type}
        cursor = db.folders.find(folder_query).sort("name", 1)
        folders = await cursor.to_list(length=None)

        text = f"📁 **{f_type.capitalize()} Folders**"
        buttons = []

        if f_type == "custom":
            buttons.append([InlineKeyboardButton("➕ Create New Folder", callback_data="myfiles_create_folder")])

        if not folders:
            text += "\n\nNo folders found."
        else:
            for folder in folders:
                count = await db.files.count_documents({"user_id": user_id, "folder_id": folder["_id"]})
                buttons.append([InlineKeyboardButton(f"📁 {folder['name']} ({count})", callback_data=f"myfiles_folder_{str(folder['_id'])}")])

        buttons.append([InlineKeyboardButton("← Back to MyFiles", callback_data="myfiles_main")])

        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data.startswith("myfiles_folder_"):
        folder_id = data.replace("myfiles_folder_", "")
        folder = await db.folders.find_one({"_id": ObjectId(folder_id)})
        if not folder:
            await callback_query.answer("Folder not found.", show_alert=True)
            return

        filter_query = {"user_id": user_id, "folder_id": ObjectId(folder_id)} if Config.PUBLIC_MODE else {"folder_id": ObjectId(folder_id)}

        # Check grouping setting
        if Config.PUBLIC_MODE:
            user_doc = await db.get_user(user_id)
            grouping_enabled = user_doc.get("group_series_by_season", True)
        else:
            config = await db.settings.find_one({"_id": "global_settings"})
            grouping_enabled = config.get("group_series_by_season", True)

        if folder.get('type') == 'series' and grouping_enabled:
            # Group by season
            files = await db.files.find(filter_query).to_list(length=None)
            season_counts = {}
            for f in files:
                season = "Unknown"

                # Check explicit DB season first (added in new process.py)
                if f.get("season"):
                    season = str(f.get("season"))
                else:
                    # Fallback to tmdb_data or guess_data (legacy)
                    tmdb_data = f.get("tmdb_data")
                    if tmdb_data and "season" in tmdb_data:
                        season = str(tmdb_data["season"])
                    elif f.get("guess_data") and "season" in f["guess_data"]:
                        s_data = f["guess_data"]["season"]
                        if isinstance(s_data, list):
                            season = str(s_data[0])
                        else:
                            season = str(s_data)
                    else:
                        # Final fallback: Regex parse from file_name
                        import re
                        name = f.get("file_name", "")
                        match = re.search(r'[sS](\d{1,2})', name)
                        if match:
                            season = str(int(match.group(1)))

                if season not in season_counts:
                    season_counts[season] = 0
                season_counts[season] += 1

            buttons = []
            for season in sorted(season_counts.keys(), key=lambda x: int(x) if x.isdigit() else 9999):
                buttons.append([InlineKeyboardButton(f"📁 Season {season} ({season_counts[season]})", callback_data=f"mf_sea_{folder_id}_{season}")])

            buttons.append([InlineKeyboardButton("← Back to Category", callback_data=f"myfiles_cat_{folder.get('type', 'custom')}")])
            total = sum(season_counts.values())
            text = f"📁 **{folder['name']}** ({total} files)\n\n📌 = Permanent | ⏳ = Temporary\n\nSelect a season:"

            await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
            return

        # Normal list
        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=0, back_data=f"myfiles_folder_{folder_id}")

        if folder.get('type') == 'custom':
            buttons.insert(-2, [InlineKeyboardButton("🗑️ Delete Folder", callback_data=f"myfiles_del_folder_{folder_id}")])

        text = f"📁 **{folder['name']}** ({total} files)\n\n📌 = Permanent | ⏳ = Temporary"
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data.startswith("mf_sea_"):
        parts = data.replace("mf_sea_", "").split("_")
        folder_id = parts[0]
        season = parts[1]

        folder = await db.folders.find_one({"_id": ObjectId(folder_id)})
        if not folder:
            await callback_query.answer("Folder not found.", show_alert=True)
            return

        filter_query, _ = await get_query_and_title(user_id, data)
        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=0, back_data=f"mf_sea_{folder_id}_{season}")

        text = f"📁 **{folder['name']} - Season {season}** ({total} files)\n\n📌 = Permanent | ⏳ = Temporary"
        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data.startswith("mf_pg_"):
        parts = data.replace("mf_pg_", "").split("_")
        page = max(0, int(parts[0]))
        back_data = "_".join(parts[1:])

        filter_query, text = await get_query_and_title(user_id, back_data)

        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=page, back_data=back_data)
        text += f" ({total} total)\n\n📌 = Permanent | ⏳ = Temporary"

        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data.startswith("myfiles_file_"):
        file_id = data.replace("myfiles_file_", "")
        f = await db.files.find_one({"_id": ObjectId(file_id)})
        if not f:
            await callback_query.answer("File not found.", show_alert=True)
            return

        name = f.get("file_name", "Unknown")
        status = f.get("status", "temporary")
        expires = f.get("expires_at")
        media_type = f.get("media_type")

        # Check if user has poster display enabled
        show_poster = await db.get_setting("display_show_poster", False, user_id)
        poster = f.get("poster_url") if show_poster else None

        text = (
            f"📄 **{name}**\n\n"
            f"**Status:** `{status.capitalize()}`\n"
        )
        if media_type:
            text += f"**Type:** `{media_type.capitalize()}`\n"
        if expires and status == "temporary":
            text += f"**Expires:** `{expires.strftime('%Y-%m-%d %H:%M UTC')}`\n"

        perm_btn_text = "❌ Make Temporary" if status == "permanent" else "📌 Make Permanent"

        state_dict = await get_myfiles_state(user_id)
        last_menu = state_dict.get("last_menu", "myfiles_main")

        buttons = [
            [InlineKeyboardButton("📤 Send File", callback_data=f"myfiles_send_{file_id}")],
            [InlineKeyboardButton("🔗 Generate Share Link", callback_data=f"myfiles_share_{file_id}")],
            [InlineKeyboardButton(perm_btn_text, callback_data=f"myfiles_toggle_perm_{file_id}")],
            [InlineKeyboardButton("✏️ Rename", callback_data=f"myfiles_rename_{file_id}"),
             InlineKeyboardButton("📂 Move", callback_data=f"myfiles_move_{file_id}")],
            [InlineKeyboardButton("🗑️ Delete File", callback_data=f"myfiles_delfile_{file_id}")],
            [InlineKeyboardButton("← Back", callback_data=last_menu)]
        ]

        reply_markup = InlineKeyboardMarkup(buttons)

        await safe_edit_or_send(client, callback_query, text, reply_markup, photo=poster)
        return

    if data == "myfiles_create_folder":
        await set_myfiles_state(user_id, {"state": "awaiting_folder_name", "prompt_msg_id": callback_query.message.id})
        text = "📁 **Create New Folder**\n\nPlease enter a name for the new folder:"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="myfiles_cat_custom")]])
        await safe_edit_or_send(client, callback_query, text, markup)
        return

    if data.startswith("myfiles_del_folder_"):
        folder_id = data.replace("myfiles_del_folder_", "")

        folder = await db.folders.find_one({"_id": ObjectId(folder_id)})
        if not folder:
            await callback_query.answer("Folder not found.", show_alert=True)
            return

        count = await db.files.count_documents({"folder_id": ObjectId(folder_id)})
        if count == 0:
            await db.folders.delete_one({"_id": ObjectId(folder_id)})
            await callback_query.answer("Empty folder deleted.", show_alert=True)
            callback_query.data = "myfiles_cat_custom"
            await myfiles_callback(client, callback_query)
            return

        text = f"⚠️ **Warning**\n\nThe folder **{folder['name']}** contains `{count}` files.\nDo you want to keep the files (they will be moved to the main directory), or delete the files as well?"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 Keep Files", callback_data=f"mf_df_keep_{folder_id}")],
            [InlineKeyboardButton("🗑️ Delete Files Too", callback_data=f"mf_df_del_{folder_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"myfiles_folder_{folder_id}")]
        ])
        await safe_edit_or_send(client, callback_query, text, markup)
        return

    if data.startswith("mf_df_keep_"):
        folder_id = data.replace("mf_df_keep_", "")
        await db.files.update_many({"folder_id": ObjectId(folder_id)}, {"$set": {"folder_id": None}})
        await db.folders.delete_one({"_id": ObjectId(folder_id)})
        await callback_query.answer("Folder deleted, files kept.", show_alert=True)
        callback_query.data = "myfiles_cat_custom"
        await myfiles_callback(client, callback_query)
        return

    if data.startswith("mf_df_del_"):
        folder_id = data.replace("mf_df_del_", "")
        await db.files.delete_many({"folder_id": ObjectId(folder_id)})
        await db.folders.delete_one({"_id": ObjectId(folder_id)})
        await callback_query.answer("Folder and all contained files deleted.", show_alert=True)
        callback_query.data = "myfiles_cat_custom"
        await myfiles_callback(client, callback_query)
        return

    if data.startswith("myfiles_rename_"):
        file_id = data.replace("myfiles_rename_", "")
        import time as _time
        await set_myfiles_state(user_id, {
            "state": f"awaiting_rename_{file_id}",
            "timestamp": _time.time(),
            "prompt_msg_id": callback_query.message.id,
            "prompt_chat_id": callback_query.message.chat.id,
        })

        f = await db.files.find_one({"_id": ObjectId(file_id)})
        current_name = f.get("file_name", "") if f else ""
        text = f"✏️ **Rename File**\n\nCurrent Name: `{current_name}`\n\nPlease send the new name for the file:"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"myfiles_file_{file_id}")]])
        await safe_edit_or_send(client, callback_query, text, markup)
        return

    if data.startswith("myfiles_move_"):
        file_id = data.replace("myfiles_move_", "")

        cursor = db.folders.find({"user_id": user_id, "type": "custom"}).sort("name", 1)
        folders = await cursor.to_list(length=None)

        text = "📂 **Move File**\n\nSelect a folder to move this file to:"
        buttons = [
            [InlineKeyboardButton("🧹 Remove from Folder", callback_data=f"mf_mov_{file_id}_None")]
        ]

        for folder in folders:
            buttons.append([InlineKeyboardButton(f"📁 {folder['name']}", callback_data=f"mf_mov_{file_id}_{str(folder['_id'])}")])

        buttons.append([InlineKeyboardButton("← Back", callback_data=f"myfiles_file_{file_id}")])

        await safe_edit_or_send(client, callback_query, text, InlineKeyboardMarkup(buttons))
        return

    if data.startswith("mf_mov_"):
        parts = data.replace("mf_mov_", "").split("_")
        file_id = parts[0]
        folder_id = parts[1]

        if folder_id == "None":
            await db.files.update_one({"_id": ObjectId(file_id)}, {"$set": {"folder_id": None}})
        else:
            await db.files.update_one({"_id": ObjectId(file_id)}, {"$set": {"folder_id": ObjectId(folder_id)}})

        await callback_query.answer("File moved.", show_alert=True)
        callback_query.data = f"myfiles_file_{file_id}"
        await myfiles_callback(client, callback_query)
        return

    if data.startswith("myfiles_send_"):
        file_id = data.replace("myfiles_send_", "")
        f = await db.files.find_one({"_id": ObjectId(file_id)})
        if not f:
            await callback_query.answer("File not found in DB.", show_alert=True)
            return

        await callback_query.answer("Sending file...", show_alert=False)
        try:
            from pyrogram.errors import PeerIdInvalid
            try:
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=f["channel_id"],
                    message_id=f["message_id"]
                )
            except PeerIdInvalid:
                await client.get_chat(f["channel_id"])
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=f["channel_id"],
                    message_id=f["message_id"]
                )
        except Exception as e:
            await client.send_message(user_id, f"❌ Failed to send file. It might have been deleted from the database channel. Error: `{e}`")
        return

    if data.startswith("myfiles_share_"):
        file_id = data.replace("myfiles_share_", "")
        bot_me = await client.get_me()
        bot_username = bot_me.username

        deep_link = f"https://t.me/{bot_username}?start=file_{file_id}"

        try:
            f = await db.files.find_one({"_id": ObjectId(file_id)})
            name = f.get("file_name", "Unknown File") if f else "Unknown File"
        except Exception:
            await callback_query.answer("Invalid File ID", show_alert=True)
            return

        text = (
            f"🔗 **Share Link Generated**\n\n"
            f"**File:** `{name}`\n\n"
            f"**Link:**\n`{deep_link}`\n\n"
            f"Anyone with this link can start the bot and receive this file."
        )

        markup = InlineKeyboardMarkup([[InlineKeyboardButton("← Back to File", callback_data=f"myfiles_file_{file_id}")]])
        await safe_edit_or_send(client, callback_query, text, markup)
        return

    if data.startswith("myfiles_delfile_"):
        file_id = data.replace("myfiles_delfile_", "")

        f = await db.files.find_one({"_id": ObjectId(file_id)})
        if f:
            await db.files.delete_one({"_id": ObjectId(file_id)})

        await callback_query.answer("File deleted.", show_alert=True)
        # Go back
        state_dict = await get_myfiles_state(user_id)
        callback_query.data = state_dict.get("last_menu", "myfiles_main")
        await myfiles_callback(client, callback_query)
        return

    if data.startswith("myfiles_toggle_perm_"):
        file_id = data.replace("myfiles_toggle_perm_", "")
        f = await db.files.find_one({"_id": ObjectId(file_id)})
        if not f: return

        new_status = "temporary" if f["status"] == "permanent" else "permanent"

        if new_status == "permanent":
            # Check limits
            user_doc = await db.get_user(user_id)
            if Config.PUBLIC_MODE:
                plan = user_doc.get("premium_plan", "standard") if user_doc and user_doc.get("is_premium") else "free"
            else:
                plan = "global"

            config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
            limits = config.get("myfiles_limits", {}).get(plan, {})
            perm_limit = limits.get("permanent_limit", 50 if Config.PUBLIC_MODE else -1)

            if perm_limit != -1:
                query_filter = {"user_id": user_id, "status": "permanent"} if Config.PUBLIC_MODE else {"status": "permanent"}
                perm_count = await db.files.count_documents(query_filter)
                if perm_count >= perm_limit:
                    await callback_query.answer(f"You have reached your permanent storage limit ({perm_limit}).", show_alert=True)
                    return

        # Update
        updates = {"status": new_status}
        if new_status == "temporary":
            # Set expiry
            user_doc = await db.get_user(user_id)
            if Config.PUBLIC_MODE:
                plan = user_doc.get("premium_plan", "standard") if user_doc and user_doc.get("is_premium") else "free"
            else:
                plan = "global"

            config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
            limits = config.get("myfiles_limits", {}).get(plan, {})
            expiry_days = limits.get("expiry_days", 10)

            if expiry_days != -1:
                updates["expires_at"] = datetime.datetime.utcnow() + datetime.timedelta(days=expiry_days)
        else:
            updates["expires_at"] = None

        await db.files.update_one({"_id": ObjectId(file_id)}, {"$set": updates})
        await callback_query.answer("Status updated.")

        # Refresh file view
        callback_query.data = f"myfiles_file_{file_id}"
        await myfiles_callback(client, callback_query)
        return

    if data == "mf_sa":
        state_dict = await get_myfiles_state(user_id)
        back_data = state_dict.get("current_view", "myfiles_cat_recent")

        filter_query, _ = await get_query_and_title(user_id, back_data)

        # Use sort order from state
        sort_order = state_dict.get("sort_order", "newest")

        if sort_order == "oldest":
            sort_tuple = [("created_at", 1)]
        elif sort_order == "a-z":
            sort_tuple = [("file_name", 1)]
        else:
            sort_tuple = [("created_at", -1)]

        files = await db.files.find(filter_query).sort(sort_tuple).to_list(length=None)
        if not files:
            await callback_query.answer("No files to send.", show_alert=True)
            return

        await callback_query.answer("Starting batch send...", show_alert=False)

        # Determine plan for queue management
        user_doc = await db.get_user(user_id)
        if Config.PUBLIC_MODE:
            plan = user_doc.get("premium_plan", "standard") if user_doc and user_doc.get("is_premium") else "free"
        else:
            plan = "global"

        # Add to Queue Manager
        from utils.queue_manager import queue_manager
        import time

        batch_id = queue_manager.create_batch()
        # Register items into the batch so update_status works
        for i, f in enumerate(files):
            # Using add_to_batch which handles (batch_id, item_id, sort_key, display_name, message_id)
            queue_manager.add_to_batch(batch_id, str(i), (0, i, 0), f.get("file_name", f"File {i}"), 0)

        # Kick off background task to send files
        import asyncio
        asyncio.create_task(process_send_all(client, user_id, files, plan, batch_id))

        await callback_query.message.reply_text(f"⏳ Added {len(files)} files to delivery queue. They will arrive shortly.")
        return

async def process_send_all(client, user_id, files, plan, batch_id):
    from pyrogram.errors import FloodWait
    import asyncio
    from utils.queue_manager import queue_manager

    count = 0
    for i, f in enumerate(files):
        # Free users get blocks of 20
        if plan == "free" and count > 0 and count % 20 == 0:
            await client.send_message(user_id, "⏳ Cooldown reached. Waiting 60 seconds to prevent spam...")
            await asyncio.sleep(60)

        try:
            from pyrogram.errors import PeerIdInvalid
            try:
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=f["channel_id"],
                    message_id=f["message_id"]
                )
            except PeerIdInvalid:
                await client.get_chat(f["channel_id"])
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=f["channel_id"],
                    message_id=f["message_id"]
                )
            count += 1
            queue_manager.update_status(batch_id, str(i), "done_user")

            # Debounce
            await asyncio.sleep(0.5 if plan != "free" else 2)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            queue_manager.update_status(batch_id, str(i), "failed", str(e))
            logger.error(f"Send all error: {e}")

    await client.send_message(user_id, f"✅ Batch send complete. Delivered {count} files.")
    try:
        await client.send_sticker(user_id, "CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")
    except Exception:
        pass

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------