# --- Imports ---
from pyrogram.errors import MessageNotModified
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.state import set_state, get_state, get_data, clear_session
from utils.log import get_logger
import asyncio
from utils.ffmpeg_tools import execute_ffmpeg

logger = get_logger("tools.VoiceNoteConverter")

# === Handlers ===
@Client.on_callback_query(filters.regex(r"^voice_converter_menu$"))
async def handle_voice_converter_menu(client, callback_query):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_voice_file")

    try:
        await callback_query.message.edit_text(
            "🎙️ **Voice Note Converter**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me an **audio file** to convert it into\n"
            "> a Telegram **voice note** (OGG Opus).\n\n"
            "**Supported:** MP3, FLAC, M4A, WAV, AAC, OGG",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )
    except MessageNotModified:
        pass

# === Functions ===
async def convert_to_voice(input_path: str, output_dir: str, safe_title: str, progress_callback=None) -> tuple[bool, bytes, str, str]:
    """
    Converts an audio file to OGG Opus format for Telegram voice notes.
    Returns: (success, stderr, output_path, meta_title)
    """
    import os
    final_filename = f"{safe_title}_voice.ogg"
    meta_title = f"{safe_title}"
    output_path = os.path.join(output_dir, final_filename)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:a", "libopus",
        "-b:a", "128k",
        "-vbr", "on",
        "-application", "voip",
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
