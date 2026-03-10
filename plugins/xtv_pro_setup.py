import asyncio
import os
import random
import string
from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid,
    PhoneNumberInvalid, ApiIdInvalid
)
from database import db
from config import Config
from utils.log import get_logger

logger = get_logger("plugins.xtv_pro_setup")
pro_setup_sessions = {}

def get_pro_session_data(user_id):
    if user_id not in pro_setup_sessions:
        pro_setup_sessions[user_id] = {}
    return pro_setup_sessions[user_id]

@Client.on_callback_query(filters.regex(r"^pro_setup_menu$"))
async def pro_menu(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id != Config.CEO_ID:
        return await callback_query.answer("Not authorized.", show_alert=True)

    # Clear any pending setup state if the user clicked cancel/back to reach this menu
    pro_setup_sessions.pop(user_id, None)

    session = await db.get_pro_session()

    if session:
        status = "✅ **𝕏TV Pro™ is Active**\n\nThe 4GB tunnel Userbot is fully setup and running."
        buttons = [
            [InlineKeyboardButton("🗑 Delete Session & Re-Setup", callback_data="pro_setup_start")],
            [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_main")]
        ]
    else:
        status = "❌ **𝕏TV Pro™ is Disabled**\n\nThe 4GB tunnel Userbot is not configured."
        buttons = [
            [InlineKeyboardButton("🚀 Setup 𝕏TV Pro™", callback_data="pro_setup_start")],
            [InlineKeyboardButton("🔙 Back to Admin Menu", callback_data="admin_main")]
        ]

    await callback_query.message.edit_text(status, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^pro_setup_start$"))
async def start_setup(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id != Config.CEO_ID: return

    pro_setup_sessions[user_id] = {"state": "awaiting_api_id"}
    await callback_query.message.edit_text(
        "🚀 **𝕏TV Pro™ Setup**\n\n"
        "Let's configure the Userbot tunnel for 4GB files.\n"
        "First, please send me your **API ID** (e.g., `1234567`):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]])
    )

@Client.on_message(filters.private & filters.user(Config.CEO_ID))
async def pro_setup_handler(client, message, group=0):
    user_id = message.from_user.id
    if user_id not in pro_setup_sessions:
        raise ContinuePropagation

    data = pro_setup_sessions[user_id]
    state = data.get("state")
    if not state:
        raise ContinuePropagation

    text = message.text.strip() if message.text else ""
    if not text:
        return await message.reply_text("Please provide text.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]]))

    if state == "awaiting_api_id":
        if not text.isdigit():
            return await message.reply_text("API ID must be numeric. Try again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]]))
        data["api_id"] = int(text)
        data["state"] = "awaiting_api_hash"
        await message.reply_text(
            "✅ Got API ID.\n\nNow, send me your **API Hash**:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]])
        )

    elif state == "awaiting_api_hash":
        data["api_hash"] = text
        data["state"] = "awaiting_phone"
        await message.reply_text(
            "✅ Got API Hash.\n\n"
            "Now, send your **Phone Number** in international format (e.g., `+1234567890`):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]])
        )

    elif state == "awaiting_phone":
        data["phone"] = text
        msg = await message.reply_text("⏳ Generating session and requesting code from Telegram...")

        try:
            # Create temporary client
            session_name = f"temp_session_{user_id}_{random.randint(1000, 9999)}"
            data["client"] = Client(
                session_name,
                api_id=data["api_id"],
                api_hash=data["api_hash"],
                in_memory=True
            )
            await data["client"].connect()
            sent_code = await data["client"].send_code(data["phone"])
            data["phone_code_hash"] = sent_code.phone_code_hash
            data["state"] = "awaiting_code"

            await msg.edit_text(
                "✅ **Verification Code Sent!**\n\n"
                "Check your Telegram app for the login code.\n"
                "**IMPORTANT:** Enter the code with spaces to avoid Telegram's security triggers.\n"
                "For example, if your code is `12345`, enter `1 2 3 4 5`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]])
            )
        except ApiIdInvalid:
            await msg.edit_text("❌ **Invalid API ID / Hash**. Setup failed.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pro_setup_menu")]]))
            del pro_setup_sessions[user_id]
        except PhoneNumberInvalid:
            await msg.edit_text("❌ **Invalid Phone Number**. Setup failed.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pro_setup_menu")]]))
            del pro_setup_sessions[user_id]
        except Exception as e:
            await msg.edit_text(f"❌ **Error requesting code:** {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pro_setup_menu")]]))
            del pro_setup_sessions[user_id]

    elif state == "awaiting_code":
        code = text.replace(" ", "")
        msg = await message.reply_text("⏳ Verifying code...")

        userbot = data.get("client")
        try:
            await userbot.sign_in(data["phone"], data["phone_code_hash"], code)
            await finalize_setup(userbot, user_id, msg)
        except SessionPasswordNeeded:
            data["state"] = "awaiting_password"
            await msg.edit_text(
                "🔐 **Two-Step Verification Enabled**\n\n"
                "Please enter your 2FA password:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]])
            )
        except PhoneCodeInvalid:
            await msg.edit_text("❌ **Invalid Code**. Try again or restart setup.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]]))
        except Exception as e:
            await msg.edit_text(f"❌ **Sign In Error:** {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]]))
            del pro_setup_sessions[user_id]

    elif state == "awaiting_password":
        msg = await message.reply_text("⏳ Verifying password...")
        userbot = data.get("client")
        try:
            await userbot.check_password(text)
            await finalize_setup(userbot, user_id, msg)
        except PasswordHashInvalid:
            await msg.edit_text("❌ **Invalid Password**. Try again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]]))
        except Exception as e:
            await msg.edit_text(f"❌ **Error:** {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pro_setup_menu")]]))
            del pro_setup_sessions[user_id]

async def finalize_setup(userbot, user_id, msg):
    try:
        me = await userbot.get_me()
        if not me.is_premium:
            await msg.edit_text(
                "❌ **Premium Account Required**\n\n"
                "Your account doesn't have Telegram Premium.\n"
                "Buy it or complete the setup with an account that has Premium to unlock 4GB uploads.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pro_setup_menu")]])
            )
            await userbot.disconnect()
            del pro_setup_sessions[user_id]
            return

        session_string = await userbot.export_session_string()
        data = pro_setup_sessions[user_id]

        await db.save_pro_session(session_string, data["api_id"], data["api_hash"])

        # Auto-Create Tunnel Channel
        await msg.edit_text("⏳ **Initializing Internal Pro Tunnel...**")

        try:
            bot_me = await msg._client.get_me()
            bot_username = bot_me.username

            # Create a private channel
            channel = await userbot.create_channel(
                title="𝕏TV Pro™ Internal Tunnel",
                description="Do not delete. Used by XTV Bot to bridge >2GB files between users and the Userbot."
            )
            tunnel_id = channel.id

            # Add main bot to channel and promote
            from pyrogram.types import ChatPrivileges
            await userbot.promote_chat_member(
                tunnel_id,
                bot_username,
                privileges=ChatPrivileges(
                    can_manage_chat=True,
                    can_delete_messages=True,
                    can_manage_video_chats=True,
                    can_restrict_members=True,
                    can_promote_members=True,
                    can_change_info=True,
                    can_post_messages=True,
                    can_edit_messages=True,
                    can_invite_users=True,
                    can_pin_messages=True
                )
            )

            # Create an invite link so the Main Bot can cache the peer
            invite_link_obj = await userbot.create_chat_invite_link(tunnel_id)
            tunnel_link = invite_link_obj.invite_link

            await db.save_pro_tunnel(tunnel_id, tunnel_link)
        except Exception as tunnel_e:
            logger.error(f"Failed to create tunnel: {tunnel_e}")

        # Start userbot on the main app
        main_app = msg._client
        if not getattr(main_app, "user_bot", None):
            main_app.user_bot = Client(
                "xtv_user_bot",
                api_id=data["api_id"],
                api_hash=data["api_hash"],
                session_string=session_string,
                workers=50,
                max_concurrent_transmissions=10
            )
            await main_app.user_bot.start()
            logger.info("𝕏TV Pro™ Premium Userbot Hot-Started Successfully!")

            # Ping the tunnel to cache peer for Main Bot
            try:
                ping_msg = await main_app.user_bot.send_message(tunnel_id, "ping", disable_notification=True)
                await ping_msg.delete()
            except Exception as e:
                logger.warning(f"Could not ping tunnel immediately after setup: {e}")

            # Start cleanup task
            from main import cleanup_tunnel
            main_app.loop.create_task(cleanup_tunnel(main_app))

        await msg.edit_text(
            "✅ **𝕏TV Pro™ Setup Complete!**\n\n"
            f"Successfully authenticated as **{me.first_name}**.\n"
            "Session string and credentials saved to the database.\n"
            "**𝕏TV Pro™ is now active and ready to process >2GB files.**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_main")]])
        )
        await userbot.disconnect()
        del pro_setup_sessions[user_id]
    except Exception as e:
        await msg.edit_text(f"❌ **Failed to finalize setup:** {e}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="pro_setup_menu")]]))
        del pro_setup_sessions[user_id]
