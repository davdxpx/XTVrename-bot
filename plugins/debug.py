from pyrogram import Client, filters
from utils.log import get_logger

logger = get_logger("plugins.debug")


@Client.on_message(filters.all, group=-1)
async def debug_all_messages(client, message):
    sender_id = (
        message.from_user.id
        if message.from_user
        else (message.sender_chat.id if message.sender_chat else "Unknown")
    )
    logger.debug(
        f"Received message from {sender_id}: {message.text or message.caption or '[Media]'}"
    )


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
