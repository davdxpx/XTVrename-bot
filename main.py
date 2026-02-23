from pyrogram import Client, idle
from config import Config
from utils.log import get_logger

# Configure logging
logger = get_logger("main")

# Initialize Bot
app = Client(
    "xtv_rename_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    plugins=dict(root="plugins")
)

# Initialize Userbot (for >2GB support)
user_bot = None
if Config.USER_SESSION:
    logger.info("USER_SESSION detected. Initializing Premium Userbot...")
    user_bot = Client(
        "xtv_user_bot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        session_string=Config.USER_SESSION
    )
    app.user_bot = user_bot # Attach to main app for easy access in plugins
else:
    app.user_bot = None
    logger.warning("No USER_SESSION found. 4GB upload support is DISABLED.")

if __name__ == "__main__":
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        exit(1)

    logger.info("Starting XTV Rename Bot...")
    app.start()

    if user_bot:
        logger.info("Starting Premium Userbot...")
        try:
            user_bot.start()
            logger.info("Userbot Started Successfully!")
        except Exception as e:
            logger.error(f"Failed to start Userbot: {e}")
            app.user_bot = None # Disable if failed

    logger.info("Bot Started!")
    idle()

    if user_bot:
        try:
            user_bot.stop()
        except:
            pass

    app.stop()
