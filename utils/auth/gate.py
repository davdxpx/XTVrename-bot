# --- Imports ---
import asyncio
import contextlib
from collections import OrderedDict

from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db import db
from utils.state import update_data
from utils.tasks import spawn
from utils.telegram.log import get_logger

logger = get_logger("utils.auth.gate")


# === Helper Functions ===
async def send_force_sub_gate(client, message, config):
    user_id = message.from_user.id

    bot_name = config.get("bot_name", "𝕏TV MediaStudio™")
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

        channels = [{"id": legacy_ch, "link": legacy_link, "username": legacy_user, "title": "our channel"}]

    if not msg_text:
        msg_text = (
            "👋 Hey! To use this bot, you must join our channel first.\n\n"
            "Hit the button below, join, then come back and try again. ✅"
        )

    first_ch = channels[0] if channels else {}
    channel_name = first_ch.get("username", first_ch.get("title", "our channel"))
    if channel_name and not str(channel_name).startswith("@") and not str(channel_name).isdigit():

         pass

    formatted_text = msg_text.replace("{channel}", str(channel_name)).replace("{bot_name}", bot_name).replace("{community}", community_name)

    buttons = []

    for ch in channels:
        if ch.get("link"):

            if config.get("force_sub_button_label"):
                final_btn_text = f"{btn_emoji} {btn_label}"
            else:
                title = ch.get("title", "Channel")
                final_btn_text = f"{btn_emoji} Join {title}"

            buttons.append([InlineKeyboardButton(final_btn_text, url=ch.get("link"))])

    msg = None
    for attempt in range(3):
        try:
            if banner_file_id:
                msg = await client.send_photo(
                    chat_id=user_id,
                    photo=banner_file_id,
                    caption=formatted_text,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            else:
                msg = await client.send_message(
                    chat_id=user_id,
                    text=formatted_text,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            break
        except FloodWait as e:
            wait = min(getattr(e, "value", 1) + 1, 60)
            logger.warning(
                f"send_force_sub_gate FloodWait {wait}s (attempt {attempt + 1}/3)"
            )
            if attempt >= 2:
                return
            await asyncio.sleep(wait)
        except Exception as e:
            logger.warning(f"send_force_sub_gate failed: {e}")
            return

    if msg:
        update_data(user_id, "force_sub_msg_id", msg.id)

# Bounded LRU. When full, the oldest entry is evicted (not the whole
# set cleared) so long-lived users never get a second welcome burst
# after the cache rolls over.
_MAX_WELCOMED = 10000
welcomed_users: "OrderedDict[int, None]" = OrderedDict()

async def check_and_send_welcome(client, message, config):
    user_id = message.from_user.id

    if user_id not in welcomed_users:
        # LRU-evict the oldest entry when full — never purge everything
        # at once, which caused repeat-welcomes after every 10k users.
        if len(welcomed_users) >= _MAX_WELCOMED:
            welcomed_users.popitem(last=False)
        welcomed_users[user_id] = None

        has_setup = await db.has_completed_setup(user_id)
        if not has_setup:
            return

        welcome_text = config.get("force_sub_welcome_text") or "✅ Welcome aboard! You're all set. Send your file and let's go."

        msg = None
        try:
            msg = await client.send_message(user_id, welcome_text)
        except FloodWait as e:
            wait = min(getattr(e, "value", 1) + 1, 60)
            logger.warning(f"welcome send FloodWait {wait}s")
            await asyncio.sleep(wait)
            with contextlib.suppress(Exception):
                msg = await client.send_message(user_id, welcome_text)
        except Exception as e:
            logger.debug(f"welcome send failed: {e}")
            return

        if not msg:
            return

        async def delete_later():
            await asyncio.sleep(5)
            with contextlib.suppress(Exception):
                await msg.delete()

        spawn(delete_later(), user_id=user_id, label="gate_welcome_delete")

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
