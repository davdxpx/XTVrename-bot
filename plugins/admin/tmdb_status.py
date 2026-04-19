# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""Admin-panel read-only TMDb status screen.

Shows whether TMDB_API_KEY is configured, points the operator at the
TMDb docs when it's missing, and lists which features light up as soon
as a key is set.
"""

from __future__ import annotations

import contextlib

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from plugins.admin.core import is_admin
from utils.tmdb.gate import TMDB_DOCS_URL, is_tmdb_available


def _status_text_configured() -> str:
    """Compact view shown once TMDB_API_KEY is set — just the perks in a
    blockquote, no tutorial."""
    return (
        "🎬 **TMDb Status**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**API key:** ✅ Configured\n\n"
        "> 🎯 Auto-match of uploads to Movie / Series\n"
        "> 🖼 Posters on MyFiles & rename previews\n"
        "> 📺 Auto-route between Movie / Series dumb channels\n"
        "> 🔍 Manual title search by keyword"
    )


def _status_text_missing() -> str:
    """Verbose onboarding copy shown when TMDB_API_KEY is unset."""
    return (
        "🎬 **TMDb Status**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "**API key:** ❌ Missing\n\n"
        "TMDb is **optional**. When a key is configured the bot unlocks:\n"
        "• Auto-match of uploaded files to a Movie / Series entry\n"
        "• Poster artwork on MyFiles and rename previews\n"
        "• Automatic routing between Movie / Series dumb channels\n"
        "• Manual search for titles by keyword\n\n"
        "Without a key those features show a 🔒 badge; everything else\n"
        "(General Mode, File Converter, MyFiles, YouTube, Tools) keeps\n"
        "working unchanged.\n\n"
        "Grab a free key, then set `TMDB_API_KEY` in the bot's env and\n"
        "restart."
    )


def _keyboard(configured: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not configured:
        rows.append(
            [InlineKeyboardButton("📖 Get a free TMDb key", url=TMDB_DOCS_URL)]
        )
    rows.append(
        [InlineKeyboardButton("↻ Refresh", callback_data="admin_tmdb_status")]
    )
    rows.append(
        [InlineKeyboardButton("← Back", callback_data="admin_system_health")]
    )
    return InlineKeyboardMarkup(rows)


@Client.on_callback_query(filters.regex(r"^admin_tmdb_status$"))
async def tmdb_status_callback(client, callback_query: CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("Not authorised.", show_alert=True)
        return
    configured = is_tmdb_available()
    text = _status_text_configured() if configured else _status_text_missing()
    with contextlib.suppress(MessageNotModified):
        await callback_query.message.edit_text(
            text, reply_markup=_keyboard(configured)
        )
    with contextlib.suppress(Exception):
        await callback_query.answer()
