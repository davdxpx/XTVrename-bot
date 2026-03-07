from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
from utils.log import get_logger
import asyncio
import io
logger = get_logger("plugins.admin")
admin_sessions = {}
def is_admin(user_id):
    return user_id == Config.CEO_ID
@Client.on_message(filters.command("admin") & filters.private)
async def admin_panel(client, message):
    if not is_admin(message.from_user.id):
        return
    await message.reply_text(
        "🛠 **XTV Admin Panel** 🛠\n\n"
        "Welcome, CEO.\n"
        "Manage global settings for the XTV Rename Bot.\n"
        "These settings affect all files processed by the bot.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🖼 Manage Thumbnail", callback_data="admin_thumb_menu")],
            [InlineKeyboardButton("📝 Edit Metadata Templates", callback_data="admin_templates")],
            [InlineKeyboardButton("📝 Edit Filename Templates", callback_data="admin_filename_templates")],
            [InlineKeyboardButton("📝 Edit Caption Template", callback_data="admin_caption")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
            [InlineKeyboardButton("👀 View Current Settings", callback_data="admin_view")]
        ])
    )
@Client.on_callback_query(filters.regex(r"^(admin_|edit_template_|edit_fn_template_)"))
async def admin_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        return
    data = callback_query.data
    logger.info(f"Admin callback: {data} from user {user_id}")
    if data == "admin_thumb_menu":
        await callback_query.message.edit_text(
            "🖼 **Manage Thumbnail**\n\n"
            "Select an action:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👀 View Current", callback_data="admin_thumb_view")],
                [InlineKeyboardButton("📤 Set Default", callback_data="admin_thumb_set")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
    elif data == "admin_thumb_view":
        thumb_bin, _ = await db.get_thumbnail()
        if thumb_bin:
            try:
                f = io.BytesIO(thumb_bin)
                f.name = "thumbnail.jpg"
                await client.send_photo(user_id, f, caption="**Current Default Thumbnail**")
                await callback_query.message.edit_text(
                    "🖼 **Manage Thumbnail**\n\n"
                    "Thumbnail sent above.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("👀 View Current", callback_data="admin_thumb_view")],
                        [InlineKeyboardButton("📤 Set Default", callback_data="admin_thumb_set")],
                        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to send thumbnail: {e}")
                await callback_query.answer("Error sending thumbnail!", show_alert=True)
        else:
            await callback_query.answer("No thumbnail set in DB!", show_alert=True)
    elif data == "admin_thumb_set":
        admin_sessions[user_id] = "awaiting_thumb"
        await callback_query.message.edit_text(
            "📤 **Set Default Thumbnail**\n\n"
            "Please send the **photo** you want to set as the default cover art/thumbnail for all files.\n"
            "This will be embedded into every video processed.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_thumb_menu")]])
        )
    elif data == "admin_templates":
        await callback_query.message.edit_text(
            "📝 **Edit Metadata Templates**\n\n"
            "Select a field to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Title", callback_data="edit_template_title"),
                 InlineKeyboardButton("Author", callback_data="edit_template_author")],
                [InlineKeyboardButton("Artist", callback_data="edit_template_artist"),
                 InlineKeyboardButton("Video", callback_data="edit_template_video")],
                [InlineKeyboardButton("Audio", callback_data="edit_template_audio"),
                 InlineKeyboardButton("Subtitle", callback_data="edit_template_subtitle")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
    elif data == "admin_caption":
        templates = await db.get_all_templates()
        current_caption = templates.get("caption", "{random}")
        admin_sessions[user_id] = "awaiting_template_caption"
        await callback_query.message.edit_text(
            "📝 **Edit Caption Template**\n\n"
            "Send the new caption text for uploaded files.\n\n"
            f"Current: `{current_caption}`\n\n"
            "**Variables:**\n"
            "- `{filename}` : The final filename\n"
            "- `{size}` : File size (e.g. 1.5 GB)\n"
            "- `{duration}` : Video duration\n"
            "- `{random}` : Generates a random alphanumeric string (Anti-Hash)\n\n"
            "Send `{random}` to use the default random text generator.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]])
        )
    elif data == "admin_view":
        settings = await db.get_settings()
        templates = settings.get("templates", {}) if settings else {}
        has_thumb = "✅ Yes" if settings and settings.get("thumbnail_binary") else "❌ No"
        text = f"👀 **Current Settings**\n\n"
        text += f"**Thumbnail Set:** {has_thumb}\n\n"
        text += "**Metadata Templates:**\n"
        if templates:
            for k, v in templates.items():
                if k == "caption":
                    text += f"- **Caption:** `{v}`\n"
                else:
                    text += f"- **{k.capitalize()}:** `{v}`\n"
        else:
            text += "No templates set.\n"
        text += "\n**Filename Templates:**\n"
        fn_templates = settings.get("filename_templates", {}) if settings else {}
        if fn_templates:
            for k, v in fn_templates.items():
                text += f"- **{k.capitalize()}:** `{v}`\n"
        else:
            text += "No filename templates set.\n"
        text += f"\n**Channel Variable:** `{settings.get('channel', Config.DEFAULT_CHANNEL) if settings else Config.DEFAULT_CHANNEL}`\n"
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]])
        )
    elif data == "admin_filename_templates":
        await callback_query.message.edit_text(
            "📝 **Edit Filename Templates**\n\n"
            "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Movies", callback_data="edit_fn_template_movies")],
                [InlineKeyboardButton("Series", callback_data="edit_fn_template_series")],
                [InlineKeyboardButton("Personal", callback_data="admin_fn_templates_personal")],
                [InlineKeyboardButton("Subtitles", callback_data="admin_fn_templates_subtitles")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
            ])
        )
    elif data == "admin_fn_templates_personal":
        await callback_query.message.edit_text(
            "📝 **Edit Personal Filename Templates**\n\n"
            "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Personal Files", callback_data="edit_fn_template_personal_file")],
                [InlineKeyboardButton("Personal Photos", callback_data="edit_fn_template_personal_photo")],
                [InlineKeyboardButton("Personal Videos", callback_data="edit_fn_template_personal_video")],
                [InlineKeyboardButton("🔙 Back", callback_data="admin_filename_templates")]
            ])
        )
    elif data == "admin_fn_templates_subtitles":
        await callback_query.message.edit_text(
            "📝 **Edit Subtitles Filename Templates**\n\n"
            "Select media type to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Movies", callback_data="edit_fn_template_subtitles_movies")],
                [InlineKeyboardButton("Series", callback_data="edit_fn_template_subtitles_series")],
            ])
        )
    elif data.startswith("edit_fn_template_"):
        field = data.replace("edit_fn_template_", "")
        admin_sessions[user_id] = f"awaiting_fn_template_{field}"
        templates = await db.get_filename_templates()
        current_val = templates.get(field, "")
        await callback_query.message.edit_text(
            f"✏️ **Edit Filename Template ({field.capitalize()})**\n\n"
            f"Send the new template text.\n"
            f"Current: `{current_val}`\n\n"
            f"Variables: `{{Title}}`, `{{Year}}`, `{{Quality}}`, `{{Season}}`, `{{Episode}}`, `{{Season_Episode}}`, `{{Language}}`, `{{Channel}}`\n"
            f"Note: File extension will be added automatically, do not include it in the template.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_filename_templates")]])
        )
    elif data == "admin_settings":
        current_channel = await db.get_channel()
        admin_sessions[user_id] = "awaiting_channel"
        await callback_query.message.edit_text(
            "⚙️ **Settings**\n\n"
            f"Send the new Channel name (e.g. `@XTVglobal`).\n"
            f"Current: `{current_channel}`\n\n",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]])
        )
    elif data == "admin_main" or data == "admin_cancel":
        admin_sessions.pop(user_id, None)
        await callback_query.message.edit_text(
            "🛠 **XTV Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for the XTV Rename Bot.\n"
            "These settings affect all files processed by the bot.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 Manage Thumbnail", callback_data="admin_thumb_menu")],
                [InlineKeyboardButton("📝 Edit Metadata Templates", callback_data="admin_templates")],
            [InlineKeyboardButton("📝 Edit Filename Templates", callback_data="admin_filename_templates")],
                [InlineKeyboardButton("📝 Edit Caption Template", callback_data="admin_caption")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
                [InlineKeyboardButton("👀 View Current Settings", callback_data="admin_view")]
            ])
        )
    elif data.startswith("edit_template_"):
        field = data.split("_")[-1]
        admin_sessions[user_id] = f"awaiting_template_{field}"
        templates = await db.get_all_templates()
        current_val = templates.get(field, "")
        await callback_query.message.edit_text(
            f"✏️ **Edit {field.capitalize()} Template**\n\n"
            f"Send the new template text.\n"
            f"Current: `{current_val}`\n\n"
            f"Variables: `{{title}}`, `{{season_episode}}`, `{{lang}}` (for audio/subtitle)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_templates")]])
        )
@Client.on_message(filters.photo & filters.private)
async def handle_admin_photo(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id) or admin_sessions.get(user_id) != "awaiting_thumb":
        return
    msg = await message.reply_text("Processing thumbnail...")
    try:
        file_id = message.photo.file_id
        path = await client.download_media(message, file_name=Config.THUMB_PATH)
        with open(path, "rb") as f:
            binary_data = f.read()
        await db.update_thumbnail(file_id, binary_data)
        await msg.edit_text("✅ Thumbnail updated successfully!",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_thumb_menu")]]))
        admin_sessions.pop(user_id, None)
    except Exception as e:
        logger.error(f"Thumbnail upload failed: {e}")
        await msg.edit_text(f"❌ Error: {e}")
@Client.on_message(filters.text & filters.private & ~filters.regex(r"^/"))
async def handle_admin_text(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return
    state = admin_sessions.get(user_id)
    if not state:
        return
    if state.startswith("awaiting_template_"):
        field = state.split("_")[-1]
        new_template = message.text
        await db.update_template(field, new_template)
        if field == "caption":
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]])
        else:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Templates", callback_data="admin_templates")]])
        await message.reply_text(f"✅ Template for **{field.capitalize()}** updated to:\n`{new_template}`",
                                 reply_markup=reply_markup)
        admin_sessions.pop(user_id, None)
    elif state.startswith("awaiting_fn_template_"):
        field = state.replace("awaiting_fn_template_", "")
        new_template = message.text
        await db.update_filename_template(field, new_template)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Filename Templates", callback_data="admin_filename_templates")]])
        await message.reply_text(f"✅ Filename template for **{field.capitalize()}** updated to:\n`{new_template}`",
                                 reply_markup=reply_markup)
        admin_sessions.pop(user_id, None)
    elif state == "awaiting_channel":
        new_channel = message.text
        await db.update_channel(new_channel)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]])
        await message.reply_text(f"✅ Channel variable updated to:\n`{new_channel}`",
                                 reply_markup=reply_markup)
        admin_sessions.pop(user_id, None)
# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
