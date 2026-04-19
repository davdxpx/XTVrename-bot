# --- Imports ---
import asyncio
import contextlib

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from plugins.user_setup import track_tool_usage
from utils.media.ffmpeg_tools import execute_ffmpeg
from utils.state import clear_session, get_data, get_state, set_state
from utils.telegram.log import get_logger

logger = get_logger("tools.VideoNoteConverter")

# === Handlers ===
@Client.on_callback_query(filters.regex(r"^video_note_menu$"))
async def handle_video_note_menu(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, 'video_note_converter')
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_videonote_file")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "⭕ **Video Note Converter**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me a **video file** to convert it into\n"
            "> a Telegram **round video note**.\n\n"
            "**Note:** Video will be cropped to square, scaled to\n"
            "384px, and limited to 60 seconds.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )

# === Functions ===
async def convert_to_video_note(input_path: str, output_dir: str, safe_title: str, progress_callback=None) -> tuple[bool, bytes, str, str]:
    """
    Converts a video to Telegram video note format (square, 384px, max 60s).
    Returns: (success, stderr, output_path, meta_title)
    """
    import os
    final_filename = f"{safe_title}_videonote.mp4"
    meta_title = f"{safe_title}"
    output_path = os.path.join(output_dir, final_filename)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", "crop=min(iw\\,ih):min(iw\\,ih),scale=384:384",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-t", "60",
        "-an",
        output_path
    ]

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
