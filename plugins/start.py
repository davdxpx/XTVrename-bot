from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.auth import auth_filter
from config import Config
from utils.log import get_logger

logger = get_logger("plugins.start")

@Client.on_message(filters.command(["start", "new"]))
async def start_command(client, message):
    # Log the attempt
    user_id = message.from_user.id
    logger.info(f"/start received from user {user_id}")

    # Check Auth manually if filter is failing or for better logging
    if not (user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS):
        logger.warning(f"Unauthorized access attempt by {user_id}")
        return # Ignore

    await message.reply_text(
        "**XTV Rename Bot**\n\n"
        "Welcome to the official XTV file renaming tool.\n"
        "This bot provides professional renaming and metadata management.\n\n"
        "Click below to start.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Start Renaming", callback_data="start_renaming")]
        ])
    )

@Client.on_message(filters.command("end") & auth_filter)
async def end_command(client, message):
    await message.reply_text("Session ended. Use /start or /new to begin again.")
