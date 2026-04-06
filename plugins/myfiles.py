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

# === Helper Functions ===
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

        text = (
            "📁 **My Files Management**\n\n"
            f"**Plan:** `{plan.capitalize()}`\n"
            f"**Permanent Storage:** `{perm_count} / {limit_str}` files\n"
            f"**Temporary Storage:** `{temp_count}` files\n\n"
            "Select a category to view your files:"
        )
    else:
        perm_count = await db.files.count_documents({"status": "permanent"})
        temp_count = await db.files.count_documents({"status": "temporary"})

        limits = config.get("myfiles_limits", {}).get("global", {})
        perm_limit = limits.get("permanent_limit", -1)

        limit_str = str(perm_limit) if perm_limit != -1 else "Unlimited"

        text = (
            "📁 **Team Files Management**\n\n"
            f"**Permanent Storage:** `{perm_count} / {limit_str}` files\n"
            f"**Temporary Storage:** `{temp_count}` files\n\n"
            "Select a category to view files:"
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

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"myfiles_leave_{back_data}")])
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
                await message.reply_text(f"❌ You have reached your custom folder limit ({folder_limit}).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="myfiles_cat_custom")]]))
                await set_myfiles_state(user_id, {})
                return

        await db.folders.insert_one({
            "user_id": user_id,
            "name": folder_name,
            "type": "custom",
            "created_at": datetime.datetime.utcnow()
        })

        await message.reply_text(f"✅ Folder **{folder_name}** created successfully.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Folders", callback_data="myfiles_cat_custom")]]))
        await set_myfiles_state(user_id, {})

        # Stop propagation to prevent flow.py from processing this text
        from pyrogram import StopPropagation
        raise StopPropagation

    if state.startswith("awaiting_rename_"):
        file_id = state.replace("awaiting_rename_", "")
        new_name = message.text.strip()

        await db.files.update_one({"_id": ObjectId(file_id)}, {"$set": {"file_name": new_name}})

        await message.reply_text(f"✅ File renamed to `{new_name}`.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to File", callback_data=f"myfiles_file_{file_id}")]]))
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

    text, markup = await get_myfiles_main_menu(user_id)
    await message.reply_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex(r"^(myfiles_|mf_mov_|mf_df_|mf_pg_|mf_st|mf_ms|mf_sea_|mf_sa)"))
async def myfiles_callback(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

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

        page = state_dict.get("current_page", 0)
        back_data = state_dict.get("current_view", "myfiles_cat_recent")
        callback_query.data = f"mf_pg_{page}_{back_data}"
        await myfiles_callback(client, callback_query)
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

        plan_features = config.get(f"premium_{plan}", {}).get("features", {})
        privacy_feat = plan_features.get("privacy", {})
        allow_anon = privacy_feat.get("link_anonymity", False)

        user_settings = await db.get_settings(user_id)
        use_anon = False
        if user_settings and "link_anonymity" in user_settings:
            use_anon = user_settings["link_anonymity"]

        if allow_anon and use_anon:
            group_id = f"{uuid.uuid4().hex[:16]}"
        else:
            group_id = f"{user_id}_{int(datetime.datetime.utcnow().timestamp())}"

        await db.db.file_groups.insert_one({
            "group_id": group_id,
            "user_id": user_id,
            "files": selected_files,
            "created_at": datetime.datetime.utcnow()
        })

        deep_link = f"https://t.me/{bot_username}?start=group_{group_id}"

        text = (
            f"📦 **Batch Share Link Generated**\n\n"
            f"**Files Included:** `{len(selected_files)}` files\n"
            f"**Link:**\n`{deep_link}`\n\n"
            f"> Anyone with this link can start the bot and receive these files."
        )

        back_data = state_dict.get("current_view", "myfiles_cat_recent")

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔗 Copy Link", copy_text=deep_link)],
                    [InlineKeyboardButton("🔙 Back", callback_data=back_data)]
                ])
            )
        except MessageNotModified:
            pass

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
        buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data=back_data)])

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
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
        try:
            if callback_query.message.photo:
                try:
                    await callback_query.message.delete()
                except:
                    pass
                await client.send_message(user_id, text, reply_markup=markup)
            else:
                await callback_query.message.edit_text(text, reply_markup=markup)
        except MessageNotModified:
            pass
        return

    if data == "myfiles_settings":
        user_settings = await db.get_settings(user_id)
        auto_perm = True
        if user_settings and "myfiles_auto_permanent" in user_settings:
            auto_perm = user_settings["myfiles_auto_permanent"]

        grouping_enabled = False
        if Config.PUBLIC_MODE:
            user_doc = await db.get_user(user_id)
            grouping_enabled = user_doc.get("group_series_by_season", False)
        else:
            config = await db.settings.find_one({"_id": "global_settings"})
            grouping_enabled = config.get("group_series_by_season", False)

        emoji = "✅ ON" if auto_perm else "❌ OFF"
        group_emoji = "✅ ON" if grouping_enabled else "❌ OFF"

        text = (
            "⚙️ **/myfiles Settings**\n\n"
            "**Auto-Permanent Mode:** When enabled, files will automatically consume your permanent storage slots. "
            "When disabled, files are saved as temporary by default, and you must manually mark them as permanent.\n\n"
            "**Group Series by Season:** When enabled, files in Series folders will be dynamically grouped into virtual Season subfolders based on metadata."
        )
        buttons = [
            [InlineKeyboardButton(f"Auto-Permanent: {emoji}", callback_data="myfiles_toggle_auto")],
            [InlineKeyboardButton(f"Group Series by Season: {group_emoji}", callback_data="myfiles_toggle_grouping")]
        ]

        # Check if user has privacy settings
        user_doc = await db.get_user(user_id)
        is_premium = user_doc.get("is_premium", False) if user_doc else False
        plan = user_doc.get("premium_plan", "standard") if is_premium else "free"

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        plan_features = config.get(f"premium_{plan}", {}).get("features", {})

        if plan_features.get("privacy_settings", False) or plan == "global":
            buttons.append([InlineKeyboardButton("🔒 Privacy Settings", callback_data="myfiles_privacy_settings")])

        buttons.append([InlineKeyboardButton("🗑️ Clear Permanent Storage", callback_data="myfiles_clear_perm")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="myfiles_main")])

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data == "myfiles_toggle_grouping":
        if Config.PUBLIC_MODE:
            user_doc = await db.get_user(user_id)
            current = user_doc.get("group_series_by_season", False)
            await db.users.update_one({"user_id": user_id}, {"$set": {"group_series_by_season": not current}})
        else:
            config = await db.settings.find_one({"_id": "global_settings"})
            current = config.get("group_series_by_season", False)
            await db.settings.update_one({"_id": "global_settings"}, {"$set": {"group_series_by_season": not current}})

        await callback_query.answer("Grouping setting toggled.", show_alert=False)
        callback_query.data = "myfiles_settings"
        await myfiles_callback(client, callback_query)
        return

    if data == "myfiles_privacy_settings":
        user_doc = await db.get_user(user_id)
        is_premium = user_doc.get("is_premium", False) if user_doc else False
        plan = user_doc.get("premium_plan", "standard") if is_premium else "free"

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        plan_features = config.get(f"premium_{plan}", {}).get("features", {})
        privacy_feat = plan_features.get("privacy", {})

        if not plan_features.get("privacy_settings", False) and plan != "global":
            await callback_query.answer("Your current plan does not have access to Privacy Settings.", show_alert=True)
            return

        user_settings = await db.get_settings(user_id)

        share_name = True
        if user_settings and "share_display_name" in user_settings:
            share_name = user_settings["share_display_name"]
        elif is_premium:
            # Default to False for premium users
            share_name = False

        hide_forward = False
        if user_settings and "hide_forward_tags" in user_settings:
            hide_forward = user_settings["hide_forward_tags"]

        link_anon = False
        if user_settings and "link_anonymity" in user_settings:
            link_anon = user_settings["link_anonymity"]

        emoji_name = "✅ ON" if share_name else "❌ OFF"
        emoji_fwd = "✅ ON" if hide_forward else "❌ OFF"
        emoji_anon = "✅ ON" if link_anon else "❌ OFF"

        text = (
            "🔒 **Privacy Settings**\n\n"
        )

        buttons = []

        if privacy_feat.get("hide_display_name", False) or plan == "global":
            text += "**Share Display Name:** When enabled, your name will be displayed when sharing your files with others via deep links.\n\n"
            buttons.append([InlineKeyboardButton(f"Display Name on Shares: {emoji_name}", callback_data="myfiles_toggle_share_name")])

        if privacy_feat.get("hide_forward_tags", False) or plan == "global":
            text += "**Hide Forwarding Tags:** When enabled, forwarded files will not have 'Forwarded from' tags when shared via deep links.\n\n"
            buttons.append([InlineKeyboardButton(f"Hide Forward Tags: {emoji_fwd}", callback_data="myfiles_toggle_hide_fwd")])

        if privacy_feat.get("link_anonymity", False) or plan == "global":
            text += "**Link Anonymity:** When enabled, batch share links use a secure, anonymous hash rather than embedding your account ID.\n\n"
            buttons.append([InlineKeyboardButton(f"Link Anonymity: {emoji_anon}", callback_data="myfiles_toggle_link_anon")])

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="myfiles_settings")])
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data == "myfiles_toggle_link_anon":
        user_doc = await db.get_user(user_id)
        is_premium = user_doc.get("is_premium", False) if user_doc else False
        plan = user_doc.get("premium_plan", "standard") if is_premium else "free"

        config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
        plan_features = config.get(f"premium_{plan}", {}).get("features", {})
        privacy_feat = plan_features.get("privacy", {})
        if not privacy_feat.get("link_anonymity", False) and plan != "global":
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
        if not plan_features.get("privacy_settings", False) and plan != "global":
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
        if not plan_features.get("privacy_settings", False) and plan != "global":
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
        callback_query.data = "myfiles_settings"
        await myfiles_callback(client, callback_query)
        return

    if data == "myfiles_clear_perm":
        try:
            await callback_query.message.edit_text(
                "⚠️ **Warning**\n\nAre you sure you want to delete ALL your permanent files? This cannot be undone.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes, Delete All", callback_data="myfiles_confirm_clear_perm")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="myfiles_settings")]
                ])
            )
        except MessageNotModified:
            pass
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
        try:
            if callback_query.message.photo:
                try:
                    await callback_query.message.delete()
                except:
                    pass
                await client.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
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

        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="myfiles_main")])

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
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
            grouping_enabled = user_doc.get("group_series_by_season", False)
        else:
            config = await db.settings.find_one({"_id": "global_settings"})
            grouping_enabled = config.get("group_series_by_season", False)

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

            buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"myfiles_cat_{folder.get('type', 'custom')}")])
            total = sum(season_counts.values())
            text = f"📁 **{folder['name']}** ({total} files)\n\n📌 = Permanent | ⏳ = Temporary\n\nSelect a season:"

            try:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            except MessageNotModified:
                pass
            return

        # Normal list
        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=0, back_data=f"myfiles_cat_{folder.get('type', 'custom')}")

        if folder.get('type') == 'custom':
            buttons.insert(-2, [InlineKeyboardButton("🗑️ Delete Folder", callback_data=f"myfiles_del_folder_{folder_id}")])

        text = f"📁 **{folder['name']}** ({total} files)\n\n📌 = Permanent | ⏳ = Temporary"
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data.startswith("mf_sea_"):
        parts = data.replace("mf_sea_", "").split("_")
        folder_id = parts[0]
        season = parts[1]

        folder = await db.folders.find_one({"_id": ObjectId(folder_id)})
        if not folder:
            await callback_query.answer("Folder not found.", show_alert=True)
            return

        filter_query = {"user_id": user_id, "folder_id": ObjectId(folder_id)} if Config.PUBLIC_MODE else {"folder_id": ObjectId(folder_id)}

        # We need to filter files by season in the DB query
        # Since MongoDB can't easily filter by nested variant types directly for this specific guessit structure,
        # we do a normal fetch and filter in python if necessary. But to support pagination, we should build a query if possible.
        # Let's try to query by guess_data.season. Since it can be a list or int, we use $in or simple equality.

        if season.isdigit():
            season_val = int(season)
            str_season_val = str(season_val)
            # Match where explicit DB season is season_val, or tmdb_data.season is season_val
            # or file_name contains S01 / S1
            filter_query["$or"] = [
                {"season": season_val},
                {"season": str_season_val},
                {"guess_data.season": season_val},
                {"guess_data.season": {"$in": [season_val]}},
                {"tmdb_data.season": season_val},
                {"tmdb_data.season": str_season_val},
                {"file_name": {"$regex": f"[sS]0?{season_val}\\b"}},
            ]
        else:
            # Handle "Unknown" or non-digit seasons
            filter_query["$and"] = [
                {"season": {"$exists": False}},
                {"guess_data.season": {"$exists": False}},
                {"tmdb_data.season": {"$exists": False}},
                {"file_name": {"$not": {"$regex": r"[sS]\d{1,2}"}}}
            ]

        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=0, back_data=f"mf_sea_{folder_id}_{season}")

        text = f"📁 **{folder['name']} - Season {season}** ({total} files)\n\n📌 = Permanent | ⏳ = Temporary"
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data.startswith("mf_pg_"):
        parts = data.replace("mf_pg_", "").split("_")
        page = max(0, int(parts[0]))
        back_data = "_".join(parts[1:])

        if back_data == "myfiles_main":
            filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
            text = "🕒 **Recent Files**"
        elif back_data.startswith("myfiles_cat_"):
            folder_type = back_data.replace("myfiles_cat_", "")
            filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
            text = f"📁 **{folder_type.capitalize()} Folders**"
        elif back_data.startswith("myfiles_folder_"):
            folder_id = back_data.replace("myfiles_folder_", "")
            filter_query = {"user_id": user_id, "folder_id": ObjectId(folder_id)} if Config.PUBLIC_MODE else {"folder_id": ObjectId(folder_id)}
            folder = await db.folders.find_one({"_id": ObjectId(folder_id)})
            text = f"📁 **{folder['name'] if folder else 'Folder'}**"
        elif back_data.startswith("mf_sea_"):
            season_parts = back_data.replace("mf_sea_", "").split("_")
            folder_id = season_parts[0]
            season = season_parts[1]
            filter_query = {"user_id": user_id, "folder_id": ObjectId(folder_id)} if Config.PUBLIC_MODE else {"folder_id": ObjectId(folder_id)}
            folder = await db.folders.find_one({"_id": ObjectId(folder_id)})

            if season.isdigit():
                season_val = int(season)
                str_season_val = str(season_val)
                filter_query["$or"] = [
                    {"season": season_val},
                    {"season": str_season_val},
                    {"guess_data.season": season_val},
                    {"guess_data.season": {"$in": [season_val]}},
                    {"tmdb_data.season": season_val},
                    {"tmdb_data.season": str_season_val},
                    {"file_name": {"$regex": f"[sS]0?{season_val}\\b"}},
                ]
            else:
                filter_query["$and"] = [
                    {"season": {"$exists": False}},
                    {"guess_data.season": {"$exists": False}},
                    {"tmdb_data.season": {"$exists": False}},
                    {"file_name": {"$not": {"$regex": r"[sS]\d{1,2}"}}}
                ]

            text = f"📁 **{folder['name'] if folder else 'Folder'} - Season {season}**"
        else:
            filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
            text = "🕒 **Files**"

        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=page, back_data=back_data)
        text += f" ({total} total)\n\n📌 = Permanent | ⏳ = Temporary"

        try:
            if callback_query.message.photo:
                try:
                    await callback_query.message.delete()
                except:
                    pass
                await client.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
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
        poster = f.get("poster_url")
        media_type = f.get("media_type")

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
            [InlineKeyboardButton("🔙 Back", callback_data=last_menu)]
        ]

        reply_markup = InlineKeyboardMarkup(buttons)

        try:
            if poster:
                from pyrogram.types import InputMediaPhoto
                try:
                    await callback_query.message.edit_media(
                        media=InputMediaPhoto(poster, caption=text),
                        reply_markup=reply_markup
                    )
                except Exception:
                    try:
                        await callback_query.message.delete()
                    except:
                        pass
                    await client.send_photo(
                        chat_id=user_id,
                        photo=poster,
                        caption=text,
                        reply_markup=reply_markup
                    )
            else:
                if callback_query.message.photo:
                    try:
                        await callback_query.message.delete()
                    except:
                        pass
                    await client.send_message(
                        chat_id=user_id,
                        text=text,
                        reply_markup=reply_markup
                    )
                else:
                    await callback_query.message.edit_text(text, reply_markup=reply_markup)
        except MessageNotModified:
            pass
        return

    if data == "myfiles_create_folder":
        await set_myfiles_state(user_id, {"state": "awaiting_folder_name"})
        try:
            await callback_query.message.edit_text(
                "📁 **Create New Folder**\n\nPlease enter a name for the new folder:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="myfiles_cat_custom")]])
            )
        except MessageNotModified:
            pass
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

        try:
            await callback_query.message.edit_text(
                f"⚠️ **Warning**\n\nThe folder **{folder['name']}** contains `{count}` files.\n"
                "Do you want to keep the files (they will be moved to the main directory), or delete the files as well?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📁 Keep Files", callback_data=f"mf_df_keep_{folder_id}")],
                    [InlineKeyboardButton("🗑️ Delete Files Too", callback_data=f"mf_df_del_{folder_id}")],
                    [InlineKeyboardButton("❌ Cancel", callback_data=f"myfiles_folder_{folder_id}")]
                ])
            )
            await callback_query.answer()
        except MessageNotModified:
            pass
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
        await set_myfiles_state(user_id, {"state": f"awaiting_rename_{file_id}"})

        f = await db.files.find_one({"_id": ObjectId(file_id)})
        current_name = f.get("file_name", "") if f else ""
        try:
            await callback_query.message.edit_text(
                f"✏️ **Rename File**\n\nCurrent Name: `{current_name}`\n\nPlease send the new name for the file:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"myfiles_file_{file_id}")]])
            )
        except MessageNotModified:
            pass
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

        buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data=f"myfiles_file_{file_id}")])

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
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

        try:
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to File", callback_data=f"myfiles_file_{file_id}")]])
            )
        except MessageNotModified:
            pass
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
            perm_limit = limits.get("permanent_limit", 50)

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

        filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}

        real_back_data = back_data
        if real_back_data.startswith("myfiles_folder_"):
            folder_id = real_back_data.replace("myfiles_folder_", "")
            filter_query["folder_id"] = ObjectId(folder_id)
        elif real_back_data.startswith("mf_sea_"):
            parts = real_back_data.replace("mf_sea_", "").split("_")
            folder_id = parts[0]
            season = parts[1]
            filter_query["folder_id"] = ObjectId(folder_id)
            if season.isdigit():
                season_val = int(season)
                str_season_val = str(season_val)
                filter_query["$or"] = [
                    {"season": season_val},
                    {"season": str_season_val},
                    {"guess_data.season": season_val},
                    {"guess_data.season": {"$in": [season_val]}},
                    {"tmdb_data.season": season_val},
                    {"tmdb_data.season": str_season_val},
                    {"file_name": {"$regex": f"[sS]0?{season_val}\\b"}},
                ]
            else:
                filter_query["$and"] = [
                    {"season": {"$exists": False}},
                    {"guess_data.season": {"$exists": False}},
                    {"tmdb_data.season": {"$exists": False}},
                    {"file_name": {"$not": {"$regex": r"[sS]\d{1,2}"}}}
                ]
        elif back_data.startswith("myfiles_cat_"):
            # They pressed send all on a category view? Usually send all is only on files list
            pass

        # Use sort order from state
        state_dict = await get_myfiles_state(user_id)
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