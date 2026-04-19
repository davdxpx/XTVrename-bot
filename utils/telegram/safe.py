"""FloodWait / MessageNotModified safe wrappers for Telegram API calls.

Across plugins we call `message.edit_text`, `client.edit_message_text` and
`client.send_message` in dozens of places. Two failure modes recur:

  * `FloodWait` — Telegram rate limiting. Every call needs `await asyncio.sleep(e.value)`
    followed by a retry, or the operation is silently lost.
  * `MessageNotModified` — editing a message to the same content. Harmless,
    but uncaught it aborts the surrounding handler.

These wrappers normalise that boilerplate so callers can focus on intent.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from pyrogram.errors import FloodWait, MessageNotModified

from utils.telegram.log import get_logger

logger = get_logger("utils.tg_safe")

_MAX_FLOODWAIT_RETRIES = 2
# Cap waiting when Telegram hands back an absurd value (e.g. banned chats) —
# we'd rather fail fast than freeze a user-facing flow for minutes.
_MAX_FLOODWAIT_SECONDS = 60


async def safe_edit(message, text: str, **kwargs) -> Optional[Any]:
    """Edit a message. Handles FloodWait (sleep + retry) and swallows
    MessageNotModified. Returns the edited Message on success, None if
    the edit was a no-op or failed unrecoverably.
    """
    for attempt in range(_MAX_FLOODWAIT_RETRIES + 1):
        try:
            return await message.edit_text(text, **kwargs)
        except MessageNotModified:
            return None
        except FloodWait as e:
            wait = min(getattr(e, "value", 1) + 1, _MAX_FLOODWAIT_SECONDS)
            logger.warning(
                f"safe_edit FloodWait {wait}s (attempt {attempt + 1}/{_MAX_FLOODWAIT_RETRIES + 1})"
            )
            if attempt >= _MAX_FLOODWAIT_RETRIES:
                return None
            await asyncio.sleep(wait)
        except Exception as e:
            logger.warning(f"safe_edit unexpected error: {e}")
            return None
    return None


async def safe_edit_message_text(client, chat_id, message_id, text: str, **kwargs):
    """Client-level edit variant (when you only have chat_id + message_id)."""
    for attempt in range(_MAX_FLOODWAIT_RETRIES + 1):
        try:
            return await client.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text, **kwargs
            )
        except MessageNotModified:
            return None
        except FloodWait as e:
            wait = min(getattr(e, "value", 1) + 1, _MAX_FLOODWAIT_SECONDS)
            logger.warning(f"safe_edit_message_text FloodWait {wait}s")
            if attempt >= _MAX_FLOODWAIT_RETRIES:
                return None
            await asyncio.sleep(wait)
        except Exception as e:
            logger.warning(f"safe_edit_message_text unexpected error: {e}")
            return None
    return None


async def safe_send(client, chat_id, text: str, **kwargs):
    """Send a message with FloodWait handling."""
    for attempt in range(_MAX_FLOODWAIT_RETRIES + 1):
        try:
            return await client.send_message(chat_id=chat_id, text=text, **kwargs)
        except FloodWait as e:
            wait = min(getattr(e, "value", 1) + 1, _MAX_FLOODWAIT_SECONDS)
            logger.warning(f"safe_send FloodWait {wait}s")
            if attempt >= _MAX_FLOODWAIT_RETRIES:
                return None
            await asyncio.sleep(wait)
        except Exception as e:
            logger.warning(f"safe_send unexpected error: {e}")
            return None
    return None


async def safe_answer(callback_query, text: str = "", show_alert: bool = False) -> bool:
    """Answer a callback query with graceful failure. Returns True on success."""
    try:
        await callback_query.answer(text, show_alert=show_alert)
        return True
    except FloodWait as e:
        wait = min(getattr(e, "value", 1) + 1, _MAX_FLOODWAIT_SECONDS)
        await asyncio.sleep(wait)
        try:
            await callback_query.answer(text, show_alert=show_alert)
            return True
        except Exception:
            return False
    except Exception as e:
        logger.debug(f"safe_answer error (likely stale query): {e}")
        return False


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
