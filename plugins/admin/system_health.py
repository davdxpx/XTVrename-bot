# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""System Health & Statuses submenu.

Groups the three operator-facing status pages (DB Schema Health, TMDb
Status, Mirror-Leech Config) under a single admin-panel entry so the
main menu stays compact. The submenu itself is just a three-row picker;
each row routes to its existing callback.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from plugins.admin.core import is_admin


_SUBMENU_ID = "admin_system_health"


def _submenu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🩺 DB Schema Health", callback_data="admin_db_health")],
            [InlineKeyboardButton("🎬 TMDb Status", callback_data="admin_tmdb_status")],
            [InlineKeyboardButton("☁️ Mirror-Leech Config", callback_data="ml_admin")],
            [InlineKeyboardButton("← Back to Admin Panel", callback_data="admin_main")],
        ]
    )


@Client.on_callback_query(filters.regex(r"^admin_system_health$"))
async def system_health_callback(client, callback_query: CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("Not authorised.", show_alert=True)
        return
    try:
        await callback_query.message.edit_text(
            "🩺 **System Health & Statuses**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Operator panels for schema migration state, TMDb availability, "
            "and the Mirror-Leech subsystem.",
            reply_markup=_submenu_keyboard(),
        )
    except MessageNotModified:
        pass
    try:
        await callback_query.answer()
    except Exception:
        pass
