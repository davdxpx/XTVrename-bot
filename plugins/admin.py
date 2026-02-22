from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.auth import auth_filter
from config import Config
from database import db
import asyncio

# Admin Session Store
admin_sessions = {} # user_id: state

def is_admin(user_id):
    return user_id == Config.CEO_ID

@Client.on_message(filters.command("admin") & filters.private)
async def admin_panel(client, message):
    if not is_admin(message.from_user.id):
        return # Ignore non-admins

    await message.reply_text(
        "**Professional Admin Panel**\n\n"
        "Manage global settings for the XTV Rename Bot.\n"
        "These settings affect all files processed by the bot.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Set Default Thumbnail", callback_data="admin_thumb")],
            [InlineKeyboardButton("Edit Metadata Templates", callback_data="admin_templates")],
            [InlineKeyboardButton("View Current Settings", callback_data="admin_view")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^admin_") & filters.private)
async def admin_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        return

    data = callback_query.data

    if data == "admin_thumb":
        admin_sessions[user_id] = "awaiting_thumb"
        await callback_query.message.edit_text(
            "**Set Default Thumbnail**\n\n"
            "Please send the photo you want to set as the default cover art/thumbnail for all files.\n"
            "This will be embedded into every video processed.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_cancel")]])
        )

    elif data == "admin_templates":
        await callback_query.message.edit_text(
            "**Edit Metadata Templates**\n\n"
            "Select a field to edit:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Title", callback_data="edit_template_title"),
                 InlineKeyboardButton("Author", callback_data="edit_template_author")],
                [InlineKeyboardButton("Artist", callback_data="edit_template_artist"),
                 InlineKeyboardButton("Video", callback_data="edit_template_video")],
                [InlineKeyboardButton("Audio", callback_data="edit_template_audio"),
                 InlineKeyboardButton("Subtitle", callback_data="edit_template_subtitle")],
                [InlineKeyboardButton("Back", callback_data="admin_main")]
            ])
        )

    elif data == "admin_view":
        settings = await db.get_settings()
        templates = settings.get("templates", {})
        has_thumb = "Yes" if settings.get("thumbnail_binary") else "No"

        text = f"**Current Settings**\n\n"
        text += f"**Thumbnail Set:** {has_thumb}\n\n"
        text += "**Templates:**\n"
        for k, v in templates.items():
            text += f"- **{k.capitalize()}:** `{v}`\n"

        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_main")]])
        )

    elif data == "admin_main" or data == "admin_cancel":
        admin_sessions.pop(user_id, None)
        await admin_panel(client, callback_query.message)

    elif data.startswith("edit_template_"):
        field = data.split("_")[-1]
        admin_sessions[user_id] = f"awaiting_template_{field}"
        await callback_query.message.edit_text(
            f"**Edit {field.capitalize()} Template**\n\n"
            f"Send the new template text.\n"
            f"Current: `{ (await db.get_all_templates()).get(field, '') }`\n\n"
            f"Variables: `{{title}}`, `{{season_episode}}`, `{{lang}}` (for audio/subtitle)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_cancel")]])
        )

@Client.on_message(filters.photo & filters.private)
async def handle_admin_photo(client, message):
    user_id = message.from_user.id
    if not is_admin(user_id) or admin_sessions.get(user_id) != "awaiting_thumb":
        return

    # Download photo to memory (binary)
    # Pyrogram download_media downloads to file usually.
    # To get binary, download to BytesIO or temp file then read.
    # Use client.download_media(message, in_memory=True)

    msg = await message.reply_text("Processing thumbnail...")
    try:
        # Download highest quality photo
        file_id = message.photo.file_id
        # We need binary for MongoDB
        path = await client.download_media(message, file_name=Config.THUMB_PATH)

        with open(path, "rb") as f:
            binary_data = f.read()

        await db.update_thumbnail(file_id, binary_data)

        # Clean up local file if we don't need it cached immediately
        # But we might use Config.THUMB_PATH as cache.
        # It's fine to leave it or overwrite next time.

        await msg.edit_text("Thumbnail updated successfully!")
        admin_sessions.pop(user_id, None)
        # Verify? No need.
    except Exception as e:
        await msg.edit_text(f"Error: {e}")

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
    await message.reply_text(f"Template for **{field.capitalize()}** updated to:\n`{new_template}`")
    admin_sessions.pop(user_id, None)
