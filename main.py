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
import os
import time
import asyncio
import datetime
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

# Load additional tools explicitly since they are in a different directory
# The plugins dict usually only loads from one root. To ensure tools are registered,
# we import them here before the app starts.
import tools.FileConverter
import tools.AudioMetadataEditor
import tools.ImageWatermarker
import tools.SubtitleExtractor

def register_tool_handlers(client, module):
    for name in dir(module):
        obj = getattr(module, name)
        # Pyrogram stores handlers as a list of tuples (handler, group) on the decorated function itself.
        if callable(obj) and hasattr(obj, "handlers") and isinstance(obj.handlers, list):
            for item in obj.handlers:
                if isinstance(item, tuple) and len(item) == 2:
                    handler, group = item
                    client.add_handler(handler, group)

register_tool_handlers(app, tools.FileConverter)
register_tool_handlers(app, tools.AudioMetadataEditor)
register_tool_handlers(app, tools.ImageWatermarker)
register_tool_handlers(app, tools.SubtitleExtractor)

user_bot = None


def _sync_cleanup_orphaned_files():
    """Synchronous file cleanup — run via asyncio.to_thread to avoid blocking."""
    download_dir = Config.DOWNLOAD_DIR
    if not os.path.exists(download_dir):
        return 0, 0

    now = time.time()
    cutoff = now - (24 * 3600)  # 24 hours
    cleaned_count = 0
    freed_space = 0

    for root, _, files in os.walk(download_dir):
        for f in files:
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
            except OSError as e:
                logger.warning(f"Error cleaning file {file_path}: {e}")

    return cleaned_count, freed_space


if __name__ == "__main__":
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        exit(1)

    logger.info("Starting 𝕏TV MediaStudio™...")
    app.start()

    # --- Database migrations ---
    try:
        from database import db
        logger.info("Running DB migrations...")
        app.loop.run_until_complete(db.migrate_old_db_to_new())
        app.loop.run_until_complete(db.migrate_global_dumb_channels_to_ceo())
    except Exception as e:
        logger.warning(f"Error during DB migration: {e}")

    # --- Database indexes ---
    try:
        from database import db
        logger.info("Ensuring database indexes...")
        app.loop.run_until_complete(db.ensure_indexes())
    except Exception as e:
        logger.warning(f"Error creating indexes: {e}")

    # --- Channel peer caching ---
    try:
        from database import db

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

    # --- Background tasks ---
    try:
        from database import db

        async def db_cleanup():
            while True:
                try:
                    now = datetime.datetime.utcnow()
                    # Delete expired temporary files from DB
                    result = await db.files.delete_many(
                        {"status": "temporary", "expires_at": {"$lt": now}}
                    )
                    if result.deleted_count:
                        logger.info(f"Cleaned up {result.deleted_count} expired temporary files from DB.")

                    # Also clean orphaned disk files
                    cleaned, freed = await asyncio.to_thread(_sync_cleanup_orphaned_files)
                    if cleaned:
                        logger.info(f"Cleaned {cleaned} orphaned disk files, freed {freed / (1024*1024):.2f} MB.")
                except Exception as e:
                    logger.error(f"Error during DB cleanup: {e}")

                await asyncio.sleep(21600)  # Every 6 hours

        async def state_cleanup():
            """Periodically clean up expired user sessions and queue batches."""
            while True:
                await asyncio.sleep(1800)  # Every 30 minutes
                try:
                    from utils.state import cleanup_expired as state_cleanup_fn
                    state_cleanup_fn()
                except Exception as e:
                    logger.debug(f"State cleanup: {e}")
                try:
                    from utils.queue_manager import queue_manager
                    queue_manager.cleanup_completed()
                except Exception as e:
                    logger.debug(f"Queue cleanup: {e}")

        logger.info("Scheduling background tasks...")
        asyncio.create_task(db_cleanup())
        asyncio.create_task(state_cleanup())

    except Exception as e:
        logger.warning(f"Could not schedule background tasks: {e}")

    # --- Recover stale flow sessions from DB ---
    try:
        from database import db

        async def recover_stale_sessions():
            cursor = db.users.find({"flow_session": {"$exists": True}})
            count = 0
            async for user_doc in cursor:
                uid = user_doc.get("user_id")
                if uid:
                    try:
                        await app.send_message(
                            uid,
                            "The bot was restarted and your active renaming session was lost.\n"
                            "Please start again by sending a file or using /start."
                        )
                    except Exception:
                        pass
                    await db.clear_flow_session(uid)
                    count += 1
            if count:
                logger.info(f"Recovered {count} stale flow sessions from DB.")

        logger.info("Checking for stale flow sessions...")
        asyncio.create_task(recover_stale_sessions())
    except Exception as e:
        logger.warning(f"Error recovering stale sessions: {e}")

    # --- Orphaned file cleanup (async, non-blocking) ---
    try:
        async def async_cleanup_orphaned():
            cleaned_count, freed_space = await asyncio.to_thread(_sync_cleanup_orphaned_files)
            if cleaned_count > 0:
                logger.info(f"Cleanup complete. Removed {cleaned_count} files, freed {freed_space / (1024*1024):.2f} MB.")
            else:
                logger.info("Cleanup complete. No orphaned files found.")

        logger.info("Running automated orphaned file cleanup...")
        asyncio.create_task(async_cleanup_orphaned())
    except Exception as e:
        logger.warning(f"Error during orphaned file cleanup: {e}")

    # --- XTV Pro userbot ---
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

    # --- Startup diagnostics ---
    admins_count = len(Config.ADMIN_IDS)
    tmdb_status = "Configured" if Config.TMDB_API_KEY else "Missing"
    db_status = "Configured" if Config.MAIN_URI else "Missing"
    xtv_pro_status = "Enabled (4GB Support)" if getattr(app, 'user_bot', None) else "Disabled (2GB Limit)"

    startup_msg = (
        f"\n{'='*60}\n"
        f"  𝕏TV MediaStudio {Config.VERSION} Initialization\n"
        f"{'-'*60}\n"
        f"  Core Settings:\n"
        f"   - Debug Mode  : {'ON' if Config.DEBUG_MODE else 'OFF'}\n"
        f"   - Public Mode : {'ON' if Config.PUBLIC_MODE else 'OFF'}\n"
        f"   - XTV Pro     : {xtv_pro_status}\n"
        f"\n"
        f"  Access Control:\n"
        f"   - CEO ID      : {Config.CEO_ID if Config.CEO_ID else 'Not Set'}\n"
        f"   - Admins      : {admins_count} configured\n"
        f"\n"
        f"  Integrations:\n"
        f"   - Database    : {db_status}\n"
        f"   - TMDb API    : {tmdb_status}\n"
        f"\n"
        f"  Storage:\n"
        f"   - Down Dir    : ./{Config.DOWNLOAD_DIR}\n"
        f"   - Def Channel : {Config.DEFAULT_CHANNEL}\n"
        f"{'='*60}"
    )
    logger.info(startup_msg)
    idle()

    # --- Graceful shutdown ---
    logger.info("Shutting down...")

    # Close persistent HTTP sessions
    try:
        from utils.tmdb import tmdb
        app.loop.run_until_complete(tmdb.close())
    except Exception as e:
        logger.debug(f"TMDb session cleanup: {e}")

    try:
        from utils.currency import close_session as close_currency_session
        app.loop.run_until_complete(close_currency_session())
    except Exception as e:
        logger.debug(f"Currency session cleanup: {e}")

    if user_bot:
        try:
            user_bot.stop()
        except Exception as e:
            logger.warning(f"Error stopping userbot: {e}")

    app.stop()
    logger.info("𝕏TV MediaStudio shut down cleanly.")

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
