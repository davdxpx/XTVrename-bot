# --- Imports ---
import contextlib

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from plugins.user_setup import track_tool_usage
from utils.log import get_logger
from utils.state import clear_session, get_data, get_state, set_state

logger = get_logger("tools.MediaInfo")

# === Handlers ===
@Client.on_callback_query(filters.regex(r"^media_info_menu$"))
async def handle_media_info_menu(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, 'media_info')
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_mediainfo_file")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            "ℹ️ **Media Info**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me any **media file** (video, audio, image)\n"
            "> to get detailed technical information.\n\n"
            "**Shows:** Codecs, resolution, bitrate, duration, streams",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]]
            ),
        )

# === Functions ===
def format_media_info(probe_data: dict, file_name: str) -> str:
    """Formats ffprobe data into a rich text message."""
    if not probe_data:
        return "❌ Could not read file information."

    fmt = probe_data.get("format", {})
    streams = probe_data.get("streams", [])

    duration_sec = float(fmt.get("duration", 0))
    hours = int(duration_sec // 3600)
    minutes = int((duration_sec % 3600) // 60)
    seconds = int(duration_sec % 60)
    duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"

    size_bytes = int(fmt.get("size", 0))
    if size_bytes >= 1024 * 1024 * 1024:
        size_str = f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        size_str = f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024:
        size_str = f"{size_bytes / 1024:.2f} KB"
    else:
        size_str = f"{size_bytes} B"

    bitrate = int(fmt.get("bit_rate", 0))
    if bitrate >= 1000000:
        bitrate_str = f"{bitrate / 1000000:.1f} Mbps"
    elif bitrate >= 1000:
        bitrate_str = f"{bitrate / 1000:.0f} Kbps"
    else:
        bitrate_str = f"{bitrate} bps" if bitrate else "N/A"

    text = (
        f"ℹ️ **Media Info**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> 📄 **File:** `{file_name}`\n"
        f"> 📦 **Format:** `{fmt.get('format_long_name', fmt.get('format_name', 'Unknown'))}`\n"
        f"> ⏱️ **Duration:** `{duration_str}`\n"
        f"> 💾 **Size:** `{size_str}`\n"
        f"> 📊 **Bitrate:** `{bitrate_str}`\n"
    )

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    sub_streams = [s for s in streams if s.get("codec_type") == "subtitle"]

    if video_streams:
        text += "\n━━━━━━━━━━━━━━━━━━━━\n\n"
        text += "🎬 **Video Streams**\n\n"
        for i, vs in enumerate(video_streams):
            width = vs.get("width", "?")
            height = vs.get("height", "?")
            codec = vs.get("codec_name", "Unknown")
            fps_str = "N/A"
            r_fps = vs.get("r_frame_rate", "")
            if r_fps and "/" in r_fps:
                num, den = r_fps.split("/")
                if int(den) > 0:
                    fps_str = f"{int(num)/int(den):.2f}"
            text += f"> **Stream {i}:** `{codec}` · `{width}x{height}` · `{fps_str} fps`\n"

    if audio_streams:
        text += "\n━━━━━━━━━━━━━━━━━━━━\n\n"
        text += "🔊 **Audio Streams**\n\n"
        for i, aus in enumerate(audio_streams):
            codec = aus.get("codec_name", "Unknown")
            channels = aus.get("channels", "?")
            sample_rate = aus.get("sample_rate", "?")
            lang = aus.get("tags", {}).get("language", "und")
            text += f"> **Stream {i}:** `{codec}` · `{channels}ch` · `{sample_rate} Hz` · `{lang}`\n"

    if sub_streams:
        text += "\n━━━━━━━━━━━━━━━━━━━━\n\n"
        text += "📝 **Subtitle Streams**\n\n"
        for i, ss in enumerate(sub_streams):
            codec = ss.get("codec_name", "Unknown")
            lang = ss.get("tags", {}).get("language", "und")
            title = ss.get("tags", {}).get("title", "")
            label = f" ({title})" if title else ""
            text += f"> **Stream {i}:** `{codec}` · `{lang}`{label}\n"

    return text

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
