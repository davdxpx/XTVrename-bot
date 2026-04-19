# --- Imports ---
import asyncio
import contextlib
import logging

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from plugins.user_setup import track_tool_usage
from utils.media.ffmpeg_tools import execute_ffmpeg, generate_ffmpeg_command
from utils.telegram.log import get_logger
from utils.state import clear_session, get_data, get_state, set_state

logger = get_logger("tools.AudioMetadataEditor")

# === Handlers ===
@Client.on_callback_query(filters.regex(r"^audio_editor_menu$"))
async def handle_audio_editor_menu(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, 'audio_editor')
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_audio_file")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "🎵 **Audio Metadata Editor**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me the **audio file** you want to edit.\n"
            "> Supported: MP3, FLAC, M4A, WAV, OGG\n\n"
            "You can edit **title**, **artist**, **album** and **cover art**.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )

@Client.on_callback_query(
    filters.regex(r"^audio_edit_(title|artist|album|thumb|process)$")
)
async def handle_audio_edit_callbacks(client, callback_query):
    if not get_state(callback_query.from_user.id):
        return await callback_query.answer("⚠️ Session expired. Please start again.", show_alert=True)
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
            reply_msg = await client.send_message(
                user_id,
                "🎵 **Audio Metadata Editor**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> ⏳ Applying metadata changes..."
            )
            from plugins.process import process_file

            asyncio.create_task(process_file(client, reply_msg, data))
        except Exception as e:
            logger.error(f"Failed to get message for audio mode: {e}")
            await client.send_message(user_id, f"Error: {e}")
        clear_session(user_id)
        return

    set_state(user_id, f"awaiting_audio_{action}")

    if action == "thumb":
        text = (
            "🖼️ **Edit Cover Art**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me a **photo** to use as cover art."
        )
    else:
        text = (
            f"✏️ **Edit {action.capitalize()}**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> Send me the new **{action}** for this audio file.\n"
            f"> Send `—` to clear the current value."
        )

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="audio_menu_back")]]
            ),
        )

@Client.on_callback_query(filters.regex(r"^audio_menu_back$"))
async def handle_audio_menu_back(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    set_state(user_id, "awaiting_audio_menu")
    await render_audio_menu(client, callback_query.message, user_id)

async def render_audio_menu(client, message, user_id):
    sd = get_data(user_id)
    title = sd.get("audio_title", "Not Set")
    artist = sd.get("audio_artist", "Not Set")
    album = sd.get("audio_album", "Not Set")
    thumb = "✅ Uploaded" if sd.get("audio_thumb_id") else "❌ Not Set"

    text = (
        f"🎵 **Audio Metadata Editor**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> 📄 **File:** `{sd.get('original_name')}`\n"
        f"> 🏷️ **Title:** `{title}`\n"
        f"> 👤 **Artist:** `{artist}`\n"
        f"> 💿 **Album:** `{album}`\n"
        f"> 🖼️ **Cover Art:** {thumb}\n\n"
        "Tap any button below to edit a field, then press **Process** when ready."
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
        with contextlib.suppress(MessageNotModified):
            await message.edit_text(text, reply_markup=markup)

# === Functions ===
async def edit_audio_metadata(input_path: str, output_dir: str, safe_title: str, ext: str, metadata: dict, thumb_path: str = None, progress_callback=None) -> tuple[bool, bytes, str, str]:
    """
    Edits audio metadata using FFmpeg.
    Returns: (success, stderr, output_path, meta_title)
    """
    import os
    final_filename = f"{safe_title}{ext}"
    meta_title = metadata.get("title", safe_title)
    output_path = os.path.join(output_dir, final_filename)

    cmd, err = await generate_ffmpeg_command(
        input_path=input_path,
        output_path=output_path,
        metadata=metadata,
        thumbnail_path=thumb_path
    )

    if not cmd:
        return False, str(err).encode(), output_path, meta_title

    success, stderr = await execute_ffmpeg(cmd, progress_callback=progress_callback)
    return success, stderr, output_path, meta_title

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
