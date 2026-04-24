# --- Imports ---
from pyrogram import Client, filters

from utils.telegram.log import get_logger

logger = get_logger("plugins.debug")

from pyrogram import ContinuePropagation


@Client.on_message(filters.all, group=-1)

# --- Handlers ---
async def debug_all_messages(client, message):
    # This handler runs for every inbound message (group=-1). A crash
    # here wouldn't kill the bot, but it would stop `ContinuePropagation`
    # from firing and silently eat events — so every step is defensive.
    try:
        sender_id = (
            message.from_user.id
            if message.from_user
            else (message.sender_chat.id if getattr(message, "sender_chat", None) else "Unknown")
        )
        preview = message.text or message.caption or "[Media]"
        logger.debug(f"Received message from {sender_id}: {preview}")
    except Exception as e:
        logger.debug(f"debug handler error: {e}")
    raise ContinuePropagation

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
