from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
import asyncio

# Admin Session Store
admin_sessions = {} # user_id: state

def is_admin(user_id):
    return user_id == Config.CEO_ID

# For messages, filters.private is fine.
@Client.on_message(filters.command("admin") & filters.private)
async def admin_panel(client, message):
    if not is_admin(message.from_user.id):
        return # Ignore non-admins

    await message.reply_text(
        "🛠 **XTV Admin Panel** 🛠\n\n"
        "Welcome, CEO.\n"
        "Manage global settings for the XTV Rename Bot.\n"
        "These settings affect all files processed by the bot.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🖼 Set Default Thumbnail", callback_data="admin_thumb")],
            [InlineKeyboardButton("📝 Edit Metadata Templates", callback_data="admin_templates")],
            [InlineKeyboardButton("👀 View Current Settings", callback_data="admin_view")]
        ])
    )

# Remove filters.private from CallbackQuery handler
@Client.on_callback_query(filters.regex(r"^admin_"))
async def admin_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        return

    data = callback_query.data

    if data == "admin_thumb":
        admin_sessions[user_id] = "awaiting_thumb"
        await callback_query.message.edit_text(
            "🖼 **Set Default Thumbnail**\n\n"
            "Please send the **photo** you want to set as the default cover art/thumbnail for all files.\n"
            "This will be embedded into every video processed.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
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

    elif data == "admin_view":
        settings = await db.get_settings()
        templates = settings.get("templates", {}) if settings else {}
        has_thumb = "✅ Yes" if settings and settings.get("thumbnail_binary") else "❌ No"

        text = f"👀 **Current Settings**\n\n"
        text += f"**Thumbnail Set:** {has_thumb}\n\n"
        text += "**Metadata Templates:**\n"
        if templates:
            for k, v in templates.items():
                text += f"- **{k.capitalize()}:** `{v}`\n"
        else:
            text += "No templates set."

        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]])
        )

    elif data == "admin_main" or data == "admin_cancel":
        admin_sessions.pop(user_id, None)
        # Re-send main panel
        await callback_query.message.edit_text(
            "🛠 **XTV Admin Panel** 🛠\n\n"
            "Welcome, CEO.\n"
            "Manage global settings for the XTV Rename Bot.\n"
            "These settings affect all files processed by the bot.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 Set Default Thumbnail", callback_data="admin_thumb")],
                [InlineKeyboardButton("📝 Edit Metadata Templates", callback_data="admin_templates")],
                [InlineKeyboardButton("👀 View Current Settings", callback_data="admin_view")]
            ])
        )

    elif data.startswith("edit_template_"):
        field = data.split("_")[-1]
        admin_sessions[user_id] = f"awaiting_template_{field}"

        # Get current val
        templates = await db.get_all_templates()
        current_val = templates.get(field, "")

        await callback_query.message.edit_text(
            f"✏️ **Edit {field.capitalize()} Template**\n\n"
            f"Send the new template text.\n"
            f"Current: `{current_val}`\n\n"
            f"Variables: `{{title}}`, `{{season_episode}}`, `{{lang}}` (for audio/subtitle)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
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

        await msg.edit_text("✅ Thumbnail updated successfully!")
        admin_sessions.pop(user_id, None)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

@Client.on_message(filters.text & filters.private)
async def handle_admin_text(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        return

    state = admin_sessions.get(user_id)
    if not state or not state.startswith("awaiting_template_"):
        return

    field = state.split("_")[-1]
    new_template = message.text

    await db.update_template(field, new_template)
    await message.reply_text(f"✅ Template for **{field.capitalize()}** updated to:\n`{new_template}`")
    admin_sessions.pop(user_id, None)
