from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
from utils.log import get_logger
import ssl
import certifi

logger = get_logger("database")

class Database:
    def __init__(self):
        if not Config.MAIN_URI:
            logger.warning("MAIN_URI is not set in environment variables.")
            self.client = None
            self.db = None
            self.settings = None
        else:
            # Fix SSL Handshake Error
            try:
                self.client = AsyncIOMotorClient(
                    Config.MAIN_URI,
                    tlsCAFile=certifi.where()
                )
            except Exception as e:
                logger.warning(f"Failed to connect with certifi, trying with tlsAllowInvalidCertificates=True: {e}")
                self.client = AsyncIOMotorClient(
                    Config.MAIN_URI,
                    tlsAllowInvalidCertificates=True
                )

            self.db = self.client[Config.DB_NAME]
            self.settings = self.db[Config.SETTINGS_COLLECTION]

    async def get_settings(self):
        if self.settings is None:
            return None

        try:
            doc = await self.settings.find_one({"_id": "global_settings"})
            if not doc:
                default_settings = {
                    "_id": "global_settings",
                    "thumbnail_file_id": None,
                    "thumbnail_binary": None,
                    "templates": Config.DEFAULT_TEMPLATES
                }
                await self.settings.insert_one(default_settings)
                return default_settings
            return doc
        except Exception as e:
            logger.error(f"Error fetching settings: {e}")
            return None

    async def update_template(self, key, value):
        if self.settings is None: return
        try:
            await self.settings.update_one(
                {"_id": "global_settings"},
                {"$set": {f"templates.{key}": value}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating template: {e}")

    async def update_thumbnail(self, file_id, binary_data):
        if self.settings is None: return
        try:
            await self.settings.update_one(
                {"_id": "global_settings"},
                {"$set": {"thumbnail_file_id": file_id, "thumbnail_binary": binary_data}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating thumbnail: {e}")

    async def get_thumbnail(self):
        if self.settings is None: return None, None
        try:
            doc = await self.settings.find_one({"_id": "global_settings"})
            if doc:
                return doc.get("thumbnail_binary"), doc.get("thumbnail_file_id")
        except Exception as e:
            logger.error(f"Error fetching thumbnail: {e}")
        return None, None

    async def get_all_templates(self):
        settings = await self.get_settings()
        if settings:
            return settings.get("templates", Config.DEFAULT_TEMPLATES)
        return Config.DEFAULT_TEMPLATES

db = Database()
