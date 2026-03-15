"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    Developed by 𝕏0L0™ (@davdxpx)                         ║
║     © 2026 XTV Network Global. All Rights Reserved.                      ║
║                                                                          ║
║  Project: XTV Rename Bot                                                 ║
║  Author: 𝕏0L0™                                                           ║
║  Telegram: @davdxpx                                                      ║
║  Channel: @XTVbots                                                       ║
║  Network: @XTVglobal                                                     ║
║  Backup: @XTVhome                                                        ║
║                                                                          ║
║  WARNING: This code is the intellectual property of XTV Network.         ║
║  Unauthorized modification, redistribution, or removal of this credit    ║
║  is strictly prohibited. Forking and simple usage is allowed under       ║
║  the terms of the license.                                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

from pyrogram import Client, idle
from config import Config
from utils.log import get_logger

logger = get_logger("main")

app = Client(
    "xtv_rename_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    workers=50,
    max_concurrent_transmissions=10,
    plugins=dict(root="plugins"),
)

user_bot = None

if __name__ == "__main__":
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        exit(1)

    # Print stylish startup banner
    startup_msg = (
        f"\n{'='*50}\n"
        f"🚀 Starting XTV Rename Bot {Config.VERSION}\n"
        f"🛠️  Debug Mode: {'ON' if Config.DEBUG_MODE else 'OFF'}\n"
        f"🌍 Public Mode: {'ON' if Config.PUBLIC_MODE else 'OFF'}\n"
        f"{'='*50}"
    )
    logger.info(startup_msg)

    app.start()

    try:
        from database import db

        async def cache_channels():
            links = await db.get_all_dumb_channel_links()
            for link in links:
                try:
                    await app.get_chat(link)
                except Exception as e:
                    pass

        logger.info("Caching Channel peers...")
        app.loop.run_until_complete(cache_channels())
    except Exception as e:
        logger.warning(f"Error during Channel caching: {e}")

    try:
        from database import db

        async def get_userbot_session():
            return await db.get_pro_session()

        pro_data = app.loop.run_until_complete(get_userbot_session())

        if pro_data and pro_data.get("session_string"):
            logger.info(
                "𝕏TV Pro™ Session detected in database. Initializing Premium Userbot..."
            )
            user_bot = Client(
                "xtv_user_bot",
                api_id=pro_data.get("api_id", Config.API_ID),
                api_hash=pro_data.get("api_hash", Config.API_HASH),
                session_string=pro_data.get("session_string"),
                workers=50,
                max_concurrent_transmissions=10,
            )
            app.user_bot = user_bot

            logger.info("Starting 𝕏TV Pro™ Premium Userbot...")
            user_bot.start()
            logger.info("𝕏TV Pro™ Premium Userbot Started Successfully!")

        else:
            app.user_bot = None
            logger.warning(
                "No 𝕏TV Pro™ Session found in database. 4GB upload support is DISABLED."
            )
    except Exception as e:
        logger.error(f"Failed to initialize Userbot from DB: {e}")
        app.user_bot = None

    logger.info("Bot Started!")
    idle()

    if user_bot:
        try:
            user_bot.stop()
        except:
            pass

    app.stop()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
