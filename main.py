"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    Developed by 𝕏0L0™ (@davdxpx)                         ║
║     © 2026 XTV Network Global. All Rights Reserved.                      ║
║                                                                          ║
║  Project: 𝕏TV MediaStudio™                                                 ║
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
    "xtv_mediastudio",
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

    logger.info("Starting 𝕏TV MediaStudio™...")
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
        import os
        import time
        from config import Config

        def cleanup_orphaned_files():
            logger.info("Running automated orphaned file cleanup...")

            # DB Expiration logic
            import asyncio
            from database import db
            import datetime

            async def db_cleanup():
                now = datetime.datetime.utcnow()
                try:
                    # Find all temporary files that have expired
                    cursor = db.files.find({"status": "temporary", "expires_at": {"$lt": now}})
                    expired_files = await cursor.to_list(length=None)

                    if expired_files:
                        logger.info(f"Found {len(expired_files)} expired temporary files. Cleaning up...")
                        # Delete them from DB
                        await db.files.delete_many({"status": "temporary", "expires_at": {"$lt": now}})

                        # Note: In a full system we'd also delete the message from the db_channel,
                        # but standard Telegram logic is that messages live forever in channels.
                        # For privacy/compliance, we'll just delete our record of them.
                except Exception as e:
                    logger.error(f"Error during DB cleanup: {e}")

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(db_cleanup())
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(db_cleanup())
                loop.close()
            except Exception as e:
                logger.warning(f"Could not run DB cleanup tasks: {e}")

            download_dir = Config.DOWNLOAD_DIR
            if not os.path.exists(download_dir):
                return

            now = time.time()
            cutoff = now - (24 * 3600)  # 24 hours
            cleaned_count = 0
            freed_space = 0

            for root, _, files in os.walk(download_dir):
                for f in files:
                    # Ignore standard static files
                    if f == "thumb.jpg":
                        continue
                    file_path = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(file_path)
                        if mtime < cutoff:
                            size = os.path.getsize(file_path)
                            os.remove(file_path)
                            cleaned_count += 1
                            freed_space += size
                            logger.debug(f"Cleaned orphaned file: {file_path}")
                    except Exception as e:
                        logger.warning(f"Error cleaning file {file_path}: {e}")

            if cleaned_count > 0:
                logger.info(f"Cleanup complete. Removed {cleaned_count} files, freed {freed_space / (1024*1024):.2f} MB.")
            else:
                logger.info("Cleanup complete. No orphaned files found.")

        cleanup_orphaned_files()
    except Exception as e:
        logger.warning(f"Error during orphaned file cleanup: {e}")

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
        f"🚀 𝕏TV MediaStudio™ {Config.VERSION} Initialization\n"
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
