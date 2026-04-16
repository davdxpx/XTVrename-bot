# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""Mirror-Leech Pyrogram plugin.

Registers commands (`/ml`, `/mirror`, `/leech`) and every `ml_*`
callback query handler. Heavy logic lives in tools/mirror_leech/*;
this file is the wiring layer that knows about Pyrogram.

Callback-data grammar (see Phase D plan for the full table):
    ml_cfg                       → user config root
    ml_cfg_up_<provider>         → per-provider config screen
    ml_cfg_test_<provider>       → test connection
    ml_cfg_clr_<provider>        → clear stored credential
    ml_cfg_paste_<provider>      → prompt user to paste token
    ml_opt_single_<file_id>      → MyFiles single-file entry
    ml_opt_multi_<state_key>     → MyFiles multi-select entry
    ml_prov_<uploader>_<ctx_id>  → pick uploader for picker context
    ml_go_<ctx_id>               → start task(s)
    ml_cancel_<task_id>          → cancel running task
    ml_queue                     → user queue
    ml_admin                     → CEO admin screen
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from tools.mirror_leech import ContextStore
from tools.mirror_leech.Controller import (
    UnsupportedSourceError,
    pick_downloader,
)
from tools.mirror_leech.uploaders import available_uploaders
from utils.log import get_logger

logger = get_logger("plugins.mirror_leech_ui")


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="ml_cancel_picker")]]
    )


async def _feature_enabled() -> bool:
    from database import db

    toggles = await db.get_setting("feature_toggles", {}) if db else {}
    if isinstance(toggles, dict):
        return bool(toggles.get("mirror_leech", False))
    return False


@Client.on_message(filters.command(["ml", "mirror", "leech"]) & filters.private)
async def ml_command(client: Client, message: Message) -> None:
    """Entry-point for `/ml <url>` / `/mirror <url>` / `/leech <url>`."""
    if not await _feature_enabled():
        await message.reply_text(
            "🚧 **Mirror-Leech is not enabled on this bot yet.**\n\n"
            "An admin needs to flip `feature_toggles.mirror_leech` on from the "
            "`/admin → Mirror-Leech Config` panel."
        )
        return

    parts = (message.text or "").split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "Usage: `/ml <url>`\n\n"
            "Supported: direct HTTP(S), YouTube / social video (yt-dlp),\n"
            "Telegram file refs, and RSS feeds. "
            "Torrents / magnets are out of scope on this branch.",
        )
        return

    source = parts[1].strip()
    try:
        dl_cls = await pick_downloader(source)
    except UnsupportedSourceError as exc:
        await message.reply_text(str(exc))
        return

    # Stash picker state so the uploader-pick keyboard can reference it via
    # a short ctx_id (callback_data is limited to 64 bytes).
    cid = ContextStore.put(
        ContextStore.PickerContext(
            user_id=message.from_user.id,
            source=source,
            candidate_downloader=dl_cls.id,
            origin_chat_id=message.chat.id,
            origin_msg_id=message.id,
        )
    )

    # Render the uploader picker. Actual button rendering lives in
    # _render_uploader_picker (added in a follow-up commit); for now we
    # drop a placeholder so the command is wired end-to-end.
    await message.reply_text(
        f"📥 Using **{dl_cls.display_name}**.\n\n"
        f"Pick destinations (ctx `{cid}`) — uploader picker UI ships in a "
        "follow-up commit.",
        reply_markup=_cancel_kb(),
    )


@Client.on_callback_query(filters.regex(r"^ml_cancel_picker$"))
async def ml_cancel_picker(client: Client, callback_query: CallbackQuery) -> None:
    """Best-effort dismiss of an in-progress picker message."""
    try:
        await callback_query.message.edit_text("🚫 Mirror-Leech picker cancelled.")
    except Exception:
        pass
    await callback_query.answer()
