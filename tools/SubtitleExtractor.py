# --- Imports ---
import asyncio
import contextlib
import logging

from pyrogram import Client, StopPropagation, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from plugins.user_setup import track_tool_usage
from utils.media.ffmpeg_tools import execute_ffmpeg
from utils.state import clear_session, get_data, get_state, set_state, update_data
from utils.telegram.log import get_logger

logger = get_logger("tools.SubtitleExtractor")

# === Handlers ===
@Client.on_callback_query(filters.regex(r"^subtitle_extractor_menu$"))
async def handle_subtitle_extractor_menu(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, 'subtitle_extractor')
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_extract_subtitles")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "📝 **Subtitle Extractor**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me the **video file** you want to\n"
            "> extract subtitles from.\n\n"
            "**Output:** SRT subtitle file",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )

@Client.on_message((filters.video | filters.document) & filters.private, group=1)
async def handle_subtitle_extractor_upload(client, message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state == "awaiting_extract_subtitles":
        file_name = "video.mkv"
        if getattr(message, "video", None):
            file_name = message.video.file_name or "video.mp4"
        elif getattr(message, "document", None):
            file_name = message.document.file_name or "file.bin"

        update_data(user_id, "original_name", file_name)
        update_data(user_id, "file_message_id", message.id)
        update_data(user_id, "file_chat_id", message.chat.id)

        session_data = get_data(user_id)
        data = {
            "type": "extract_subtitles",
            "original_name": session_data.get("original_name"),
            "file_message_id": session_data.get("file_message_id"),
            "file_chat_id": session_data.get("file_chat_id"),
            "file_message": message,
            "is_auto": False,
        }

        reply_msg = await client.send_message(
            user_id,
            "📝 **Subtitle Extractor**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> ⏳ Scanning video streams for text tracks..."
        )
        from plugins.process import process_file

        asyncio.create_task(process_file(client, reply_msg, data))
        clear_session(user_id)
        raise StopPropagation

# === Functions ===
async def extract_subtitles(input_path: str, output_dir: str, safe_title: str, progress_callback=None) -> tuple[bool, bytes, str, str]:
    """
    Extracts subtitles from a media file using FFmpeg.
    Returns: (success, stderr, output_path, meta_title)
    """
    import os
    final_filename = f"{safe_title}_subtitles.srt"
    meta_title = f"{safe_title} Subtitles"
    output_path = os.path.join(output_dir, final_filename)

    cmd = ["ffmpeg", "-y", "-i", input_path, "-map", "0:s:0?", "-c:s", "srt", output_path]
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
