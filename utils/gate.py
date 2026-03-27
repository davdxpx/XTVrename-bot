import asyncio
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

async def send_force_sub_gate(client, message, config):
    user_id = message.from_user.id

    bot_name = config.get("bot_name", "XTV Rename Bot")
    community_name = config.get("community_name", "Our Community")

    banner_file_id = config.get("force_sub_banner_file_id")
    msg_text = config.get("force_sub_message_text")
    btn_label = config.get("force_sub_button_label", "Join Channel")
    btn_emoji = config.get("force_sub_button_emoji", "📢")

    channels = config.get("force_sub_channels", [])
    legacy_ch = config.get("force_sub_channel")
    legacy_link = config.get("force_sub_link")
    legacy_user = config.get("force_sub_username", "")

    if not channels and legacy_ch:
        # Fallback to single channel
        channels = [{"id": legacy_ch, "link": legacy_link, "username": legacy_user, "title": "our channel"}]

    if not msg_text:
        msg_text = (
            "👋 Hey! To use this bot, you must join our channel first.\n\n"
            "Hit the button below, join, then come back and try again. ✅"
        )

    first_ch = channels[0] if channels else {}
    channel_name = first_ch.get("username", first_ch.get("title", "our channel"))
    if channel_name and not str(channel_name).startswith("@") and not str(channel_name).isdigit():
         # Keep it as is or add @ if it's a username, but we'll assume username is already @ formatted or it's a title
         pass

    formatted_text = msg_text.replace("{channel}", str(channel_name)).replace("{bot_name}", bot_name).replace("{community}", community_name)

    buttons = []

    # Send the "You're In!" message later if they are returning
    # If the CEO set a custom label globally, use it, otherwise use the per-channel label
    for ch in channels:
        if ch.get("link"):
            # Default per-channel label was "📢 Join [Channel Title]"
            # If the admin edited the global button label, we override it
            if config.get("force_sub_button_label"):
                final_btn_text = f"{btn_emoji} {btn_label}"
            else:
                title = ch.get("title", "Channel")
                final_btn_text = f"{btn_emoji} Join {title}"

            buttons.append([InlineKeyboardButton(final_btn_text, url=ch.get("link"))])

    if banner_file_id:
        await client.send_photo(
            chat_id=user_id,
            photo=banner_file_id,
            caption=formatted_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await client.send_message(
            chat_id=user_id,
            text=formatted_text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

welcomed_users = set()

async def check_and_send_welcome(client, message, config):
    user_id = message.from_user.id

    # Simple check: if user hasn't been welcomed yet in this session
    if user_id not in welcomed_users:
        welcomed_users.add(user_id)

        # If they haven't completed setup, don't spam the welcome message because the setup menu will pop up
        has_setup = await db.has_completed_setup(user_id)
        if not has_setup:
            return

        # Then send the message
        welcome_text = config.get("force_sub_welcome_text") or "✅ Welcome aboard! You're all set. Send your file and let's go."

        msg = await client.send_message(user_id, welcome_text)

        # Auto-delete after 5s
        async def delete_later():
            await asyncio.sleep(5)
            try:
                await msg.delete()
            except Exception:
                pass

        asyncio.create_task(delete_later())
