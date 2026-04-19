# --- Imports ---
from pyrogram import filters
from pyrogram.errors import PeerIdInvalid, UserNotParticipant

from config import Config
from db import db
from utils.telegram.log import get_logger

logger = get_logger("utils.auth")

# === Helper Functions ===
def is_authorized(user_id):
    if Config.PUBLIC_MODE:
        return True
    return user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS

def is_admin(user_id):
    return user_id == Config.CEO_ID

async def check_force_sub(client, user_id):
    if not Config.PUBLIC_MODE:
        return True

    if user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS:
        return True

    config = await db.get_public_config()
    force_sub_channels = config.get("force_sub_channels", [])
    legacy_channel = config.get("force_sub_channel")

    channels_to_check = []
    if force_sub_channels:
        for ch in force_sub_channels:
            if ch.get("id"):
                channels_to_check.append(ch["id"])
    elif legacy_channel:
        channels_to_check.append(legacy_channel)

    if not channels_to_check:
        return True

    for channel in channels_to_check:
        try:
            await client.get_chat_member(channel, user_id)
        except UserNotParticipant:
            return False
        except PeerIdInvalid:

            try:
                await client.get_chat(channel)
                await client.get_chat_member(channel, user_id)
            except UserNotParticipant:
                return False
            except Exception as e:
                logger.error(
                    f"Error checking force sub for {user_id} in {channel} (after get_chat fallback): {e}"
                )

                continue
        except Exception as e:
            logger.error(
                f"Error checking force sub for {user_id} in {channel}: {e}"
            )

            continue

    return True

auth_filter = filters.create(
    lambda _, __, update: is_authorized(update.from_user.id if update.from_user else 0)
)
admin_filter = filters.create(
    lambda _, __, update: is_admin(update.from_user.id if update.from_user else 0)
)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
