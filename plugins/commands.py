from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from utils.log import get_logger

logger = get_logger("plugins.commands")

@Client.on_message(filters.command(["start", "new"]) & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id
    logger.info(f"CMD received: {message.text} from {user_id}")

    if not (user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS):
        logger.warning(f"Unauthorized access by {user_id}")
        return

    await message.reply_text(
        "**XTV Rename Bot**\n\n"
        "Welcome to the official XTV file renaming tool.\n"
        "This bot provides professional renaming and metadata management.\n\n"
        "Click below to start.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Start Renaming", callback_data="start_renaming")]
        ])
    )

@Client.on_message(filters.command("end") & filters.private)
async def end_command(client, message):
    user_id = message.from_user.id
    logger.info(f"CMD received: {message.text} from {user_id}")
    await message.reply_text("Session ended. Use /start or /new to begin again.")
