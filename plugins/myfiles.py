# --- Imports ---
from pyrogram import Client, filters
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
    cursor = db.files.find(filter_query).sort("created_at", -1).skip(skip).limit(limit)
    files = await cursor.to_list(length=limit)
    total_files = await db.files.count_documents(filter_query)

    buttons = []
    for f in files:
        name = f.get("file_name", "Unknown File")
        if len(name) > 30: name = name[:27] + "..."
        status_emoji = "📌" if f.get("status") == "permanent" else "⏳"
        buttons.append([InlineKeyboardButton(f"{status_emoji} {name}", callback_data=f"myfiles_file_{str(f['_id'])}")])

    nav_row = []
    total_pages = math.ceil(total_files / limit) if total_files > 0 else 1

    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"myfiles_page_{page-1}_{back_data}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))

    nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))

    if skip + limit < total_files:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"myfiles_page_{page+1}_{back_data}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))

    buttons.append(nav_row)

    # Action buttons for the folder/category itself
    buttons.append([
        InlineKeyboardButton("📤 Send All", callback_data=f"myfiles_sendall_{back_data}")
    ])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=back_data)])
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
        from pyrogram.errors import StopPropagation
        raise StopPropagation

    if state.startswith("awaiting_rename_"):
        file_id = state.replace("awaiting_rename_", "")
        new_name = message.text.strip()

        await db.files.update_one({"_id": ObjectId(file_id)}, {"$set": {"file_name": new_name}})

        await message.reply_text(f"✅ File renamed to `{new_name}`.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to File", callback_data=f"myfiles_file_{file_id}")]]))
        await set_myfiles_state(user_id, {})

        from pyrogram.errors import StopPropagation
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

@Client.on_callback_query(filters.regex(r"^(myfiles_|mf_mov_|mf_df_)"))
async def myfiles_callback(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    # Fast-dismiss loading spinner except where we specifically want an alert.
    # We will answer below if we need a custom text.
    try:
        if not (data.startswith("myfiles_send_") or data.startswith("myfiles_sendall_") or data.startswith("myfiles_delfile_") or data.startswith("myfiles_del_folder_") or data.startswith("mf_mov_") or data.startswith("mf_df_")):
            await callback_query.answer()
    except Exception:
        pass

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
            await callback_query.message.edit_text(text, reply_markup=markup)
        except MessageNotModified:
            pass
        return

    if data == "myfiles_settings":
        user_settings = await db.get_settings(user_id)
        auto_perm = True
        if user_settings and "myfiles_auto_permanent" in user_settings:
            auto_perm = user_settings["myfiles_auto_permanent"]

        emoji = "✅ ON" if auto_perm else "❌ OFF"
        text = (
            "⚙️ **/myfiles Settings**\n\n"
            "**Auto-Permanent Mode:** When enabled, files will automatically consume your permanent storage slots. "
            "When disabled, files are saved as temporary by default, and you must manually mark them as permanent."
        )
        buttons = [
            [InlineKeyboardButton(f"Auto-Permanent: {emoji}", callback_data="myfiles_toggle_auto")],
            [InlineKeyboardButton("🗑️ Clear Permanent Storage", callback_data="myfiles_clear_perm")],
            [InlineKeyboardButton("🔙 Back", callback_data="myfiles_main")]
        ]
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
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
        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=0, back_data=f"myfiles_cat_{folder.get('type', 'custom')}")

        if folder.get('type') == 'custom':
            buttons.insert(-2, [InlineKeyboardButton("🗑️ Delete Folder", callback_data=f"myfiles_del_folder_{folder_id}")])

        text = f"📁 **{folder['name']}** ({total} files)\n\n📌 = Permanent | ⏳ = Temporary"
        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        return

    if data.startswith("myfiles_page_"):
        parts = data.replace("myfiles_page_", "").split("_")
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
        else:
            filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
            text = "🕒 **Files**"

        buttons, total = await build_files_list_keyboard(user_id, filter_query, page=page, back_data=back_data)
        text += f" ({total} total)\n\n📌 = Permanent | ⏳ = Temporary"

        try:
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

        text = (
            f"📄 **{name}**\n\n"
            f"**Status:** `{status.capitalize()}`\n"
        )
        if expires and status == "temporary":
            text += f"**Expires:** `{expires.strftime('%Y-%m-%d %H:%M UTC')}`\n"

        perm_btn_text = "❌ Make Temporary" if status == "permanent" else "📌 Make Permanent"

        state_dict = await get_myfiles_state(user_id)
        last_menu = state_dict.get("last_menu", "myfiles_main")

        buttons = [
            [InlineKeyboardButton("📤 Send File", callback_data=f"myfiles_send_{file_id}")],
            [InlineKeyboardButton(perm_btn_text, callback_data=f"myfiles_toggle_perm_{file_id}")],
            [InlineKeyboardButton("✏️ Rename", callback_data=f"myfiles_rename_{file_id}"),
             InlineKeyboardButton("📂 Move", callback_data=f"myfiles_move_{file_id}")],
            [InlineKeyboardButton("🗑️ Delete File", callback_data=f"myfiles_delfile_{file_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=last_menu)]
        ]

        try:
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
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

    if data.startswith("myfiles_sendall_"):
        back_data = data.replace("myfiles_sendall_", "")

        if back_data == "myfiles_main":
            filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}
        elif back_data.startswith("myfiles_folder_"):
            folder_id = back_data.replace("myfiles_folder_", "")
            filter_query = {"user_id": user_id, "folder_id": ObjectId(folder_id)} if Config.PUBLIC_MODE else {"folder_id": ObjectId(folder_id)}
        else:
            filter_query = {"user_id": user_id} if Config.PUBLIC_MODE else {}

        files = await db.files.find(filter_query).sort("created_at", 1).to_list(length=None)
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
        batch_id = f"sendall_{user_id}_{int(time.time())}"

        queue_manager.create_batch(batch_id, len(files), user_id)
        # Register items into the batch so update_status works
        for i, f in enumerate(files):
            queue_manager.add_item(batch_id, str(i), f.get("file_name", f"File {i}"))

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

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------