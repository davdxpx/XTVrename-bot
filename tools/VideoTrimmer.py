# --- Imports ---
from pyrogram.errors import MessageNotModified
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.state import set_state, get_state, get_data, update_data, clear_session
from utils.log import get_logger
import asyncio
from utils.ffmpeg_tools import execute_ffmpeg

logger = get_logger("tools.VideoTrimmer")

# === Handlers ===
@Client.on_callback_query(filters.regex(r"^video_trimmer_menu$"))
async def handle_video_trimmer_menu(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_trim_file")

    try:
        await callback_query.message.edit_text(
            "✂️ **Video Trimmer**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me the **video file** you want to trim.\n"
            "> You will then specify start and end timestamps.\n\n"
            "**Format:** `HH:MM:SS` or `MM:SS`",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass

# === Functions ===
async def trim(input_path: str, output_dir: str, safe_title: str, start_time: str, end_time: str, progress_callback=None) -> tuple[bool, bytes, str, str]:
    """
    Trims a video file between start_time and end_time using FFmpeg.
    Returns: (success, stderr, output_path, meta_title)
    """
    import os
    ext = os.path.splitext(input_path)[1] or ".mkv"
    final_filename = f"{safe_title}_trimmed{ext}"
    meta_title = f"{safe_title}"
    output_path = os.path.join(output_dir, final_filename)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ss", start_time,
        "-to", end_time,
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        output_path
    ]

    success, stderr = await execute_ffmpeg(cmd, progress_callback=progress_callback)
    return success, stderr, output_path, meta_title


def validate_timestamp(ts: str) -> bool:
    """Validates a timestamp in HH:MM:SS or MM:SS format."""
    import re
    return bool(re.match(r"^(\d{1,2}:)?\d{1,2}:\d{2}(\.\d+)?$", ts.strip()))


def normalize_timestamp(ts: str) -> str:
    """Normalizes timestamp to HH:MM:SS format."""
    parts = ts.strip().split(":")
    if len(parts) == 2:
        return f"00:{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    elif len(parts) == 3:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
    return ts.strip()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
