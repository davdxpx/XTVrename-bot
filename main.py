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

# Configure logging
logger = get_logger("main")

# Initialize Bot
# High performance settings: workers=50, max_concurrent_transmissions=10
app = Client(
    "xtv_rename_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    workers=50,
    max_concurrent_transmissions=10,
    plugins=dict(root="plugins")
)

# Initialize Userbot (for >2GB support)
user_bot = None

if __name__ == "__main__":
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        exit(1)

    logger.info("Starting XTV Rename Bot...")
    app.start()

    # Cache Dumb Channel peers using stored invite links to prevent PEER_ID_INVALID on ephemeral hosts
    try:
        from database import db
        async def cache_channels():
            # Dumb Channels
            links = await db.get_all_dumb_channel_links()
            for link in links:
                try:
                    # Using get_chat with an invite link caches the peer in the session
                    # Note: Telegram Bots cannot use CheckChatInvite for private channels.
                    # If links are public (@username), it works. If private (+hash), it raises BOT_METHOD_INVALID.
                    # We will catch this, but it's safe to ignore since the bot might already know it.
                    await app.get_chat(link)
                except Exception as e:
                    # Log as debug so we don't spam warnings on valid setups where the bot just can't use the link
                    pass

        logger.info("Caching Channel peers...")
        app.loop.run_until_complete(cache_channels())
    except Exception as e:
        logger.warning(f"Error during Channel caching: {e}")

    # Fetch Userbot session from Database
    try:
        from database import db
        async def get_userbot_session():
            return await db.get_pro_session()
        pro_data = app.loop.run_until_complete(get_userbot_session())

        if pro_data and pro_data.get("session_string"):
            logger.info("𝕏TV Pro™ Session detected in database. Initializing Premium Userbot...")
            user_bot = Client(
                "xtv_user_bot",
                api_id=pro_data.get("api_id", Config.API_ID),
                api_hash=pro_data.get("api_hash", Config.API_HASH),
                session_string=pro_data.get("session_string"),
                workers=50,
                max_concurrent_transmissions=10
            )
            app.user_bot = user_bot

            logger.info("Starting 𝕏TV Pro™ Premium Userbot...")
            user_bot.start()
            logger.info("𝕏TV Pro™ Premium Userbot Started Successfully!")

            # To prevent PEER_ID_INVALID on the Main Bot when copying files into the private tunnel,
            # the Userbot (which is immune to bot limitations) must send a message to the tunnel,
            # forcing Telegram to sync the channel's peer info back to the Main Bot instantly.
            tunnel_id = pro_data.get("tunnel_id")
            if tunnel_id:
                try:
                    logger.info(f"Pinging Pro Tunnel ({tunnel_id}) to synchronize peer data...")
                    # Send a silent ping and delete it immediately
                    msg = app.loop.run_until_complete(user_bot.send_message(tunnel_id, "ping", disable_notification=True))
                    app.loop.run_until_complete(user_bot.delete_messages(tunnel_id, msg.id))
                    logger.info("Tunnel Peer successfully cached for Main Bot!")
                except Exception as e:
                    logger.warning(f"Could not ping Pro Tunnel on startup (this is okay if the tunnel is already cached): {e}")

        else:
            app.user_bot = None
            logger.warning("No 𝕏TV Pro™ Session found in database. 4GB upload support is DISABLED.")
    except Exception as e:
        logger.error(f"Failed to initialize Userbot from DB: {e}")
        app.user_bot = None

    # Background Task for Auto-Cleanup of the Pro Tunnel Channel
    async def cleanup_tunnel():
        import asyncio
        from datetime import datetime, timedelta, timezone

        while True:
            try:
                # Run once a day
                await asyncio.sleep(86400)

                pro_session = await db.get_pro_session()
                tunnel_id = pro_session.get("tunnel_id") if pro_session else None

                if tunnel_id and app.user_bot:
                    logger.info("Running scheduled cleanup for Pro Tunnel Channel...")
                    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)

                    messages_to_delete = []
                    async for msg in app.user_bot.get_chat_history(tunnel_id):
                        if msg.date < two_days_ago:
                            messages_to_delete.append(msg.id)

                        # Delete in batches of 100 (Telegram limit)
                        if len(messages_to_delete) >= 100:
                            await app.user_bot.delete_messages(tunnel_id, messages_to_delete)
                            messages_to_delete = []
                            await asyncio.sleep(1)

                    if messages_to_delete:
                        await app.user_bot.delete_messages(tunnel_id, messages_to_delete)

                    logger.info("Scheduled cleanup for Pro Tunnel Channel complete.")
            except Exception as e:
                logger.error(f"Error during Tunnel cleanup task: {e}")

    if app.user_bot:
        app.loop.create_task(cleanup_tunnel())

    logger.info("Bot Started!")
    idle()

    if user_bot:
        try:
            user_bot.stop()
        except:
            pass

    app.stop()
