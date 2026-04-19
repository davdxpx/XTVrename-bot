"""Central TMDb availability gate.

Every TMDb-dependent feature routes through here so a missing
`TMDB_API_KEY` degrades gracefully into a friendly "this feature needs
TMDb, but everything else still works" message instead of silently
failing or hammering the API with 401s.
"""

from __future__ import annotations

import contextlib
from typing import Any

from config import Config
from utils.telegram.log import get_logger

logger = get_logger("utils.tmdb_gate")

TMDB_DOCS_URL = "https://www.themoviedb.org/settings/api"


def is_tmdb_available() -> bool:
    """True iff a non-blank TMDB_API_KEY is configured."""
    key = Config.TMDB_API_KEY
    return bool(key and key.strip())


def tmdb_required_message(feature: str = "This feature") -> str:
    return (
        f"🔒 **{feature} needs TMDb**\n\n"
        "The bot owner hasn't configured a TMDb API key, so title matching, "
        "posters, and auto-routing are off.\n\n"
        "Ask your admin to set `TMDB_API_KEY` — it's free at TMDb.\n\n"
        "_Everything else still works: file conversion, MyFiles, YouTube, "
        "general-mode renaming, and the Tools menu._"
    )


def tmdb_docs_keyboard():
    # Lazy import so callers without pyrogram (tests) don't pull it in.
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📖 Get a TMDb key", url=TMDB_DOCS_URL)]]
    )


async def ensure_tmdb(
    client: Any,
    target: Any,
    feature: str = "This feature",
) -> bool:
    """Send a friendly block message if TMDb is unavailable.

    Returns True when the caller may proceed, False when the caller should
    short-circuit. `target` may be either a Message (command handler) or a
    CallbackQuery (inline-button handler).
    """
    if is_tmdb_available():
        return True

    from pyrogram.types import CallbackQuery  # lazy for test-env friendliness

    text = tmdb_required_message(feature)
    markup = tmdb_docs_keyboard()

    if isinstance(target, CallbackQuery):
        with contextlib.suppress(Exception):
            await target.answer()
        try:
            await target.message.reply_text(text, reply_markup=markup)
        except Exception:
            logger.warning("ensure_tmdb: failed to reply to CallbackQuery")
    else:
        try:
            await target.reply_text(text, reply_markup=markup)
        except Exception:
            logger.warning("ensure_tmdb: failed to reply to Message")
    return False
