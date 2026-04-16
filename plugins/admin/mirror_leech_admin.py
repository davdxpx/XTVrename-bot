# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""Admin-panel Mirror-Leech configuration.

Top-level ml_admin screen shows:
  - master on/off toggle (feature_toggles.mirror_leech)
  - SECRETS_KEY status
  - list of downloaders / uploaders marked available/unavailable on the host

Currently this screen is read-only beyond the master toggle; per-provider
enable/disable + concurrency limits ship in a follow-up commit so this
commit stays reviewable.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from database import db
from plugins.admin.core import is_admin
from tools.mirror_leech import Secrets
from tools.mirror_leech.downloaders import all_downloaders
from tools.mirror_leech.uploaders import all_uploaders
from utils.log import get_logger

logger = get_logger("plugins.admin.mirror_leech")


async def _feature_enabled() -> bool:
    toggles = await db.get_setting("feature_toggles", {}) or {}
    return bool(toggles.get("mirror_leech", False))


async def _render(callback_query: CallbackQuery) -> None:
    enabled = await _feature_enabled()
    secrets_ok = Secrets.is_available()

    lines = [
        "☁️ **Mirror-Leech Config**",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"**Feature toggle:** {'✅ enabled' if enabled else '❌ disabled'}",
        f"**SECRETS_KEY:** {'✅ set' if secrets_ok else '❌ missing — set it before enabling the feature'}",
        "",
        "**Downloaders**",
    ]
    for cls in all_downloaders():
        avail = cls.available() if hasattr(cls, "available") else True
        marker = "✅" if avail else "🚫"
        lines.append(f"{marker} `{cls.id}` — {cls.display_name}")
    lines.append("")
    lines.append("**Uploaders**")
    for cls in all_uploaders():
        marker = "✅" if cls.available() else "🚫"
        binary_hint = f" (needs `{cls.binary_required}`)" if cls.binary_required and not cls.available() else ""
        pkg_hint = (
            f" (needs Python `{cls.python_import_required}`)"
            if cls.python_import_required and not cls.available()
            else ""
        )
        lines.append(f"{marker} `{cls.id}` — {cls.display_name}{binary_hint}{pkg_hint}")

    toggle_label = (
        "🚫 Disable Mirror-Leech" if enabled else "✅ Enable Mirror-Leech"
    )
    if not secrets_ok and not enabled:
        toggle_label = "🔒 Set SECRETS_KEY first"

    rows = [
        [InlineKeyboardButton(toggle_label, callback_data="ml_admin_toggle")],
        [InlineKeyboardButton("↻ Refresh", callback_data="ml_admin")],
        [InlineKeyboardButton("← Back", callback_data="admin_back")],
    ]
    try:
        await callback_query.message.edit_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows)
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^ml_admin$"))
async def ml_admin_callback(client: Client, callback_query: CallbackQuery) -> None:
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("Not authorised.", show_alert=True)
        return
    await _render(callback_query)
    await callback_query.answer()


@Client.on_callback_query(filters.regex(r"^ml_admin_toggle$"))
async def ml_admin_toggle(client: Client, callback_query: CallbackQuery) -> None:
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("Not authorised.", show_alert=True)
        return

    current = await _feature_enabled()
    if not current and not Secrets.is_available():
        await callback_query.answer(
            "Set SECRETS_KEY on the host before enabling the feature.",
            show_alert=True,
        )
        return

    toggles = await db.get_setting("feature_toggles", {}) or {}
    if not isinstance(toggles, dict):
        toggles = {}
    toggles["mirror_leech"] = not current
    await db.update_setting("feature_toggles", toggles)
    await callback_query.answer(
        "Enabled." if not current else "Disabled."
    )
    await _render(callback_query)
