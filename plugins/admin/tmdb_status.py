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

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from plugins.admin.core import is_admin
from utils.tmdb_gate import TMDB_DOCS_URL, is_tmdb_available


def _status_text() -> str:
    status_line = "✅ Configured" if is_tmdb_available() else "❌ Missing"
    return (
        "🎬 **TMDb Status**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**API key:** {status_line}\n\n"
        "TMDb is **optional**. When a key is configured, the bot unlocks:\n"
        "• Auto-match of uploaded files to a Movie / Series entry\n"
        "• Poster artwork on MyFiles and rename previews\n"
        "• Automatic routing between Movie / Series dumb channels\n"
        "• Manual search for titles by keyword\n\n"
        "When the key is missing, those features show a friendly\n"
        "🔒 badge and explain how to enable them. The rest of the bot\n"
        "(General Mode, File Converter, MyFiles, YouTube, Tools) keeps\n"
        "working unchanged.\n\n"
        "Set `TMDB_API_KEY` in the bot's env/config to enable."
    )


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📖 Get a free TMDb key", url=TMDB_DOCS_URL)],
            [InlineKeyboardButton("↻ Refresh", callback_data="admin_tmdb_status")],
            [InlineKeyboardButton("← Back", callback_data="admin_main")],
        ]
    )


@Client.on_callback_query(filters.regex(r"^admin_tmdb_status$"))
async def tmdb_status_callback(client, callback_query: CallbackQuery):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("Not authorised.", show_alert=True)
        return
    try:
        await callback_query.message.edit_text(_status_text(), reply_markup=_keyboard())
    except MessageNotModified:
        pass
