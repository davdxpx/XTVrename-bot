# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Confirm-screen pickers: codec / audio / specials.

Three multi-page pickers the user reaches from the confirmation
screen when the active filename template references ``{Codec}``,
``{Audio}``, or ``{Specials}``. Each picker stores its current page
per file-session so paging doesn't survive picker switches but does
survive a round-trip through Change Audio → Back → Change Audio.

Picker values are indexed in callback_data because several labels
contain characters that don't round-trip through ``"_".split()``
(e.g. ``"AAC 5.1"``, ``"DD+ Atmos"``, ``"MPEG-2"``). ``set_codec_``
and ``set_audio_`` callbacks encode the index as ``iN`` and decode
back to the label from the module-level option lists.

SOURCE dedup lives in the specials toggle: when the user picks a
SOURCE-group label (BluRay, WEB-DL, BDRip…) any previously-selected
SOURCE-group label is dropped automatically — a release can't be
BluRay AND BDRip at the same time.

PR B (follow-up) will split ``_SPECIALS_OPTIONS`` into five dedicated
pickers (Source / HDR / Edition / Release / Extras) so ``{Edition}``,
``{HDR}`` etc. are individually user-pickable; until then Specials
remains the catch-all bucket it always has been.
"""

import contextlib
import re

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from plugins.flow.sessions import file_sessions
from utils.auth import auth_filter
from utils.telegram.log import get_logger
from utils.ui_pagination import paginate_kb

logger = get_logger("plugins.flow.pickers")


# --- Picker option lists -----------------------------------------------------
_CODEC_OPTIONS: list[str] = [
    "x264", "x265", "HEVC", "AVC", "AV1",
    "VP9", "MPEG-2", "VC-1", "XviD", "DivX",
]

_AUDIO_OPTIONS: list[str] = [
    # Atmos combos lead so they're easy to reach
    "TrueHD Atmos", "DD+ Atmos", "DDP Atmos", "EAC3 Atmos",
    "DTS-HD MA", "DTS-HD", "DTS:X", "DTS-ES",
    "Atmos", "TrueHD",
    "DDP5.1", "DDP7.1", "DDP2.0", "DDP", "DD+",
    "EAC3", "DD5.1", "DD7.1", "DD2.0", "AC3", "DD",
    "DTS", "AAC 5.1", "AAC 2.0", "AAC", "FLAC", "ALAC",
    "MP3", "OPUS",
    "DUAL", "Multi", "DL", "Dubbed", "MicDub", "LineDub",
]

_SPECIALS_OPTIONS: list[str] = [
    # SOURCE (streaming + physical) — only one of these can coexist.
    "BluRay", "UHD BluRay", "BDRip", "BRRip",
    "WEB-DL", "WEBRip", "WEB",
    "AMZN WEB-DL", "NF WEB-DL", "DSNP WEB-DL", "HULU WEB-DL",
    "MAX WEB-DL", "HMAX WEB-DL", "ATVP WEB-DL", "PMTP WEB-DL",
    "HDTV", "DVDRip", "DVD", "VHS", "HDRip", "CAM", "TS",
    # HDR
    "HDR", "HDR10", "HDR10+", "Dolby Vision",
    "DV P5", "DV P7", "HLG", "SDR",
    # Edition
    "Extended", "Director's Cut", "Extended Edition", "Extended Cut",
    "Ultimate Edition", "Special Edition", "Theatrical Cut",
    "Final Cut", "IMAX", "IMAX Enhanced",
    "Unrated", "Uncut", "Remastered",
    # Release
    "REMUX", "PROPER", "REPACK", "RERIP",
    "Criterion", "INTERNAL", "LIMITED",
    # Extras
    "DUAL", "Multi", "Dual Audio", "Multi Audio",
    "Dubbed", "MicDub", "LineDub", "Subbed",
    "HardSubs", "SoftSubs", "HardCoded", "DL",
]

# SOURCE_LABELS is the subset of _SPECIALS_OPTIONS that counts as a
# "source" for dedup purposes. Kept explicit rather than derived so a
# future edit to the options list can't silently change dedup scope.
_SOURCE_LABELS: set[str] = {
    "BluRay", "UHD BluRay", "BDRip", "BRRip",
    "WEB-DL", "WEBRip", "WEB",
    "AMZN WEB-DL", "NF WEB-DL", "DSNP WEB-DL", "HULU WEB-DL",
    "MAX WEB-DL", "HMAX WEB-DL", "ATVP WEB-DL", "PMTP WEB-DL",
    "HDTV", "DVDRip", "DVD", "VHS", "HDRip", "CAM", "TS",
}

_PICKER_PER_PAGE = 9
_PICKER_PER_ROW = 3


# --- Per-session paging helpers ---------------------------------------------
def _picker_page(fs: dict, name: str) -> int:
    """Read current page for a picker out of the file session."""
    pages = fs.setdefault("picker_pages", {})
    return int(pages.get(name, 0))


def _set_picker_page(fs: dict, name: str, page: int) -> None:
    pages = fs.setdefault("picker_pages", {})
    pages[name] = max(0, int(page))


# --- Keyboard builders -------------------------------------------------------
def _build_codec_keyboard(msg_id: int, fs: dict) -> InlineKeyboardMarkup:
    current = fs.get("codec", "")
    locked = bool(fs.get("codec_locked"))
    page = _picker_page(fs, "codec")
    items = [(str(i), label) for i, label in enumerate(_CODEC_OPTIONS)]
    none_text = "🚫 None (locked)" if locked else ("✅ None" if not current else "None")
    extras = [
        [InlineKeyboardButton(none_text, callback_data=f"set_codec_none_{msg_id}")],
        [InlineKeyboardButton("← Back", callback_data=f"back_confirm_{msg_id}")],
    ]
    current_key = (
        str(_CODEC_OPTIONS.index(current)) if current in _CODEC_OPTIONS else None
    )
    rows = paginate_kb(
        items=items,
        page=page,
        per_page=_PICKER_PER_PAGE,
        per_row=_PICKER_PER_ROW,
        selected={current_key} if current_key else set(),
        cb_template=lambda idx: f"set_codec_i{idx}_{msg_id}",
        page_cb_template=lambda p: f"codec_pg_{p}_{msg_id}",
        extra_rows=extras,
    )
    return InlineKeyboardMarkup(rows)


def _build_audio_keyboard(msg_id: int, fs: dict) -> InlineKeyboardMarkup:
    current = fs.get("audio", "")
    locked = bool(fs.get("audio_locked"))
    page = _picker_page(fs, "audio")
    items = [(str(i), label) for i, label in enumerate(_AUDIO_OPTIONS)]
    none_text = "🚫 None (locked)" if locked else ("✅ None" if not current else "None")
    extras = [
        [InlineKeyboardButton(none_text, callback_data=f"set_audio_none_{msg_id}")],
        [InlineKeyboardButton("← Back", callback_data=f"back_confirm_{msg_id}")],
    ]
    current_key = (
        str(_AUDIO_OPTIONS.index(current)) if current in _AUDIO_OPTIONS else None
    )
    rows = paginate_kb(
        items=items,
        page=page,
        per_page=_PICKER_PER_PAGE,
        per_row=_PICKER_PER_ROW,
        selected={current_key} if current_key else set(),
        cb_template=lambda idx: f"set_audio_i{idx}_{msg_id}",
        page_cb_template=lambda p: f"audio_pg_{p}_{msg_id}",
        extra_rows=extras,
    )
    return InlineKeyboardMarkup(rows)


def _build_specials_keyboard(msg_id: int, fs: dict) -> InlineKeyboardMarkup:
    current: list[str] = fs.get("specials", []) or []
    locked = bool(fs.get("specials_locked"))
    page = _picker_page(fs, "specials")
    items = [(str(i), label) for i, label in enumerate(_SPECIALS_OPTIONS)]
    selected_keys = {
        str(i) for i, label in enumerate(_SPECIALS_OPTIONS) if label in current
    }
    lock_label = "🚫 None (locked)" if locked else "🚫 None (lock)"
    extras = [
        [
            InlineKeyboardButton("❌ Clear All", callback_data=f"clear_spc_{msg_id}"),
            InlineKeyboardButton(lock_label, callback_data=f"lock_spc_{msg_id}"),
        ],
        [InlineKeyboardButton("✅ Done", callback_data=f"back_confirm_{msg_id}")],
    ]
    rows = paginate_kb(
        items=items,
        page=page,
        per_page=_PICKER_PER_PAGE,
        per_row=_PICKER_PER_ROW,
        selected=selected_keys,
        cb_template=lambda idx: f"toggle_spc_i{idx}_{msg_id}",
        page_cb_template=lambda p: f"specials_pg_{p}_{msg_id}",
        extra_rows=extras,
    )
    return InlineKeyboardMarkup(rows)


def _codec_prompt() -> str:
    return (
        "📼 **Select Codec:**\nChoose a codec for the template. "
        "Pick **None** to lock — auto-fill won't overwrite it."
    )


def _audio_prompt() -> str:
    return (
        "🔊 **Select Audio:**\nChoose an audio tag for the template. "
        "Pick **None** to lock — auto-fill won't overwrite it even if "
        "Dual/Multi streams are detected."
    )


def _specials_prompt(selected_count: int) -> str:
    hint = ""
    if selected_count:
        hint = f"\n**{selected_count}** currently selected."
    return (
        "🎬 **Select Specials:**\nToggle specials for the template "
        "(multiple allowed). Only one **source** can be active at a "
        "time — picking BDRip removes BluRay, etc."
        f"{hint}"
    )


# --- Codec callbacks ---------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^ch_codec_") & auth_filter)
async def handle_change_codec(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    # Reset to page 0 when entering fresh (preserves deep-link state
    # when a picker-page callback re-enters this handler, though that
    # doesn't happen with the current grammar).
    _set_picker_page(fs, "codec", 0)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _codec_prompt(),
            reply_markup=_build_codec_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^codec_pg_(\d+)_(\d+)$") & auth_filter)
async def handle_codec_page(client, callback_query):
    m = re.match(r"^codec_pg_(\d+)_(\d+)$", callback_query.data)
    if not m:
        return
    page, msg_id = int(m.group(1)), int(m.group(2))
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "codec", page)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _codec_prompt(),
            reply_markup=_build_codec_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^set_codec_") & auth_filter)
async def handle_set_codec(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    parts = callback_query.data.split("_")
    payload = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    if payload == "none":
        fs["codec"] = ""
        fs["codec_locked"] = True
    elif payload.startswith("i") and payload[1:].isdigit():
        idx = int(payload[1:])
        if 0 <= idx < len(_CODEC_OPTIONS):
            fs["codec"] = _CODEC_OPTIONS[idx]
            fs["codec_locked"] = False
        else:
            await callback_query.answer("Unknown codec option.", show_alert=True)
            return
    else:
        # Legacy callback (pre-v1.6.2) — tolerate it so in-flight
        # sessions at upgrade time don't dead-end.
        fs["codec"] = payload
        fs["codec_locked"] = False

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


# --- Audio callbacks ---------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^ch_audio_") & auth_filter)
async def handle_change_audio(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "audio", 0)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _audio_prompt(),
            reply_markup=_build_audio_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^audio_pg_(\d+)_(\d+)$") & auth_filter)
async def handle_audio_page(client, callback_query):
    m = re.match(r"^audio_pg_(\d+)_(\d+)$", callback_query.data)
    if not m:
        return
    page, msg_id = int(m.group(1)), int(m.group(2))
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "audio", page)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _audio_prompt(),
            reply_markup=_build_audio_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^set_audio_") & auth_filter)
async def handle_set_audio(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    parts = callback_query.data.split("_")
    payload = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    if payload == "none":
        fs["audio"] = ""
        fs["audio_locked"] = True
    elif payload.startswith("i") and payload[1:].isdigit():
        idx = int(payload[1:])
        if 0 <= idx < len(_AUDIO_OPTIONS):
            fs["audio"] = _AUDIO_OPTIONS[idx]
            fs["audio_locked"] = False
        else:
            await callback_query.answer("Unknown audio option.", show_alert=True)
            return
    else:
        fs["audio"] = payload
        fs["audio_locked"] = False

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


# --- Specials callbacks ------------------------------------------------------
@Client.on_callback_query(filters.regex(r"^ch_specials_") & auth_filter)
async def handle_change_specials(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "specials", 0)
    selected = fs.get("specials", []) or []
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _specials_prompt(len(selected)),
            reply_markup=_build_specials_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^specials_pg_(\d+)_(\d+)$") & auth_filter)
async def handle_specials_page(client, callback_query):
    m = re.match(r"^specials_pg_(\d+)_(\d+)$", callback_query.data)
    if not m:
        return
    page, msg_id = int(m.group(1)), int(m.group(2))
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "specials", page)
    selected = fs.get("specials", []) or []
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _specials_prompt(len(selected)),
            reply_markup=_build_specials_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^toggle_spc_") & auth_filter)
async def handle_toggle_specials(client, callback_query):
    parts = callback_query.data.split("_")
    payload = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current: list[str] = fs.get("specials", []) or []

    # Resolve the target label (prefer index form; fall back to raw
    # label for legacy callbacks so upgrade-in-flight pickers keep
    # working).
    target: str | None = None
    if payload.startswith("i") and payload[1:].isdigit():
        idx = int(payload[1:])
        if 0 <= idx < len(_SPECIALS_OPTIONS):
            target = _SPECIALS_OPTIONS[idx]
    if target is None:
        target = payload if payload in _SPECIALS_OPTIONS else None
    if target is None:
        await callback_query.answer("Unknown special.", show_alert=True)
        return

    if target in current:
        current.remove(target)
    else:
        # Per-source dedup: only one SOURCE label at a time.
        if target in _SOURCE_LABELS:
            current = [s for s in current if s not in _SOURCE_LABELS]
        current.append(target)

    fs["specials"] = current
    fs["specials_locked"] = False

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _specials_prompt(len(current)),
            reply_markup=_build_specials_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^clear_spc_") & auth_filter)
async def handle_clear_specials(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    msg_id = int(callback_query.data.split("_")[2])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    file_sessions[msg_id]["specials"] = []

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


@Client.on_callback_query(filters.regex(r"^lock_spc_") & auth_filter)
async def handle_lock_specials(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    fs["specials"] = []
    fs["specials_locked"] = True
    await callback_query.answer("🚫 Specials locked — auto-fill will skip this.", show_alert=False)
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)
