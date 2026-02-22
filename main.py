from pyrogram import Client, idle
from config import Config
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# Initialize Bot
app = Client(
    "xtv_rename_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    plugins=dict(root="plugins")
)

if __name__ == "__main__":
    if not Config.BOT_TOKEN:
        logging.error("BOT_TOKEN is not set!")
        exit(1)

    logging.info("Starting XTV Rename Bot...")
    app.start()
    logging.info("Bot Started!")
    idle()
    app.stop()
