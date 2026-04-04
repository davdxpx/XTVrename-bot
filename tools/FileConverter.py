# --- Imports ---
from pyrogram.errors import MessageNotModified
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.state import set_state, get_state, get_data, clear_session
from utils.log import get_logger
import asyncio
import logging
from utils.ffmpeg_tools import execute_ffmpeg

logger = get_logger("tools.FileConverter")

# === Handlers ===
@Client.on_callback_query(filters.regex(r"^file_converter_menu$"))
async def handle_file_converter_menu(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_convert_file")

    try:
        await callback_query.message.edit_text(
            "🔀 **File Converter**\n\n"
            "Please **send me the file** (Video or Image) you want to convert.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass

@Client.on_callback_query(filters.regex(r"^convert_to_(.+)$"))
async def handle_convert_to(client, callback_query):
    if not get_state(callback_query.from_user.id):
        return await callback_query.answer("⚠️ Session expired. Please start again.", show_alert=True)
    await callback_query.answer()
    user_id = callback_query.from_user.id
    target_format = callback_query.data.split("_")[2]

    await callback_query.message.delete()
    session_data = get_data(user_id)

    data = {
        "type": "convert",
        "original_name": session_data.get("original_name"),
        "file_message_id": session_data.get("file_message_id"),
        "file_chat_id": session_data.get("file_chat_id"),
        "target_format": target_format,
        "is_auto": False,
    }

    try:
        msg = await client.get_messages(
            session_data.get("file_chat_id"), session_data.get("file_message_id")
        )
        data["file_message"] = msg
        reply_msg = await client.send_message(user_id, "Processing conversion...")
        from plugins.process import process_file

        asyncio.create_task(process_file(client, reply_msg, data))
    except Exception as e:
        logger.error(f"Failed to get message for convert mode: {e}")
        await client.send_message(user_id, f"Error: {e}")

    clear_session(user_id)

# === Functions ===
async def convert(input_path: str, output_path: str, target_format: str, progress_callback=None) -> tuple[bool, bytes]:
    """
    Converts a media file to the target format using FFmpeg.
    """
    cmd = ["ffmpeg", "-y", "-i", input_path]

    if target_format == "mp3":
        cmd.extend(["-vn", "-c:a", "libmp3lame", "-q:a", "2"])
    elif target_format == "gif":
        cmd.extend(["-vf", "fps=10,scale=320:-1:flags=lanczos", "-c:v", "gif"])
    elif target_format in ["png", "jpg", "jpeg", "webp"]:
        cmd.extend(["-vframes", "1"])
    elif target_format == "x264":
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "copy", "-c:s", "copy"])
    elif target_format == "x265":
        cmd.extend(["-c:v", "libx265", "-preset", "fast", "-crf", "28", "-c:a", "copy", "-c:s", "copy"])
    elif target_format == "audionorm":
        cmd.extend(["-c:v", "copy", "-c:s", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-c", "copy"])

    cmd.append(output_path)

    return await execute_ffmpeg(cmd, progress_callback=progress_callback)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
