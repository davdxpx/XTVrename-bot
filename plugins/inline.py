# --- Imports ---
import math

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedDocument,
    InlineQueryResultCachedVideo,
    InputTextMessageContent,
)

from config import Config
from database import db
from utils.log import get_logger

logger = get_logger("plugins.inline")

@Client.on_inline_query()
async def inline_search(client: Client, inline_query: InlineQuery):
    query = inline_query.query.strip()
    user_id = inline_query.from_user.id

    # If empty query, don't show results or maybe show a prompt
    if not query:
        await inline_query.answer([], cache_time=0)
        return

    # Check access based on PUBLIC_MODE
    if not Config.PUBLIC_MODE and user_id != Config.CEO_ID and user_id not in Config.ADMIN_IDS:
        await inline_query.answer([
            InlineQueryResultArticle(
                title="Access Denied",
                description="You are not authorized to use this feature.",
                input_message_content=InputTextMessageContent("Access Denied")
            )
        ], cache_time=0)
        return

    # Build DB filter
    filter_query = {"file_name": {"$regex": query, "$options": "i"}}
    if Config.PUBLIC_MODE:
        filter_query["user_id"] = user_id

    # Limit search results to 50 (Telegram inline limit)
    cursor = db.files.find(filter_query).limit(50)
    files = await cursor.to_list(length=50)

    results = []

    # We will generate Deep Links for files
    bot_me = await client.get_me()
    bot_username = bot_me.username

    for f in files:
        file_id_str = str(f["_id"])
        name = f.get("file_name", "Unknown File")
        status = f.get("status", "temporary")
        status_emoji = "📌" if status == "permanent" else "⏳"

        expires_str = ""
        if status == "temporary" and f.get("expires_at"):
            expires_str = f" | Expires: {f['expires_at'].strftime('%Y-%m-%d')}"

        description = f"{status_emoji} {status.capitalize()}{expires_str}"

        deep_link = f"https://t.me/{bot_username}?start=file_{file_id_str}"

        # We can either send the deep link text, or a cached document if we know it.
        # But inline query limits require standard file_ids if we want to send direct media.
        # Deep links are safer and don't require the file to be recently cached by Telegram.

        results.append(
            InlineQueryResultArticle(
                title=name,
                description=description,
                input_message_content=InputTextMessageContent(
                    f"📄 **{name}**\n\nClick the link below to get this file:"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Get File", url=deep_link)]
                ])
            )
        )

    if not results:
        results.append(
            InlineQueryResultArticle(
                title="No results found",
                description=f"No files matching '{query}'",
                input_message_content=InputTextMessageContent(f"No results found for: {query}")
            )
        )

    await inline_query.answer(results, cache_time=5)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
