import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH")

    # User Session (for 4GB uploads)
    USER_SESSION = os.getenv("USER_SESSION")

    # MongoDB
    MAIN_URI = os.getenv("MAIN_URI")
    DB_NAME = "MainDB"  # The main database name
    SETTINGS_COLLECTION = "rename_bot_settings"

    # Access Control
    CEO_ID = int(os.getenv("CEO_ID", 0))
    FRANCHISEE_IDS = [int(x) for x in os.getenv("FRANCHISEE_IDS", "").split(",") if x.strip()]

    # TMDb
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")

    # Paths
    DOWNLOAD_DIR = "downloads/"
    THUMB_PATH = "downloads/thumb.jpg"  # Default location for temporary thumbnails

    # Default Templates (Fallback if DB is empty)
    DEFAULT_TEMPLATES = {
        "title": "@XTVglobal - {title} {season_episode}",
        "author": "@XTVglobal",
        "artist": "By:- @XTVglobal",
        "video": "Encoded By:- @XTVglobal",
        "audio": "Audio By:- @XTVglobal - {lang}",
        "subtitle": "Subtitled By:- @XTVglobal - {lang}"
    }

    # Default Filename Templates
    DEFAULT_FILENAME_TEMPLATES = {
        "movies": "{Title}.{Year}.{Quality}_[{Channel}]",
        "series": "{Title}.{Season_Episode}.{Quality}_[{Channel}]",
        "subtitles_movies": "{Title}.{Year}_[{Channel}]",
        "subtitles_series": "{Title}.{Season_Episode}.{Language}",
        "personal_video": "{Title} {Year} [{Channel}]",
        "personal_photo": "{Title} {Year} [{Channel}]",
        "personal_file": "{Title} {Year} [{Channel}]"
    }

    # Default Channel
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
