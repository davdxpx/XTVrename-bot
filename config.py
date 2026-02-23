"""
╔══════════════════════════════════════════════════════════════════════════╗
║                    Developed by 𝕏0L0™ (@davdxpx)                         ║
║     © 2024 XTV Network Global. All Rights Reserved.                      ║
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

if not os.path.exists(Config.DOWNLOAD_DIR):
    os.makedirs(Config.DOWNLOAD_DIR)
