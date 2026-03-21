import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    VERSION = "v1.3.1"
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH")

    MAIN_URI = os.getenv("MAIN_URI")
    DB_NAME = "MainDB"
    SETTINGS_COLLECTION = "rename_bot_settings"

    CEO_ID = int(os.getenv("CEO_ID", 0))
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

    PUBLIC_MODE = os.getenv("PUBLIC_MODE", "False").lower() == "true"
    DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() in ("true", "1", "yes")

    TMDB_API_KEY = os.getenv("TMDB_API_KEY")

    DOWNLOAD_DIR = "downloads/"
    THUMB_PATH = "downloads/thumb.jpg"

    DEFAULT_TEMPLATES = {
        "title": "@XTVglobal - {title} {season_episode}",
        "author": "@XTVglobal",
        "artist": "By:- @XTVglobal",
        "video": "Encoded By:- @XTVglobal",
        "audio": "Audio By:- @XTVglobal - {lang}",
        "subtitle": "Subtitled By:- @XTVglobal - {lang}",
    }

    DEFAULT_FILENAME_TEMPLATES = {
        "movies": "{Title}.{Year}.{Quality}_[{Channel}]",
        "series": "{Title}.{Season_Episode}.{Quality}_[{Channel}]",
        "subtitles_movies": "{Title}.{Year}_[{Channel}]",
        "subtitles_series": "{Title}.{Season_Episode}.{Language}",
        "personal_video": "{Title} {Year} [{Channel}]",
        "personal_photo": "{Title} {Year} [{Channel}]",
        "personal_file": "{Title} {Year} [{Channel}]",
    }

    DEFAULT_CHANNEL = "@XTVglobal"


if not os.path.exists(Config.DOWNLOAD_DIR):
    os.makedirs(Config.DOWNLOAD_DIR)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
