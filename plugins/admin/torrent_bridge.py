# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""Bridge from main's new admin package to torrent-edition's legacy panel.

The torrent subsystem's admin UI was developed inside the pre-refactor
plugins/admin.py monolith. That file now lives as plugins/admin_legacy.py
so it can coexist with main's plugins/admin/ package without Python
complaining about a file-vs-package name clash.

This bridge handles the `admin_torrent_bridge` callback by rendering the
legacy panel's entry screen inside the current /admin message, so users
see one continuous admin flow instead of having to remember a second
command.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import CallbackQuery

from config import Config
from database import db
from plugins.admin.core import is_admin


@Client.on_callback_query(filters.regex(r"^admin_torrent_bridge$"))
async def admin_torrent_bridge(client: Client, callback_query: CallbackQuery) -> None:
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("Not authorised.", show_alert=True)
        return

    # Pull the legacy menu builder + panel copy from admin_legacy.py.
    try:
        from plugins.admin_legacy import get_admin_main_menu as legacy_menu
    except Exception as exc:
        await callback_query.answer(
            f"Torrent admin unavailable: {exc}", show_alert=True
        )
        return

    pro_session = await db.get_pro_session()
    myfiles_enabled = await db.get_setting("myfiles_enabled", default=False)
    markup = legacy_menu(pro_session, Config.PUBLIC_MODE, myfiles_enabled)

    body = (
        "🧲 **Torrent Admin**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "You're in the legacy admin panel — it hosts the torrent-specific "
        "settings (feature toggle, per-plan size limits, etc.) that live "
        "outside main's new System Health page.\n\n"
        "_Use the keyboard below; “← Back to Admin Panel” returns you to "
        "the new admin root._"
    )

    try:
        await callback_query.message.edit_text(body, reply_markup=markup)
    except MessageNotModified:
        pass
    try:
        await callback_query.answer()
    except Exception:
        pass
