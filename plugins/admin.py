"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    Developed by 𝕏0L0™ (@davdxpx)                         ║
║     © 2024 XTV Network Global. All Rights Reserved.                      ║
║                                                                          ║
║  Project: XTV Rename Bot                                                 ║
║  Author: 𝕏0L0™                                                           ║
║  Telegram: @davdxpx                                                      ║
║  Channel: @XTVbots                                                       ║
║  Network: @XTVglobal                                                     ║
║  Backup: @XTVhome                                                        ║
║                                                                          ║
║  WARNING: This code is the intellectual property of XTV Network.         ║
║  Unauthorized modification, redistribution, or removal of this credit    ║
║  is strictly prohibited. Forking and simple usage is allowed under       ║
║  the terms of the license.                                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

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
            [InlineKeyboardButton("📝 Edit Caption Template", callback_data="admin_caption")],
            [InlineKeyboardButton("👀 View Current Settings", callback_data="admin_view")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^(admin_|edit_template_)"))
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
            text += "No templates set."

        await callback_query.message.edit_text(
            text,
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
                [InlineKeyboardButton("📝 Edit Caption Template", callback_data="admin_caption")],
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
    if not state or not state.startswith("awaiting_template_"):
        return

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
