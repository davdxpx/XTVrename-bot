"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    Developed by 𝕏0L0™ (@davdxpx)                         ║
║     © 2026 XTV Network Global. All Rights Reserved.                      ║
║                                                                          ║
║  Project: 𝕏TV Rename Bot                                                 ║
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

# --- Imports ---
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

    logger.info("Starting 𝕏TV Rename Bot...")
    app.start()

    try:
        from database import db
        logger.info("Running DB migrations...")
        app.loop.run_until_complete(db.migrate_old_db_to_new())
    except Exception as e:
        logger.warning(f"Error during DB migration: {e}")

    try:
        from database import db
        import asyncio

        async def cache_channels():
            links = await db.get_all_dumb_channel_links()
            tasks = []

            async def cache_link(link):
                try:
                    await app.get_chat(link)
                except Exception:
                    pass

            for link in links:
                tasks.append(cache_link(link))

            config = await db.get_public_config()
            force_sub_channels = config.get("force_sub_channels", [])
            legacy_ch = config.get("force_sub_channel")

            async def cache_id(ch_id):
                try:
                    await app.get_chat(ch_id)
                except Exception:
                    pass

            if force_sub_channels:
                for ch in force_sub_channels:
                    if ch.get("id"):
                        tasks.append(cache_id(ch["id"]))
            elif legacy_ch:
                tasks.append(cache_id(legacy_ch))

            if tasks:
                await asyncio.gather(*tasks)

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

    admins_count = len(Config.ADMIN_IDS)
    tmdb_status = "✅ Configured" if Config.TMDB_API_KEY else "❌ Missing"
    db_status = "✅ Configured" if Config.MAIN_URI else "❌ Missing"
    xtv_pro_status = "🟢 Enabled (4GB Support)" if app.user_bot else "🔴 Disabled (2GB Limit)"

    startup_msg = (
        f"\n{'='*60}\n"
        f"🚀 𝕏TV Rename Bot {Config.VERSION} Initialization\n"
        f"{'-'*60}\n"
        f"⚙️  Core Settings:\n"
        f"   • Debug Mode  : {'🟢 ON' if Config.DEBUG_MODE else '🔴 OFF'}\n"
        f"   • Public Mode : {'🟢 ON' if Config.PUBLIC_MODE else '🔴 OFF'}\n"
        f"   • 𝕏TV Pro™    : {xtv_pro_status}\n"
        f"\n"
        f"👥 Access Control:\n"
        f"   • CEO ID      : {Config.CEO_ID if Config.CEO_ID else 'Not Set'}\n"
        f"   • Admins      : {admins_count} configured\n"
        f"\n"
        f"🔗 Integrations:\n"
        f"   • Database    : {db_status}\n"
        f"   • TMDb API    : {tmdb_status}\n"
        f"\n"
        f"📁 Storage:\n"
        f"   • Down Dir    : ./{Config.DOWNLOAD_DIR}\n"
        f"   • Def Channel : {Config.DEFAULT_CHANNEL}\n"
        f"{'='*60}"
    )
    logger.info(startup_msg)
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
