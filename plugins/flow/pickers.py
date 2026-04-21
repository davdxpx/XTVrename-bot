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

# --- Dedicated per-category option lists (PR B) -----------------------------
# Five new template placeholders landed in PR #369: {Source}, {HDR},
# {Edition}, {Release}, {Extras}. Each gets its own picker below so the
# confirm screen can expose them individually and template-gated. The
# legacy Specials picker + _SPECIALS_OPTIONS above stay in place as the
# "all of the above" aggregate for `{Specials}` templates; a future PR
# can retire it once users have migrated to the category-specific
# placeholders.
#
# Selection mode (matches utils/media/patterns.py detector multi flag):
#   Source  — single-select  (a release is one source)
#   HDR     — single-select  (a file is encoded in one HDR flavour)
#   Edition — multi-select   (Extended + IMAX Enhanced is a real combo)
#   Release — multi-select   (REMUX + PROPER can both apply)
#   Extras  — multi-select

_SOURCE_OPTIONS: list[str] = [
    "BluRay", "UHD BluRay", "BDRip", "BRRip",
    "WEB-DL", "WEBRip", "WEB",
    "AMZN WEB-DL", "NF WEB-DL", "DSNP WEB-DL", "HULU WEB-DL",
    "MAX WEB-DL", "HMAX WEB-DL", "ATVP WEB-DL", "PMTP WEB-DL",
    "HDTV", "DVDRip", "DVD", "VHS", "HDRip", "CAM", "TS",
]

_HDR_OPTIONS: list[str] = [
    "Dolby Vision", "DV P5", "DV P7", "DV P8",
    "HDR10+", "HDR10", "HDR",
    "HLG", "SDR",
]

_EDITION_OPTIONS: list[str] = [
    "Extended", "Extended Edition", "Extended Cut",
    "Director's Cut", "Final Cut", "Theatrical Cut",
    "Ultimate Edition", "Special Edition",
    "IMAX", "IMAX Enhanced",
    "Unrated", "Uncut", "Remastered",
]

_RELEASE_OPTIONS: list[str] = [
    "REMUX", "PROPER", "REPACK", "RERIP",
    "Criterion", "INTERNAL", "LIMITED",
]

_EXTRAS_OPTIONS: list[str] = [
    "DUAL", "Multi", "Dual Audio", "Multi Audio",
    "Dubbed", "MicDub", "LineDub", "Subbed",
    "HardSubs", "SoftSubs", "HardCoded", "DL",
]

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


# --- HDR picker (single-select) ---------------------------------------------
def _build_hdr_keyboard(msg_id: int, fs: dict) -> InlineKeyboardMarkup:
    current = fs.get("hdr", "")
    locked = bool(fs.get("hdr_locked"))
    page = _picker_page(fs, "hdr")
    items = [(str(i), label) for i, label in enumerate(_HDR_OPTIONS)]
    none_text = "🚫 None (locked)" if locked else ("✅ None" if not current else "None")
    extras = [
        [InlineKeyboardButton(none_text, callback_data=f"set_hdr_none_{msg_id}")],
        [InlineKeyboardButton("← Back", callback_data=f"back_confirm_{msg_id}")],
    ]
    current_key = (
        str(_HDR_OPTIONS.index(current)) if current in _HDR_OPTIONS else None
    )
    rows = paginate_kb(
        items=items,
        page=page,
        per_page=_PICKER_PER_PAGE,
        per_row=_PICKER_PER_ROW,
        selected={current_key} if current_key else set(),
        cb_template=lambda idx: f"set_hdr_i{idx}_{msg_id}",
        page_cb_template=lambda p: f"hdr_pg_{p}_{msg_id}",
        extra_rows=extras,
    )
    return InlineKeyboardMarkup(rows)


def _hdr_prompt() -> str:
    return (
        "🌈 **Select HDR:**\nA file is encoded in one HDR flavour — Dolby "
        "Vision, HDR10, HDR10+, HLG, or SDR. Pick **None** to lock auto-fill."
    )


@Client.on_callback_query(filters.regex(r"^ch_hdr_") & auth_filter)
async def handle_change_hdr(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "hdr", 0)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _hdr_prompt(),
            reply_markup=_build_hdr_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^hdr_pg_(\d+)_(\d+)$") & auth_filter)
async def handle_hdr_page(client, callback_query):
    m = re.match(r"^hdr_pg_(\d+)_(\d+)$", callback_query.data)
    if not m:
        return
    page, msg_id = int(m.group(1)), int(m.group(2))
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "hdr", page)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _hdr_prompt(),
            reply_markup=_build_hdr_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^set_hdr_") & auth_filter)
async def handle_set_hdr(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    parts = callback_query.data.split("_")
    payload = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    if payload == "none":
        fs["hdr"] = ""
        fs["hdr_locked"] = True
    elif payload.startswith("i") and payload[1:].isdigit():
        idx = int(payload[1:])
        if 0 <= idx < len(_HDR_OPTIONS):
            fs["hdr"] = _HDR_OPTIONS[idx]
            fs["hdr_locked"] = False
        else:
            await callback_query.answer("Unknown HDR option.", show_alert=True)
            return
    else:
        await callback_query.answer("Unknown HDR option.", show_alert=True)
        return

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


# --- Source picker (single-select, like Codec/Audio) ------------------------
def _build_source_keyboard(msg_id: int, fs: dict) -> InlineKeyboardMarkup:
    current = fs.get("source", "")
    locked = bool(fs.get("source_locked"))
    page = _picker_page(fs, "source")
    items = [(str(i), label) for i, label in enumerate(_SOURCE_OPTIONS)]
    none_text = "🚫 None (locked)" if locked else ("✅ None" if not current else "None")
    extras = [
        [InlineKeyboardButton(none_text, callback_data=f"set_src_none_{msg_id}")],
        [InlineKeyboardButton("← Back", callback_data=f"back_confirm_{msg_id}")],
    ]
    current_key = (
        str(_SOURCE_OPTIONS.index(current)) if current in _SOURCE_OPTIONS else None
    )
    rows = paginate_kb(
        items=items,
        page=page,
        per_page=_PICKER_PER_PAGE,
        per_row=_PICKER_PER_ROW,
        selected={current_key} if current_key else set(),
        cb_template=lambda idx: f"set_src_i{idx}_{msg_id}",
        page_cb_template=lambda p: f"src_pg_{p}_{msg_id}",
        extra_rows=extras,
    )
    return InlineKeyboardMarkup(rows)


def _source_prompt() -> str:
    return (
        "🎬 **Select Source:**\nPick the release source (BluRay, WEB-DL, …). "
        "Only one source applies to a release — picking another replaces the "
        "current one. Pick **None** to lock against auto-detect."
    )


@Client.on_callback_query(filters.regex(r"^ch_src_") & auth_filter)
async def handle_change_source(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "source", 0)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _source_prompt(),
            reply_markup=_build_source_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^src_pg_(\d+)_(\d+)$") & auth_filter)
async def handle_source_page(client, callback_query):
    m = re.match(r"^src_pg_(\d+)_(\d+)$", callback_query.data)
    if not m:
        return
    page, msg_id = int(m.group(1)), int(m.group(2))
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "source", page)
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _source_prompt(),
            reply_markup=_build_source_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^set_src_") & auth_filter)
async def handle_set_source(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    parts = callback_query.data.split("_")
    payload = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    if payload == "none":
        fs["source"] = ""
        fs["source_locked"] = True
    elif payload.startswith("i") and payload[1:].isdigit():
        idx = int(payload[1:])
        if 0 <= idx < len(_SOURCE_OPTIONS):
            fs["source"] = _SOURCE_OPTIONS[idx]
            fs["source_locked"] = False
        else:
            await callback_query.answer("Unknown source option.", show_alert=True)
            return
    else:
        await callback_query.answer("Unknown source option.", show_alert=True)
        return

    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


# --- Edition picker (multi-select) ------------------------------------------
def _build_edition_keyboard(msg_id: int, fs: dict) -> InlineKeyboardMarkup:
    current: list[str] = fs.get("edition", []) or []
    locked = bool(fs.get("edition_locked"))
    page = _picker_page(fs, "edition")
    items = [(str(i), label) for i, label in enumerate(_EDITION_OPTIONS)]
    selected_keys = {
        str(i) for i, label in enumerate(_EDITION_OPTIONS) if label in current
    }
    lock_label = "🚫 None (locked)" if locked else "🚫 None (lock)"
    extras = [
        [
            InlineKeyboardButton("❌ Clear All", callback_data=f"clr_edi_{msg_id}"),
            InlineKeyboardButton(lock_label, callback_data=f"lok_edi_{msg_id}"),
        ],
        [InlineKeyboardButton("✅ Done", callback_data=f"back_confirm_{msg_id}")],
    ]
    rows = paginate_kb(
        items=items,
        page=page,
        per_page=_PICKER_PER_PAGE,
        per_row=_PICKER_PER_ROW,
        selected=selected_keys,
        cb_template=lambda idx: f"tgl_edi_i{idx}_{msg_id}",
        page_cb_template=lambda p: f"edi_pg_{p}_{msg_id}",
        extra_rows=extras,
    )
    return InlineKeyboardMarkup(rows)


def _edition_prompt(selected_count: int) -> str:
    hint = f"\n**{selected_count}** currently selected." if selected_count else ""
    return (
        "🎭 **Select Edition:**\nToggle edition tags (multiple allowed — "
        "Extended + IMAX Enhanced is a real combo)." + hint
    )


@Client.on_callback_query(filters.regex(r"^ch_edi_") & auth_filter)
async def handle_change_edition(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "edition", 0)
    selected = fs.get("edition", []) or []
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _edition_prompt(len(selected)),
            reply_markup=_build_edition_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^edi_pg_(\d+)_(\d+)$") & auth_filter)
async def handle_edition_page(client, callback_query):
    m = re.match(r"^edi_pg_(\d+)_(\d+)$", callback_query.data)
    if not m:
        return
    page, msg_id = int(m.group(1)), int(m.group(2))
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "edition", page)
    selected = fs.get("edition", []) or []
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _edition_prompt(len(selected)),
            reply_markup=_build_edition_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^tgl_edi_") & auth_filter)
async def handle_toggle_edition(client, callback_query):
    parts = callback_query.data.split("_")
    payload = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current: list[str] = fs.get("edition", []) or []

    target: str | None = None
    if payload.startswith("i") and payload[1:].isdigit():
        idx = int(payload[1:])
        if 0 <= idx < len(_EDITION_OPTIONS):
            target = _EDITION_OPTIONS[idx]
    if target is None:
        await callback_query.answer("Unknown edition option.", show_alert=True)
        return

    if target in current:
        current.remove(target)
    else:
        current.append(target)

    fs["edition"] = current
    fs["edition_locked"] = False

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _edition_prompt(len(current)),
            reply_markup=_build_edition_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^clr_edi_") & auth_filter)
async def handle_clear_edition(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    file_sessions[msg_id]["edition"] = []
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


@Client.on_callback_query(filters.regex(r"^lok_edi_") & auth_filter)
async def handle_lock_edition(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    fs["edition"] = []
    fs["edition_locked"] = True
    await callback_query.answer("🚫 Edition locked — auto-fill will skip it.", show_alert=False)
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


# --- Release picker (multi-select) ------------------------------------------
def _build_release_keyboard(msg_id: int, fs: dict) -> InlineKeyboardMarkup:
    current: list[str] = fs.get("release", []) or []
    locked = bool(fs.get("release_locked"))
    page = _picker_page(fs, "release")
    items = [(str(i), label) for i, label in enumerate(_RELEASE_OPTIONS)]
    selected_keys = {
        str(i) for i, label in enumerate(_RELEASE_OPTIONS) if label in current
    }
    lock_label = "🚫 None (locked)" if locked else "🚫 None (lock)"
    extras = [
        [
            InlineKeyboardButton("❌ Clear All", callback_data=f"clr_rel_{msg_id}"),
            InlineKeyboardButton(lock_label, callback_data=f"lok_rel_{msg_id}"),
        ],
        [InlineKeyboardButton("✅ Done", callback_data=f"back_confirm_{msg_id}")],
    ]
    rows = paginate_kb(
        items=items,
        page=page,
        per_page=_PICKER_PER_PAGE,
        per_row=_PICKER_PER_ROW,
        selected=selected_keys,
        cb_template=lambda idx: f"tgl_rel_i{idx}_{msg_id}",
        page_cb_template=lambda p: f"rel_pg_{p}_{msg_id}",
        extra_rows=extras,
    )
    return InlineKeyboardMarkup(rows)


def _release_prompt(selected_count: int) -> str:
    hint = f"\n**{selected_count}** currently selected." if selected_count else ""
    return (
        "📦 **Select Release tags:**\nToggle release modifiers (REMUX, "
        "PROPER, REPACK, etc.). Multiple allowed." + hint
    )


@Client.on_callback_query(filters.regex(r"^ch_rel_") & auth_filter)
async def handle_change_release(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "release", 0)
    selected = fs.get("release", []) or []
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _release_prompt(len(selected)),
            reply_markup=_build_release_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^rel_pg_(\d+)_(\d+)$") & auth_filter)
async def handle_release_page(client, callback_query):
    m = re.match(r"^rel_pg_(\d+)_(\d+)$", callback_query.data)
    if not m:
        return
    page, msg_id = int(m.group(1)), int(m.group(2))
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "release", page)
    selected = fs.get("release", []) or []
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _release_prompt(len(selected)),
            reply_markup=_build_release_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^tgl_rel_") & auth_filter)
async def handle_toggle_release(client, callback_query):
    parts = callback_query.data.split("_")
    payload = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current: list[str] = fs.get("release", []) or []

    target: str | None = None
    if payload.startswith("i") and payload[1:].isdigit():
        idx = int(payload[1:])
        if 0 <= idx < len(_RELEASE_OPTIONS):
            target = _RELEASE_OPTIONS[idx]
    if target is None:
        await callback_query.answer("Unknown release option.", show_alert=True)
        return

    if target in current:
        current.remove(target)
    else:
        current.append(target)

    fs["release"] = current
    fs["release_locked"] = False

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _release_prompt(len(current)),
            reply_markup=_build_release_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^clr_rel_") & auth_filter)
async def handle_clear_release(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    file_sessions[msg_id]["release"] = []
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


@Client.on_callback_query(filters.regex(r"^lok_rel_") & auth_filter)
async def handle_lock_release(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    fs["release"] = []
    fs["release_locked"] = True
    await callback_query.answer("🚫 Release locked — auto-fill will skip it.", show_alert=False)
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


# --- Extras picker (multi-select) -------------------------------------------
def _build_extras_keyboard(msg_id: int, fs: dict) -> InlineKeyboardMarkup:
    current: list[str] = fs.get("extras", []) or []
    locked = bool(fs.get("extras_locked"))
    page = _picker_page(fs, "extras")
    items = [(str(i), label) for i, label in enumerate(_EXTRAS_OPTIONS)]
    selected_keys = {
        str(i) for i, label in enumerate(_EXTRAS_OPTIONS) if label in current
    }
    lock_label = "🚫 None (locked)" if locked else "🚫 None (lock)"
    extras_rows = [
        [
            InlineKeyboardButton("❌ Clear All", callback_data=f"clr_ext_{msg_id}"),
            InlineKeyboardButton(lock_label, callback_data=f"lok_ext_{msg_id}"),
        ],
        [InlineKeyboardButton("✅ Done", callback_data=f"back_confirm_{msg_id}")],
    ]
    rows = paginate_kb(
        items=items,
        page=page,
        per_page=_PICKER_PER_PAGE,
        per_row=_PICKER_PER_ROW,
        selected=selected_keys,
        cb_template=lambda idx: f"tgl_ext_i{idx}_{msg_id}",
        page_cb_template=lambda p: f"ext_pg_{p}_{msg_id}",
        extra_rows=extras_rows,
    )
    return InlineKeyboardMarkup(rows)


def _extras_prompt(selected_count: int) -> str:
    hint = f"\n**{selected_count}** currently selected." if selected_count else ""
    return (
        "➕ **Select Extras:**\nToggle extras (Dual Audio, Dubbed, HardSubs, "
        "…). Multiple allowed." + hint
    )


@Client.on_callback_query(filters.regex(r"^ch_ext_") & auth_filter)
async def handle_change_extras(client, callback_query):
    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "extras", 0)
    selected = fs.get("extras", []) or []
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _extras_prompt(len(selected)),
            reply_markup=_build_extras_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^ext_pg_(\d+)_(\d+)$") & auth_filter)
async def handle_extras_page(client, callback_query):
    m = re.match(r"^ext_pg_(\d+)_(\d+)$", callback_query.data)
    if not m:
        return
    page, msg_id = int(m.group(1)), int(m.group(2))
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    fs = file_sessions[msg_id]
    _set_picker_page(fs, "extras", page)
    selected = fs.get("extras", []) or []
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _extras_prompt(len(selected)),
            reply_markup=_build_extras_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^tgl_ext_") & auth_filter)
async def handle_toggle_extras(client, callback_query):
    parts = callback_query.data.split("_")
    payload = parts[2]
    msg_id = int(parts[3])

    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    current: list[str] = fs.get("extras", []) or []

    target: str | None = None
    if payload.startswith("i") and payload[1:].isdigit():
        idx = int(payload[1:])
        if 0 <= idx < len(_EXTRAS_OPTIONS):
            target = _EXTRAS_OPTIONS[idx]
    if target is None:
        await callback_query.answer("Unknown extras option.", show_alert=True)
        return

    if target in current:
        current.remove(target)
    else:
        current.append(target)

    fs["extras"] = current
    fs["extras_locked"] = False

    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            _extras_prompt(len(current)),
            reply_markup=_build_extras_keyboard(msg_id, fs),
        )


@Client.on_callback_query(filters.regex(r"^clr_ext_") & auth_filter)
async def handle_clear_extras(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    file_sessions[msg_id]["extras"] = []
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)


@Client.on_callback_query(filters.regex(r"^lok_ext_") & auth_filter)
async def handle_lock_extras(client, callback_query):
    from plugins.flow.confirmation_screen import update_confirmation_message

    msg_id = int(callback_query.data.split("_")[2])
    if msg_id not in file_sessions:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    fs = file_sessions[msg_id]
    fs["extras"] = []
    fs["extras_locked"] = True
    await callback_query.answer("🚫 Extras locked — auto-fill will skip it.", show_alert=False)
    await update_confirmation_message(client, msg_id, callback_query.from_user.id)
