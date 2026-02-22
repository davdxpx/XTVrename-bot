from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.auth import auth_filter
from config import Config

@Client.on_message(filters.command(["start", "new"]) & auth_filter)
async def start_command(client, message):
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

# Only CEO and Franchisees are allowed. Others are ignored by auth_filter.
