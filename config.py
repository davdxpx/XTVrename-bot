import os
import time

from dotenv import load_dotenv

BOT_START_TIME = time.time()

load_dotenv()


class Config:
    VERSION = "v1.6.0"
    MYFILES_VERSION = "2.2"
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("API_ID", 0))
    API_HASH = os.getenv("API_HASH")

    MAIN_URI = os.getenv("MAIN_URI") # Dont put your variables in this file, put it into your .env file. 
    DB_NAME = "MainDB"
    SETTINGS_COLLECTION = "MediaStudio-Settings"

    CEO_ID = int(os.getenv("CEO_ID", 0))
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

    PUBLIC_MODE = os.getenv("PUBLIC_MODE", "False").lower() == "true"
    DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() in ("true", "1", "yes")

    TMDB_API_KEY = os.getenv("TMDB_API_KEY")

    # Fernet key for encrypting Mirror-Leech provider credentials at rest.
    # Required only when the mirror_leech feature toggle is on. Generate one via:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    SECRETS_KEY = os.getenv("SECRETS_KEY")

    DOWNLOAD_DIR = "downloads/"
    THUMB_PATH = "downloads/thumb.jpg"

    # Tenplates can be changed, in the Bot directly, or if you want also here.
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

    @classmethod
    def validate(cls):
        """Validate required configuration at startup.

        Note: TMDB_API_KEY is intentionally NOT validated here. It is
        optional as of the broaden-audience refactor — see utils.tmdb.gate
        for the availability check. Features that need it gracefully
        degrade with a friendly message; everything else keeps working.
        """
        errors = []
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is required (get one from @BotFather)")
        if not cls.API_ID:
            errors.append("API_ID is required (get one from my.telegram.org)")
        if not cls.API_HASH:
            errors.append("API_HASH is required (get one from my.telegram.org)")
        if not cls.MAIN_URI:
            errors.append("MAIN_URI is required (MongoDB connection string)")
        if errors:
            raise SystemExit(
                "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
            )


Config.validate()

if not os.path.exists(Config.DOWNLOAD_DIR):
    os.makedirs(Config.DOWNLOAD_DIR)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 𝕏TV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
