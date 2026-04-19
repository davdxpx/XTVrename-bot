# --- Imports ---
import asyncio
import contextlib
import logging
import os

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from plugins.user_setup import track_tool_usage
from utils.media.ffmpeg_tools import execute_ffmpeg
from utils.telegram.log import get_logger
from utils.state import clear_session, get_data, get_state, set_state, update_data

logger = get_logger("tools.FileConverter")

# ==========================================================================
# File Converter — Mega Edition
# --------------------------------------------------------------------------
# Callback-data namespace:
#   fc_cat_{video|audio|image}    -> category root (after upload)
#   fc_sub_{submenu}              -> open submenu (keeps file in session)
#   fc_op_{opstring}              -> execute operation (opstring may contain ':')
#   fc_back_{cat|tool}            -> back navigation
#
# Operation dispatcher (see convert() below) parses opstring into
# (op_type, *params) and calls the matching _op_* builder. Each builder
# returns (ffmpeg_cmd_list, target_ext, meta_title_suffix).
# ==========================================================================

# Video container presets: (code, label, emoji).
VIDEO_CONTAINERS = [
    ("mp4",  "MP4",  "🎬"),
    ("mkv",  "MKV",  "📦"),
    ("mov",  "MOV",  "🎞"),
    ("avi",  "AVI",  "📼"),
    ("webm", "WEBM", "🌐"),
    ("flv",  "FLV",  "⚡"),
    ("3gp",  "3GP",  "📱"),
    ("ts",   "TS",   "📡"),
]

# Video codec presets: (code, label).
VIDEO_CODECS = [
    ("x264", "🔷 x264 (H.264)"),
    ("x265", "🔶 x265 (H.265)"),
    ("vp9",  "🅥 VP9"),
    ("av1",  "🅰 AV1"),
]

# Audio format presets for both extract-audio (video→audio) and audio-format (audio→audio).
AUDIO_FORMATS = [
    ("mp3",  "🎵 MP3"),
    ("m4a",  "🎶 M4A (AAC)"),
    ("ogg",  "🔊 OGG"),
    ("opus", "💠 OPUS"),
    ("flac", "💎 FLAC"),
    ("wav",  "📀 WAV"),
    ("wma",  "🪟 WMA"),
]

AUDIO_BITRATES = [
    ("128", "128 kbps"),
    ("192", "192 kbps"),
    ("256", "256 kbps"),
    ("320", "320 kbps"),
]

# Frame-extract target formats (first-frame grab from a video).
FRAME_FORMATS = [
    ("png",  "🖼 PNG"),
    ("jpg",  "📸 JPG"),
    ("webp", "🌐 WEBP"),
]

# Animated GIF presets: (code, label, fps, width).
GIF_PRESETS = [
    ("low",  "🐢 Low (10fps, 320w)",  10, 320),
    ("med",  "🚗 Med (15fps, 480w)",  15, 480),
    ("high", "🚀 High (20fps, 640w)", 20, 640),
]

# Video audio FX presets (re-encodes audio track, copies video).
VIDEO_AFX_PRESETS = [
    ("normalize", "📏 Normalize"),
    ("boost",     "🔊 Boost +6dB"),
    ("mono",      "🔇 Mono Downmix"),
]

# Video resolution transforms: (code, label, height).
VIDEO_RESOLUTIONS = [
    ("480",  "480p",  480),
    ("720",  "720p",  720),
    ("1080", "1080p", 1080),
    ("4k",   "4K",    2160),
]

# Video speed transforms: (code, label, factor).
VIDEO_SPEEDS = [
    ("05", "0.5x (slow)", 0.5),
    ("15", "1.5x",        1.5),
    ("2",  "2x (fast)",   2.0),
]

# Audio FX presets for pure-audio inputs.
AUDIO_FX_PRESETS = [
    ("normalize", "📏 Normalize"),
    ("boost",     "🔊 Boost +6dB"),
    ("bass",      "🎚 Bass Boost"),
    ("speed05",   "🐢 Speed 0.5x"),
    ("speed15",   "🚗 Speed 1.5x"),
    ("speed2",    "🚀 Speed 2x"),
    ("reverse",   "⏪ Reverse"),
    ("mono",      "🔇 Mono Downmix"),
]

# Image format presets.
IMAGE_FORMATS = [
    ("png",  "🖼 PNG"),
    ("jpg",  "📸 JPG"),
    ("webp", "🌐 WEBP"),
    ("bmp",  "🟦 BMP"),
    ("tiff", "📄 TIFF"),
    ("gif",  "🎞 GIF"),
    ("ico",  "📌 ICO"),
    ("avif", "🆕 AVIF"),
]

# Image resize presets: (code, label, kind, value).
# kind='h' → height in pixels; kind='p' → percentage scale.
IMAGE_RESIZES = [
    ("480",  "480p",  "h", 480),
    ("720",  "720p",  "h", 720),
    ("1080", "1080p", "h", 1080),
    ("4k",   "4K",    "h", 2160),
    ("50p",  "50%",   "p", 0.5),
    ("25p",  "25%",   "p", 0.25),
]

# Image rotate/flip presets.
IMAGE_ROTFLIP = [
    ("rot90",  "↻ 90°"),
    ("rot180", "↻ 180°"),
    ("rot270", "↻ 270°"),
    ("fliph",  "↔ Flip H"),
    ("flipv",  "↕ Flip V"),
]

# Image filter presets.
IMAGE_FILTERS = [
    ("gray",   "⚫ Grayscale"),
    ("invert", "🔃 Invert"),
    ("sepia",  "🟤 Sepia"),
]

# Image compression presets.
IMAGE_COMPRESS = [
    ("low",  "🗜 Low (small file)"),
    ("med",  "⚖️ Medium"),
    ("high", "💎 High quality"),
]


# === Keyboard helpers ===
def _cancel_row():
    return [InlineKeyboardButton("❌ Cancel", callback_data="cancel_rename")]


def _back_row(target: str = "cat"):
    """Back button row. target='cat' → category root; target='tool' → tool entry."""
    return [InlineKeyboardButton("🔙 Back", callback_data=f"fc_back_{target}")]


def _chunk(buttons, per_row: int = 2):
    """Group a flat list of InlineKeyboardButton into rows of `per_row`."""
    rows = []
    for i in range(0, len(buttons), per_row):
        rows.append(buttons[i:i + per_row])
    return rows

# === Tool entry ===
TOOL_ENTRY_TEXT = (
    "🔀 **File Converter — Mega Edition**\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "> Send me a **video**, **audio** or **image** file\n"
    "> and I'll show you everything I can do with it.\n\n"
    "**🎬 Video:** Container · Codec · Extract Audio · Extract Frame ·\n"
    "GIF · Audio FX · Resolution · Mute · Speed · Reverse\n\n"
    "**🎵 Audio:** MP3 · M4A · OGG · OPUS · FLAC · WAV · WMA ·\n"
    "Bitrate · Normalize · Boost · Bass · Speed · Reverse · Mono\n\n"
    "**🖼 Image:** PNG · JPG · WEBP · BMP · TIFF · GIF · ICO · AVIF ·\n"
    "Resize · Rotate · Flip · Filter · Compress"
)


@Client.on_callback_query(filters.regex(r"^file_converter_menu$"))
async def handle_file_converter_menu(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, 'file_converter')
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)
    set_state(user_id, "awaiting_convert_file")

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            TOOL_ENTRY_TEXT,
            reply_markup=InlineKeyboardMarkup([_cancel_row()]),
        )


# === Category root renderer (called after file upload by flow.py and by fc_back_cat) ===
def _category_menu_markup(file_kind: str) -> InlineKeyboardMarkup:
    """Top-level menu shown right after a file is uploaded.
    Buttons open sub-menus (`fc_sub_*`). Each sub-menu has its own Back row.
    """
    if file_kind == "video":
        rows = [
            [InlineKeyboardButton("📦 Container",   callback_data="fc_sub_container"),
             InlineKeyboardButton("🎞 Codec",       callback_data="fc_sub_codec")],
            [InlineKeyboardButton("🎵 Extract Audio", callback_data="fc_sub_xaudio"),
             InlineKeyboardButton("🖼 Extract Frame", callback_data="fc_sub_xframe")],
            [InlineKeyboardButton("🎞 GIF",          callback_data="fc_sub_gif"),
             InlineKeyboardButton("🔊 Audio FX",     callback_data="fc_sub_afx")],
            [InlineKeyboardButton("⚙️ Transform",    callback_data="fc_sub_vtransform")],
        ]
    elif file_kind == "audio":
        rows = [
            [InlineKeyboardButton("📊 Bitrate",      callback_data="fc_sub_abr"),
             InlineKeyboardButton("🔀 Format",       callback_data="fc_sub_afmt")],
            [InlineKeyboardButton("🔊 Audio FX",     callback_data="fc_sub_afx_audio")],
        ]
    elif file_kind == "image":
        rows = [
            [InlineKeyboardButton("🔀 Format",       callback_data="fc_sub_iformat"),
             InlineKeyboardButton("📐 Resize",       callback_data="fc_sub_iresize")],
            [InlineKeyboardButton("🔄 Rotate / Flip", callback_data="fc_sub_irot"),
             InlineKeyboardButton("🎨 Filter",       callback_data="fc_sub_ifilter")],
            [InlineKeyboardButton("🗜 Compress",     callback_data="fc_sub_icomp")],
        ]
    else:
        rows = []
    rows.append([InlineKeyboardButton("🔙 Back to Tool", callback_data="fc_back_tool")])
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def _category_header(file_kind: str, file_name: str | None) -> str:
    icons = {"video": "🎬", "audio": "🎵", "image": "🖼"}
    icon = icons.get(file_kind, "📄")
    name = file_name or "your file"
    return (
        f"🔀 **File Converter**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> {icon} **File:** `{name}`\n\n"
        f"Pick a category to see what I can do:"
    )


async def render_category_menu(message_or_cbq, user_id: int, *, edit: bool = False):
    """Render the category-root menu.

    - `edit=False`: send a fresh message (used by flow.py right after upload).
    - `edit=True`:  edit the existing message in place (used by fc_back_cat).
    """
    sess = get_data(user_id) or {}
    file_kind = sess.get("file_kind") or "video"
    file_name = sess.get("original_name")
    text = _category_header(file_kind, file_name)
    markup = _category_menu_markup(file_kind)

    set_state(user_id, "awaiting_convert_op")

    if edit:
        with contextlib.suppress(MessageNotModified):
            await message_or_cbq.edit_text(text, reply_markup=markup)
    else:
        await message_or_cbq.reply_text(text, reply_markup=markup)


# === Generic op-submit handler ===
async def _submit_conversion(client, callback_query, opstring: str):
    """Common code path: read file from session, kick off process_file with
    the opstring as `target_format`. The convert() dispatcher below knows how
    to parse opstrings (`<op>:<param>...`) and falls back to legacy keys.
    """
    user_id = callback_query.from_user.id
    if not get_state(user_id):
        return await callback_query.answer(
            "⚠️ Session expired. Please start again.", show_alert=True
        )
    await callback_query.answer()
    session_data = get_data(user_id)

    data = {
        "type": "convert",
        "original_name": session_data.get("original_name"),
        "file_message_id": session_data.get("file_message_id"),
        "file_chat_id": session_data.get("file_chat_id"),
        "target_format": opstring,
        "audio_bitrate": session_data.get("audio_bitrate", "192"),
        "is_auto": False,
    }

    try:
        # Replace the menu in place with a "starting..." status, then spawn the job.
        with contextlib.suppress(MessageNotModified):
            await callback_query.message.edit_text(
                "🔀 **File Converter**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"> ⏳ Initializing conversion pipeline...\n"
                f"> Op: `{opstring}`",
                reply_markup=None,
            )

        msg = await client.get_messages(
            session_data.get("file_chat_id"), session_data.get("file_message_id")
        )
        data["file_message"] = msg

        from plugins.process import process_file
        asyncio.create_task(process_file(client, callback_query.message, data))
    except Exception as e:
        logger.error(f"Failed to start conversion ({opstring}): {e}")
        with contextlib.suppress(Exception):
            await callback_query.message.edit_text(f"❌ Error: `{e}`")

    clear_session(user_id)


@Client.on_callback_query(filters.regex(r"^fc_op_(.+)$"))
async def handle_fc_op(client, callback_query):
    opstring = callback_query.data[len("fc_op_"):]
    await _submit_conversion(client, callback_query, opstring)


# === Submenu helper ===
def _submenu_markup(buttons_pairs, *, per_row: int = 2, back_target: str = "cat"):
    """Build a submenu InlineKeyboardMarkup from (label, callback_data) pairs.
    Always appends [🔙 Back] + [❌ Cancel] rows.
    """
    btns = [InlineKeyboardButton(label, callback_data=cb) for (label, cb) in buttons_pairs]
    rows = _chunk(btns, per_row=per_row)
    rows.append(_back_row(back_target))
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


async def _open_submenu(callback_query, title: str, hint: str, markup: InlineKeyboardMarkup):
    """Standard submenu rendering (edits the existing menu message)."""
    user_id = callback_query.from_user.id
    if not get_state(user_id):
        return await callback_query.answer(
            "⚠️ Session expired. Please start again.", show_alert=True
        )
    await callback_query.answer()
    sess = get_data(user_id) or {}
    file_name = sess.get("original_name") or "your file"
    text = (
        f"🔀 **File Converter — {title}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> 📄 **File:** `{file_name}`\n\n"
        f"{hint}"
    )
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(text, reply_markup=markup)


# === FC-3: Container submenu ===
@Client.on_callback_query(filters.regex(r"^fc_sub_container$"))
async def handle_fc_sub_container(client, callback_query):
    pairs = [
        (f"{emoji} {label}", f"fc_op_container:{code}")
        for code, label, emoji in VIDEO_CONTAINERS
    ]
    await _open_submenu(
        callback_query,
        title="Container",
        hint="Pick a target container. Re-encoding only happens when the chosen container needs it.",
        markup=_submenu_markup(pairs, per_row=2),
    )


# === FC-4: Codec submenu ===
@Client.on_callback_query(filters.regex(r"^fc_sub_codec$"))
async def handle_fc_sub_codec(client, callback_query):
    pairs = [(label, f"fc_op_codec:{code}") for code, label in VIDEO_CODECS]
    await _open_submenu(
        callback_query,
        title="Video Codec",
        hint="Re-encode the video track with a different codec. Audio is copied where possible.",
        markup=_submenu_markup(pairs, per_row=2),
    )


# === FC-5: Extract Audio submenu (video → audio-only file) ===
@Client.on_callback_query(filters.regex(r"^fc_sub_xaudio$"))
async def handle_fc_sub_xaudio(client, callback_query):
    pairs = [(label, f"fc_op_xaudio:{code}") for code, label in AUDIO_FORMATS if code != "wma"]
    await _open_submenu(
        callback_query,
        title="Extract Audio",
        hint="Rip the audio track out of your video and save it as a standalone file.",
        markup=_submenu_markup(pairs, per_row=2),
    )


# === FC-6: Extract Frame submenu (first-frame grab) ===
@Client.on_callback_query(filters.regex(r"^fc_sub_xframe$"))
async def handle_fc_sub_xframe(client, callback_query):
    pairs = [(label, f"fc_op_xframe:{code}") for code, label in FRAME_FORMATS]
    await _open_submenu(
        callback_query,
        title="Extract Frame",
        hint="Grab the first frame of the video as a still image.",
        markup=_submenu_markup(pairs, per_row=3),
    )


# === FC-7: Animated GIF submenu ===
@Client.on_callback_query(filters.regex(r"^fc_sub_gif$"))
async def handle_fc_sub_gif(client, callback_query):
    pairs = [(label, f"fc_op_gif:{code}") for code, label, _fps, _w in GIF_PRESETS]
    await _open_submenu(
        callback_query,
        title="Animated GIF",
        hint="Convert the whole video into an animated GIF. Higher quality → bigger file.",
        markup=_submenu_markup(pairs, per_row=1),
    )


# === FC-8: Video Audio-FX submenu (normalize / boost / mono) ===
@Client.on_callback_query(filters.regex(r"^fc_sub_afx$"))
async def handle_fc_sub_afx(client, callback_query):
    pairs = [(label, f"fc_op_vafx:{code}") for code, label in VIDEO_AFX_PRESETS]
    await _open_submenu(
        callback_query,
        title="Audio FX",
        hint="Apply an audio effect to your video. The video track is copied untouched.",
        markup=_submenu_markup(pairs, per_row=1),
    )


# === FC-13: Image Format submenu ===
@Client.on_callback_query(filters.regex(r"^fc_sub_iformat$"))
async def handle_fc_sub_iformat(client, callback_query):
    pairs = [(label, f"fc_op_iformat:{code}") for code, label in IMAGE_FORMATS]
    await _open_submenu(
        callback_query,
        title="Image Format",
        hint="Convert the image to a different format.",
        markup=_submenu_markup(pairs, per_row=2),
    )


# === FC-14: Image Resize submenu ===
@Client.on_callback_query(filters.regex(r"^fc_sub_iresize$"))
async def handle_fc_sub_iresize(client, callback_query):
    pairs = [(label, f"fc_op_iresize:{code}") for code, label, _k, _v in IMAGE_RESIZES]
    await _open_submenu(
        callback_query,
        title="Image Resize",
        hint="Scale the image while preserving aspect ratio.",
        markup=_submenu_markup(pairs, per_row=3),
    )


# === FC-15: Image Rotate / Flip submenu ===
@Client.on_callback_query(filters.regex(r"^fc_sub_irot$"))
async def handle_fc_sub_irot(client, callback_query):
    pairs = [(label, f"fc_op_irot:{code}") for code, label in IMAGE_ROTFLIP]
    await _open_submenu(
        callback_query,
        title="Rotate / Flip",
        hint="Rotate or flip the image.",
        markup=_submenu_markup(pairs, per_row=3),
    )


# === FC-16: Image Filter submenu ===
@Client.on_callback_query(filters.regex(r"^fc_sub_ifilter$"))
async def handle_fc_sub_ifilter(client, callback_query):
    pairs = [(label, f"fc_op_ifilter:{code}") for code, label in IMAGE_FILTERS]
    await _open_submenu(
        callback_query,
        title="Image Filter",
        hint="Apply a color filter.",
        markup=_submenu_markup(pairs, per_row=3),
    )


# === FC-17: Image Compress submenu ===
@Client.on_callback_query(filters.regex(r"^fc_sub_icomp$"))
async def handle_fc_sub_icomp(client, callback_query):
    pairs = [(label, f"fc_op_icomp:{code}") for code, label in IMAGE_COMPRESS]
    await _open_submenu(
        callback_query,
        title="Image Compress",
        hint="Adjust file size vs. quality.",
        markup=_submenu_markup(pairs, per_row=1),
    )


# === FC-10: Audio Bitrate submenu (pure-audio input) ===
@Client.on_callback_query(filters.regex(r"^fc_sub_abr$"))
async def handle_fc_sub_abr(client, callback_query):
    user_id = callback_query.from_user.id
    sess = get_data(user_id) or {}
    current = sess.get("audio_bitrate", "192")
    pairs = []
    for code, label in AUDIO_BITRATES:
        marker = " ✅" if code == current else ""
        pairs.append((f"{label}{marker}", f"fc_setbr:{code}"))
    await _open_submenu(
        callback_query,
        title="Audio Bitrate",
        hint=(
            f"Pick the default bitrate for lossy formats (MP3/M4A/OPUS/WMA).\n"
            f"Currently: **{current} kbps**. After choosing, pick a Format."
        ),
        markup=_submenu_markup(pairs, per_row=2),
    )


# Handle fc_setbr: store bitrate in session, then go back to category menu.
@Client.on_callback_query(filters.regex(r"^fc_setbr:(.+)$"))
async def handle_fc_setbr(client, callback_query):
    user_id = callback_query.from_user.id
    if not get_state(user_id):
        return await callback_query.answer(
            "⚠️ Session expired. Please start again.", show_alert=True
        )
    code = callback_query.data.split(":", 1)[1]
    update_data(user_id, "audio_bitrate", code)
    await callback_query.answer(f"Bitrate set to {code} kbps", show_alert=False)
    await render_category_menu(callback_query.message, user_id, edit=True)


# === FC-11: Audio Format submenu (pure-audio input → audio-file) ===
@Client.on_callback_query(filters.regex(r"^fc_sub_afmt$"))
async def handle_fc_sub_afmt(client, callback_query):
    user_id = callback_query.from_user.id
    sess = get_data(user_id) or {}
    br = sess.get("audio_bitrate", "192")
    pairs = [(label, f"fc_op_afmt:{code}") for code, label in AUDIO_FORMATS]
    await _open_submenu(
        callback_query,
        title="Audio Format",
        hint=f"Convert the audio file to a different format.\nBitrate for lossy codecs: **{br} kbps** (change via Bitrate menu).",
        markup=_submenu_markup(pairs, per_row=2),
    )


# === FC-12: Audio FX submenu (pure-audio input) ===
@Client.on_callback_query(filters.regex(r"^fc_sub_afx_audio$"))
async def handle_fc_sub_afx_audio(client, callback_query):
    pairs = [(label, f"fc_op_aafx:{code}") for code, label in AUDIO_FX_PRESETS]
    await _open_submenu(
        callback_query,
        title="Audio FX",
        hint="Apply an audio effect. Output is re-encoded to MP3 @ current bitrate.",
        markup=_submenu_markup(pairs, per_row=2),
    )


# === FC-9: Video Transform submenu (resolution / mute / speed / reverse) ===
@Client.on_callback_query(filters.regex(r"^fc_sub_vtransform$"))
async def handle_fc_sub_vtransform(client, callback_query):
    pairs = []
    for code, label, _h in VIDEO_RESOLUTIONS:
        pairs.append((f"📐 {label}", f"fc_op_vres:{code}"))
    pairs.append(("🔇 Mute Audio", "fc_op_vmute:on"))
    for code, label, _f in VIDEO_SPEEDS:
        pairs.append((f"⏱ {label}", f"fc_op_vspeed:{code}"))
    pairs.append(("⏪ Reverse", "fc_op_vreverse:on"))
    await _open_submenu(
        callback_query,
        title="Video Transform",
        hint="Change resolution, mute the audio, speed the video up/down or reverse it.",
        markup=_submenu_markup(pairs, per_row=2),
    )


# === FC-18: Universal back handlers ===
@Client.on_callback_query(filters.regex(r"^fc_back_cat$"))
async def handle_fc_back_cat(client, callback_query):
    """Return to the category-root menu (file remains in session)."""
    user_id = callback_query.from_user.id
    if not get_state(user_id):
        return await callback_query.answer(
            "⚠️ Session expired. Please start again.", show_alert=True
        )
    await callback_query.answer()
    await render_category_menu(callback_query.message, user_id, edit=True)


@Client.on_callback_query(filters.regex(r"^fc_back_tool$"))
async def handle_fc_back_tool(client, callback_query):
    """Return to tool entry (session reset — user must upload a new file)."""
    user_id = callback_query.from_user.id
    await callback_query.answer()
    clear_session(user_id)
    set_state(user_id, "awaiting_convert_file")
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            TOOL_ENTRY_TEXT,
            reply_markup=InlineKeyboardMarkup([_cancel_row()]),
        )


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
        reply_msg = await client.send_message(
            user_id,
            "🔀 **File Converter**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> ⏳ Initializing conversion pipeline..."
        )
        from plugins.process import process_file

        asyncio.create_task(process_file(client, reply_msg, data))
    except Exception as e:
        logger.error(f"Failed to get message for convert mode: {e}")
        await client.send_message(user_id, f"Error: {e}")

    clear_session(user_id)

# ==========================================================================
# FFmpeg operation builders
# --------------------------------------------------------------------------
# Each builder accepts (input_path, output_path, *params) and returns a list
# of strings (the ffmpeg argv). The convert() dispatcher picks the builder
# based on the op-type prefix in the opstring.
# ==========================================================================


# Shared helper: audio-only encoder args for a given format+bitrate.
def _audio_encoder_args(fmt: str, bitrate: str | None = None) -> list[str]:
    fmt = fmt.lower()
    br = (bitrate or "192").strip()
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", f"{br}k"]
    if fmt == "m4a":
        return ["-c:a", "aac", "-b:a", f"{br}k"]
    if fmt == "ogg":
        return ["-c:a", "libvorbis", "-q:a", "5"]
    if fmt == "opus":
        return ["-c:a", "libopus", "-b:a", f"{br}k"]
    if fmt == "flac":
        return ["-c:a", "flac"]
    if fmt == "wav":
        return ["-c:a", "pcm_s16le"]
    if fmt == "wma":
        return ["-c:a", "wmav2", "-b:a", f"{br}k"]
    return ["-c:a", "copy"]


# FC-5: Extract-audio op — strip video stream, re-encode audio to target fmt.
def _op_xaudio(input_path: str, output_path: str, fmt: str) -> list[str]:
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vn"]
    cmd.extend(_audio_encoder_args(fmt))
    cmd.append(output_path)
    return cmd


# FC-6: Extract-frame op — first frame as still image.
def _op_xframe(input_path: str, output_path: str, fmt: str) -> list[str]:
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vframes", "1"]
    fmt = fmt.lower()
    if fmt == "webp":
        cmd.extend(["-c:v", "libwebp", "-q:v", "90"])
    elif fmt == "jpg":
        cmd.extend(["-q:v", "2"])
    # PNG: default lossless, no extra args.
    cmd.append(output_path)
    return cmd


# FC-4: Codec op — re-encode video track with the chosen codec.
def _op_codec(input_path: str, output_path: str, codec: str) -> list[str]:
    codec = codec.lower()
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if codec == "x264":
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "copy", "-c:s", "copy"])
    elif codec == "x265":
        cmd.extend(["-c:v", "libx265", "-preset", "fast", "-crf", "28",
                    "-c:a", "copy", "-c:s", "copy"])
    elif codec == "vp9":
        cmd.extend(["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32",
                    "-c:a", "libopus", "-b:a", "128k"])
    elif codec == "av1":
        cmd.extend(["-c:v", "libaom-av1", "-crf", "30", "-b:v", "0",
                    "-cpu-used", "6",
                    "-c:a", "libopus", "-b:a", "128k"])
    else:
        cmd.extend(["-c", "copy"])
    cmd.append(output_path)
    return cmd


# FC-3: Container op — remux (or re-encode when the container demands it).
def _op_container(input_path: str, output_path: str, fmt: str) -> list[str]:
    fmt = fmt.lower()
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if fmt in ("mp4", "mkv", "mov", "ts"):
        # Stream-copy friendly containers.
        cmd.extend(["-c", "copy", "-map", "0"])
    elif fmt == "avi":
        # AVI chokes on some modern audio codecs — force AAC audio.
        cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"])
    elif fmt == "webm":
        # WebM requires VP8/VP9 + Vorbis/Opus.
        cmd.extend(["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32",
                    "-c:a", "libopus", "-b:a", "128k"])
    elif fmt == "flv":
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-f", "flv"])
    elif fmt == "3gp":
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "28",
                    "-s", "352x288", "-r", "15",
                    "-c:a", "aac", "-b:a", "32k", "-ar", "8000", "-ac", "1"])
    else:
        cmd.extend(["-c", "copy"])
    cmd.append(output_path)
    return cmd


# FC-13: Image Format op — encode image to chosen format.
def _op_iformat(input_path: str, output_path: str, fmt: str) -> list[str]:
    fmt = fmt.lower()
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if fmt == "jpg":
        cmd.extend(["-q:v", "2"])
    elif fmt == "webp":
        cmd.extend(["-c:v", "libwebp", "-q:v", "90"])
    elif fmt == "avif":
        cmd.extend(["-c:v", "libaom-av1", "-still-picture", "1", "-crf", "30"])
    elif fmt == "ico":
        cmd.extend(["-vf", "scale=256:256"])
    elif fmt == "gif":
        cmd.extend(["-vf", "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"])
    elif fmt == "bmp":
        cmd.extend(["-c:v", "bmp"])
    elif fmt == "tiff":
        cmd.extend(["-c:v", "tiff"])
    # PNG: default is lossless; no extra args needed.
    cmd.append(output_path)
    return cmd


# FC-14: Image Resize op — scale using lanczos.
def _op_iresize(input_path: str, output_path: str, code: str) -> list[str]:
    kind, value = "h", 720
    for c, _label, k, v in IMAGE_RESIZES:
        if c == code:
            kind, value = k, v
            break
    if kind == "h":
        vf = f"scale=-2:{int(value)}:flags=lanczos"
    else:
        vf = f"scale=iw*{float(value)}:ih*{float(value)}:flags=lanczos"
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vf,
        output_path,
    ]


# FC-15: Image Rotate/Flip op.
def _op_irot(input_path: str, output_path: str, code: str) -> list[str]:
    code = code.lower()
    mapping = {
        "rot90":  "transpose=1",
        "rot180": "transpose=1,transpose=1",
        "rot270": "transpose=2",
        "fliph":  "hflip",
        "flipv":  "vflip",
    }
    vf = mapping.get(code, "null")
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vf,
        output_path,
    ]


# FC-16: Image Filter op — color manipulations.
def _op_ifilter(input_path: str, output_path: str, code: str) -> list[str]:
    code = code.lower()
    if code == "gray":
        vf = "format=gray"
    elif code == "invert":
        vf = "negate"
    elif code == "sepia":
        # Classic sepia matrix.
        vf = ("colorchannelmixer="
              "rr=.393:rg=.769:rb=.189:"
              "gr=.349:gg=.686:gb=.168:"
              "br=.272:bg=.534:bb=.131")
    else:
        vf = "null"
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vf,
        output_path,
    ]


# FC-17: Image Compress op — quality presets.
def _op_icomp(input_path: str, output_path: str, code: str) -> list[str]:
    code = code.lower()
    # q:v scale for JPG/MJPEG: 2 (best) .. 31 (worst).
    if code == "low":
        q = 15  # small file
    elif code == "med":
        q = 7
    else:  # high
        q = 2
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-q:v", str(q),
        output_path,
    ]


# FC-11: Audio Format op — re-encode pure-audio input to target format.
# Opstring is `afmt:<fmt>` (bitrate pulled from session by dispatcher).
def _op_afmt(input_path: str, output_path: str, fmt: str, bitrate: str = "192") -> list[str]:
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vn"]
    cmd.extend(_audio_encoder_args(fmt, bitrate))
    cmd.append(output_path)
    return cmd


# FC-12: Audio FX op — apply a filter to a pure-audio file.
def _op_aafx(input_path: str, output_path: str, fx: str, bitrate: str = "192") -> list[str]:
    fx = fx.lower()
    if fx == "normalize":
        af = "loudnorm=I=-16:TP=-1.5:LRA=11"
    elif fx == "boost":
        af = "volume=6dB"
    elif fx == "bass":
        af = "bass=g=8"
    elif fx == "speed05":
        af = "atempo=0.5"
    elif fx == "speed15":
        af = "atempo=1.5"
    elif fx == "speed2":
        af = "atempo=2.0"
    elif fx == "reverse":
        af = "areverse"
    elif fx == "mono":
        af = "pan=mono|c0=0.5*c0+0.5*c1"
    else:
        af = "anull"
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-vn",
        "-af", af,
        "-c:a", "libmp3lame", "-b:a", f"{bitrate}k",
        output_path,
    ]


# FC-9: Video resolution op — scale to target height, preserve aspect ratio.
def _op_vres(input_path: str, output_path: str, code: str) -> list[str]:
    height = 720
    for c, _label, h in VIDEO_RESOLUTIONS:
        if c == code:
            height = h
            break
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        output_path,
    ]


# FC-9: Mute audio — drop the audio track, copy video.
def _op_vmute(input_path: str, output_path: str, _arg: str = "on") -> list[str]:
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "copy", "-an",
        output_path,
    ]


# FC-9: Video speed op — change playback speed of video+audio together.
def _op_vspeed(input_path: str, output_path: str, code: str) -> list[str]:
    factor = 1.0
    for c, _label, f in VIDEO_SPEEDS:
        if c == code:
            factor = f
            break
    # setpts uses 1/factor (faster video → smaller PTS).
    vpts = 1.0 / factor
    # atempo only accepts 0.5..2.0; chain for extremes.
    if factor >= 2.0:
        atempo_chain = "atempo=2.0"
    elif factor <= 0.5:
        atempo_chain = "atempo=0.5"
    else:
        atempo_chain = f"atempo={factor}"
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        f"[0:v]setpts={vpts}*PTS[v];[0:a]{atempo_chain}[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]


# FC-9: Reverse video — both audio and video reversed.
def _op_vreverse(input_path: str, output_path: str, _arg: str = "on") -> list[str]:
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", "reverse", "-af", "areverse",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]


# FC-8: Video Audio-FX op — re-encode audio with a filter, copy video/subs.
def _op_vafx(input_path: str, output_path: str, fx: str) -> list[str]:
    fx = fx.lower()
    if fx == "normalize":
        af = "loudnorm=I=-16:TP=-1.5:LRA=11"
    elif fx == "boost":
        af = "volume=6dB"
    elif fx == "mono":
        af = "pan=mono|c0=0.5*c0+0.5*c1"
    else:
        af = "anull"
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "copy", "-c:s", "copy",
        "-af", af,
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]


# FC-7: Animated GIF op — build a looped GIF with chosen fps/width preset.
def _op_gif(input_path: str, output_path: str, preset: str) -> list[str]:
    preset = preset.lower()
    fps, width = 10, 320  # default = low
    for code, _label, f, w in GIF_PRESETS:
        if code == preset:
            fps, width = f, w
            break
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    return [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vf,
        "-c:v", "gif",
        "-loop", "0",
        output_path,
    ]


# ==========================================================================
# FC-19: Operation dispatcher
# --------------------------------------------------------------------------
# Maps op-type prefix → (builder, extension resolver).
# Extension resolver takes the param string and returns the target file ext.
# Builders return the ffmpeg argv list.
# ==========================================================================

def _ext_same_as_param(param: str) -> str:
    return param.split(":", 1)[0].lower()


def _ext_fixed(ext: str):
    def _f(_param: str) -> str:
        return ext
    return _f


# (builder_fn, ext_resolver_fn, takes_bitrate_from_session)
OP_HANDLERS = {
    "container": (_op_container, _ext_same_as_param, False),
    "codec":     (_op_codec,     _ext_fixed("mkv"),   False),
    "xaudio":    (_op_xaudio,    _ext_same_as_param,  False),
    "xframe":    (_op_xframe,    _ext_same_as_param,  False),
    "gif":       (_op_gif,       _ext_fixed("gif"),   False),
    "vafx":      (_op_vafx,      _ext_fixed("mp4"),   False),
    "vres":      (_op_vres,      _ext_fixed("mp4"),   False),
    "vmute":     (_op_vmute,     _ext_fixed("mp4"),   False),
    "vspeed":    (_op_vspeed,    _ext_fixed("mp4"),   False),
    "vreverse":  (_op_vreverse,  _ext_fixed("mp4"),   False),
    "afmt":      (_op_afmt,      _ext_same_as_param,  True),
    "aafx":      (_op_aafx,      _ext_fixed("mp3"),   True),
    "iformat":   (_op_iformat,   _ext_same_as_param,  False),
    "iresize":   (_op_iresize,   None,                False),  # uses input ext
    "irot":      (_op_irot,      None,                False),  # uses input ext
    "ifilter":   (_op_ifilter,   None,                False),  # uses input ext
    "icomp":     (_op_icomp,     None,                False),  # uses input ext
}


# Legacy aliases keep backwards compatibility with the old flat ^convert_to_*
# callbacks and existing process.py code path.
_LEGACY_SIMPLE_EXTS = {
    "mp3": "mp3", "m4a": "m4a", "ogg": "ogg", "opus": "opus",
    "flac": "flac", "wav": "wav", "wma": "wma",
    "mp4": "mp4", "mkv": "mkv", "mov": "mov", "webm": "webm",
    "avi": "avi", "flv": "flv", "3gp": "3gp", "ts": "ts",
    "png": "png", "jpg": "jpg", "jpeg": "jpg", "webp": "webp",
    "bmp": "bmp", "tiff": "tiff", "ico": "ico", "avif": "avif",
    "gif": "gif",
    "x264": "mkv", "x265": "mkv", "audionorm": "mkv",
}


def _build_legacy_cmd(input_path: str, output_path: str, target_format: str) -> list[str]:
    """Old flat-format ffmpeg command builder (kept for backward-compat)."""
    cmd = ["ffmpeg", "-y", "-i", input_path]
    if target_format == "mp3":
        cmd.extend(["-vn", "-c:a", "libmp3lame", "-q:a", "2"])
    elif target_format == "gif":
        cmd.extend(["-vf", "fps=10,scale=320:-1:flags=lanczos", "-c:v", "gif"])
    elif target_format in ("png", "jpg", "jpeg", "webp"):
        cmd.extend(["-vframes", "1"])
    elif target_format == "x264":
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "copy", "-c:s", "copy"])
    elif target_format == "x265":
        cmd.extend(["-c:v", "libx265", "-preset", "fast", "-crf", "28",
                    "-c:a", "copy", "-c:s", "copy"])
    elif target_format == "audionorm":
        cmd.extend(["-c:v", "copy", "-c:s", "copy",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-c", "copy"])
    cmd.append(output_path)
    return cmd


# === Functions ===
async def convert(input_path: str, output_dir: str, safe_title: str, target_format: str, progress_callback=None, session_data: dict | None = None) -> tuple[bool, bytes, str, str]:
    """
    Converts a media file using FFmpeg.

    `target_format` can be:
      - a legacy flat string (e.g. "mp3", "x264", "gif", "png")  → handled via _build_legacy_cmd
      - an opstring "<op>:<param>[:<param>...]"                  → dispatched via OP_HANDLERS

    `session_data` (optional) is used by op handlers that need extra context,
    e.g. `afmt`/`aafx` read the user-selected audio bitrate.

    Returns: (success, stderr, output_path, meta_title)
    """
    meta_title = f"{safe_title}"

    # ---- New opstring path -----------------------------------------------
    if ":" in target_format:
        op, _, param = target_format.partition(":")
        entry = OP_HANDLERS.get(op)
        if entry is not None:
            builder, ext_resolver, needs_bitrate = entry

            # Ext resolution.
            if ext_resolver is None:
                # Preserve input file extension (image transforms).
                _, in_ext = os.path.splitext(input_path)
                target_ext = in_ext.lstrip(".").lower() or "out"
            else:
                target_ext = ext_resolver(param)

            final_filename = f"{safe_title}.{target_ext}"
            output_path = os.path.join(output_dir, final_filename)

            # Build cmd.
            if needs_bitrate:
                bitrate = "192"
                if session_data and session_data.get("audio_bitrate"):
                    bitrate = str(session_data["audio_bitrate"])
                cmd = builder(input_path, output_path, param, bitrate)
            else:
                cmd = builder(input_path, output_path, param)

            success, stderr = await execute_ffmpeg(cmd, progress_callback=progress_callback)
            return success, stderr, output_path, meta_title

        # Unknown op → fall through to legacy handling (likely fails fast).
        logger.warning(f"convert(): unknown opstring op='{op}', falling back to legacy")

    # ---- Legacy flat-format path -----------------------------------------
    target_ext = _LEGACY_SIMPLE_EXTS.get(target_format, target_format)
    final_filename = f"{safe_title}.{target_ext}"
    output_path = os.path.join(output_dir, final_filename)
    cmd = _build_legacy_cmd(input_path, output_path, target_format)

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
