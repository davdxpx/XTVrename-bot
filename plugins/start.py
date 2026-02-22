from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config

def is_authorized(user_id):
    return user_id == Config.CEO_ID or user_id in Config.FRANCHISEE_IDS

auth_filter = filters.create(lambda _, __, update: is_authorized(update.from_user.id if update.from_user else 0))

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
