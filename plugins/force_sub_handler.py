from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from database import db
from plugins.admin import admin_sessions, is_admin
from config import Config
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.log import get_logger

logger = get_logger("plugins.force_sub_handler")


@Client.on_chat_member_updated(filters.channel)
async def handle_bot_added_to_channel(client, update):
    if not Config.PUBLIC_MODE:
        return

    user_id = update.from_user.id

    if not is_admin(user_id):
        return

    state = admin_sessions.get(user_id)
    if state not in ["awaiting_public_force_sub", "awaiting_fs_add_channel"] and not (isinstance(state, str) and state.startswith("awaiting_force_sub_channel_")):
        return

    new_status = update.new_chat_member.status if update.new_chat_member else None

    if new_status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        chat_id = update.chat.id
        chat_title = update.chat.title

        try:
            chat_info = await client.get_chat(chat_id)
            invite_link = chat_info.invite_link
            if not invite_link:
                invite_link = await client.export_chat_invite_link(chat_id)

            username = chat_info.username

            if state == "awaiting_public_force_sub":
                # Legacy single-channel
                await db.update_public_config("force_sub_channel", chat_id)
                await db.update_public_config("force_sub_link", invite_link)
                await db.update_public_config("force_sub_username", username)

                await client.send_message(
                    chat_id=user_id,
                    text=f"✅ **Force-Sub Setup Complete!**\n\nI successfully detected that you added me to **{chat_title}**.\n\nChannel ID: `{chat_id}`\nSaved Link: {invite_link}",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🔙 Back to Menu", callback_data="admin_main"
                                )
                            ]
                        ]
                    ),
                )
                admin_sessions.pop(user_id, None)
            else:
                # Multi-channel setup
                config = await db.get_public_config()
                channels = config.get("force_sub_channels", [])

                new_channel = {
                    "id": chat_id,
                    "link": invite_link,
                    "username": username,
                    "title": chat_title,
                    "button_label": f"📢 Join {chat_title}"
                }

                channels.append(new_channel)
                await db.update_public_config("force_sub_channels", channels)

                # Keep legacy field populated for backward compat if it's the first channel
                if len(channels) == 1:
                    await db.update_public_config("force_sub_channel", chat_id)
                    await db.update_public_config("force_sub_link", invite_link)
                    await db.update_public_config("force_sub_username", username)

                await client.send_message(
                    chat_id=user_id,
                    text=f"✅ **Force-Sub Channel Added!**\n\nI successfully detected that you added me to **{chat_title}**.\n\nChannel ID: `{chat_id}`\nSaved Link: {invite_link}",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🔙 Back to Config", callback_data="admin_force_sub_menu"
                                )
                            ]
                        ]
                    ),
                )
                admin_sessions.pop(user_id, None)


        except Exception as e:
            logger.error(f"Force sub setup error during chat_member_updated: {e}")
            await client.send_message(
                chat_id=user_id,
                text=f"❌ **Failed to verify channel.**\n\nI was added to the channel, but I don't have permission to create invite links. Please grant me the 'Invite Users via Link' permission.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Cancel", callback_data="admin_force_sub_menu")]]
                ),
            )


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------

@Client.on_chat_member_updated(filters.channel, group=1)
async def on_user_join_channel(client, update):
    # Ignore bot updates for this specific logic
    if update.new_chat_member and update.new_chat_member.user.is_bot:
        return

    # We only care if user joined
    joined = False
    valid_statuses = [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]

    if not update.old_chat_member:
        if update.new_chat_member and update.new_chat_member.status in valid_statuses:
            joined = True
    else:
        if update.old_chat_member.status not in valid_statuses and update.new_chat_member.status in valid_statuses:
            joined = True

    if not joined:
        return

    user = update.new_chat_member.user

    if not Config.PUBLIC_MODE:
        return

    # Verify if they joined one of the force sub channels
    config = await db.get_public_config()
    force_sub_channels = config.get("force_sub_channels", [])
    legacy_channel = config.get("force_sub_channel")

    channels_to_check = []
    if force_sub_channels:
        for ch in force_sub_channels:
            if ch.get("id"):
                channels_to_check.append(str(ch["id"]))
    elif legacy_channel:
        channels_to_check.append(str(legacy_channel))

    chat_id_str = str(update.chat.id)
    chat_username = f"@{update.chat.username}" if update.chat.username else None

    is_force_sub_channel = False
    if chat_id_str in channels_to_check:
        is_force_sub_channel = True
    elif chat_username and chat_username in channels_to_check:
        is_force_sub_channel = True

    if not is_force_sub_channel:
        return

    logger.debug(f"User {user.id} joined force sub channel {update.chat.id}")

    # They joined a force sub channel. Now, check if they have completed the setup.
    has_setup = await db.has_completed_setup(user.id)
    if has_setup:
        return

    # Send the starter setup message
    await send_starter_setup_message(client, user.id, user.first_name)


async def send_starter_setup_message(client, user_id, first_name=""):
    bot_name = "**𝕏TV Rename Bot**"
    if Config.PUBLIC_MODE:
        config = await db.get_public_config()
        bot_name = f"**{config.get('bot_name', 'XTV Rename Bot')}**"

    text = (
        f"👋 **Welcome to {bot_name}, {first_name}!**\\n\\n"
        "You are now ready to use the bot. To give you the best experience, "
        "please select what you primarily want to use this bot for:\\n\\n"
        "**🧠 Smart Media Mode:** Best for TV Shows and Movies. I will automatically detect seasons, episodes, and download TMDb posters/metadata!\\n\\n"
        "**⚡ Quick Rename Mode:** Best for Personal Videos, Anime, or general files. I will skip auto-detection and just let you rename the file immediately."
    )

    markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🧠 Smart Media Mode", callback_data="setup_mode_smart")],
            [InlineKeyboardButton("⚡ Quick Rename Mode", callback_data="setup_mode_quick")]
        ]
    )

    try:
        await client.send_message(chat_id=user_id, text=text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Failed to send starter setup message to {user_id}: {e}")


@Client.on_callback_query(filters.regex(r"^setup_mode_"))
async def handle_setup_mode_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "setup_mode_smart":
        mode = "smart_media_mode"
        mode_str = "🧠 Smart Media Mode"
    else:
        mode = "quick_rename_mode"
        mode_str = "⚡ Quick Rename Mode"

    await db.update_workflow_mode(mode, user_id)
    await db.mark_setup_completed(user_id, True)

    text = (
        f"✅ **Setup Complete!**\\n\\n"
        f"You have selected **{mode_str}**.\\n"
        "*(You can change this anytime via /settings)*\\n\\n"
        "**💡 Tip:** Simply send or forward any file to me right now to begin!"
    )

    await callback_query.message.edit_text(text)
    await callback_query.answer("Preferences saved!", show_alert=False)
