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

    def _get_doc_id(self, user_id=None):
        if Config.PUBLIC_MODE and user_id is not None:
            return f"user_{user_id}"
        return "global_settings"

    async def get_settings(self, user_id=None):
        if self.settings is None:
            return None

        doc_id = self._get_doc_id(user_id)
        try:
            doc = await self.settings.find_one({"_id": doc_id})
            if not doc:
                default_settings = {
                    "_id": doc_id,
                    "thumbnail_file_id": None,
                    "thumbnail_binary": None,
                    "templates": Config.DEFAULT_TEMPLATES,
                    "filename_templates": Config.DEFAULT_FILENAME_TEMPLATES,
                    "channel": Config.DEFAULT_CHANNEL
                }
                await self.settings.insert_one(default_settings)
                return default_settings
            return doc
        except Exception as e:
            logger.error(f"Error fetching settings for {doc_id}: {e}")
            return None

    async def update_template(self, key, value, user_id=None):
        if self.settings is None: return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id},
                {"$set": {f"templates.{key}": value}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating template for {doc_id}: {e}")

    async def update_thumbnail(self, file_id, binary_data, user_id=None):
        if self.settings is None: return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id},
                {"$set": {"thumbnail_file_id": file_id, "thumbnail_binary": binary_data}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating thumbnail for {doc_id}: {e}")

    async def get_thumbnail(self, user_id=None):
        if self.settings is None: return None, None
        doc_id = self._get_doc_id(user_id)
        try:
            doc = await self.settings.find_one({"_id": doc_id})
            if doc:
                return doc.get("thumbnail_binary"), doc.get("thumbnail_file_id")
        except Exception as e:
            logger.error(f"Error fetching thumbnail for {doc_id}: {e}")
        return None, None

    async def get_all_templates(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("templates", Config.DEFAULT_TEMPLATES)
        return Config.DEFAULT_TEMPLATES

    async def get_filename_templates(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("filename_templates", Config.DEFAULT_FILENAME_TEMPLATES)
        return Config.DEFAULT_FILENAME_TEMPLATES

    async def update_filename_template(self, key, value, user_id=None):
        if self.settings is None: return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id},
                {"$set": {f"filename_templates.{key}": value}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating filename template for {doc_id}: {e}")

    async def get_channel(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("channel", Config.DEFAULT_CHANNEL)
        return Config.DEFAULT_CHANNEL

    async def update_channel(self, value, user_id=None):
        if self.settings is None: return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id},
                {"$set": {"channel": value}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating channel for {doc_id}: {e}")

    # --- PUBLIC_MODE Global Configs ---
    async def get_public_config(self):
        """Fetch the global public mode configuration set by the CEO."""
        if self.settings is None:
            return {}
        try:
            doc = await self.settings.find_one({"_id": "public_mode_config"})
            if not doc:
                default_config = {
                    "_id": "public_mode_config",
                    "bot_name": "XTV Rename Bot",
                    "community_name": "Our Community",
                    "support_contact": "@davdxpx",
                    "force_sub_channel": None,
                    "force_sub_link": None,
                    "rate_limit_delay": 0  # 0 means disabled
                }
                await self.settings.insert_one(default_config)
                return default_config
            return doc
        except Exception as e:
            logger.error(f"Error fetching public config: {e}")
            return {}

    async def update_public_config(self, key, value):
        if self.settings is None: return
        try:
            await self.settings.update_one(
                {"_id": "public_mode_config"},
                {"$set": {key: value}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating public config: {e}")

    async def check_rate_limit(self, user_id: int) -> bool:
        """Check if a user is currently rate limited."""
        if self.settings is None: return True
        config = await self.get_public_config()
        delay = config.get("rate_limit_delay", 0)

        if delay <= 0:
            return True

        try:
            user_doc = await self.settings.find_one({"_id": f"user_{user_id}"})
            if not user_doc:
                return True

            last_used = user_doc.get("last_used", 0)
            import time
            if time.time() - last_used < delay:
                return False

            return True
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return True

    async def update_rate_limit(self, user_id: int):
        """Update the last used timestamp for a user."""
        if self.settings is None: return
        import time
        try:
            await self.settings.update_one(
                {"_id": f"user_{user_id}"},
                {"$set": {"last_used": time.time()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating rate limit: {e}")

db = Database()
