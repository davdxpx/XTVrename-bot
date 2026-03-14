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
            try:
                self.client = AsyncIOMotorClient(
                    Config.MAIN_URI, tlsCAFile=certifi.where()
                )
            except Exception as e:
                logger.warning(
                    f"Failed to connect with certifi, trying with tlsAllowInvalidCertificates=True: {e}"
                )
                self.client = AsyncIOMotorClient(
                    Config.MAIN_URI, tlsAllowInvalidCertificates=True
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
                    "channel": Config.DEFAULT_CHANNEL,
                }
                await self.settings.insert_one(default_settings)
                return default_settings
            return doc
        except Exception as e:
            logger.error(f"Error fetching settings for {doc_id}: {e}")
            return None

    async def update_template(self, key, value, user_id=None):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id}, {"$set": {f"templates.{key}": value}}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating template for {doc_id}: {e}")

    async def update_thumbnail(self, file_id, binary_data, user_id=None):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id},
                {
                    "$set": {
                        "thumbnail_file_id": file_id,
                        "thumbnail_binary": binary_data,
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Error updating thumbnail for {doc_id}: {e}")

    async def get_thumbnail(self, user_id=None):
        if self.settings is None:
            return None, None
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
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id},
                {"$set": {f"filename_templates.{key}": value}},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Error updating filename template for {doc_id}: {e}")

    async def get_channel(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("channel", Config.DEFAULT_CHANNEL)
        return Config.DEFAULT_CHANNEL

    async def update_channel(self, value, user_id=None):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id}, {"$set": {"channel": value}}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating channel for {doc_id}: {e}")

    async def get_dumb_channels(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("dumb_channels", {})
        return {}

    async def add_dumb_channel(
        self, channel_id, channel_name, invite_link=None, user_id=None
    ):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            update_data = {f"dumb_channels.{channel_id}": channel_name}
            if invite_link:
                update_data[f"dumb_channel_links.{channel_id}"] = invite_link

            await self.settings.update_one(
                {"_id": doc_id}, {"$set": update_data}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error adding dumb channel for {doc_id}: {e}")

    async def get_all_dumb_channel_links(self):
        if self.settings is None:
            return []
        links = set()
        async for doc in self.settings.find({"dumb_channel_links": {"$exists": True}}):
            for link in doc.get("dumb_channel_links", {}).values():
                if link:
                    links.add(link)
        return list(links)

    async def remove_dumb_channel(self, channel_id, user_id=None):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id},
                {"$unset": {f"dumb_channels.{channel_id}": ""}},
                upsert=True,
            )
            settings = await self.get_settings(user_id)
            if settings and settings.get("default_dumb_channel") == str(channel_id):
                await self.settings.update_one(
                    {"_id": doc_id},
                    {"$unset": {"default_dumb_channel": ""}},
                    upsert=True,
                )
        except Exception as e:
            logger.error(f"Error removing dumb channel for {doc_id}: {e}")

    async def get_default_dumb_channel(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("default_dumb_channel")
        return None

    async def set_default_dumb_channel(self, channel_id, user_id=None):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id},
                {"$set": {"default_dumb_channel": str(channel_id)}},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Error setting default dumb channel for {doc_id}: {e}")

    async def get_dumb_channel_timeout(self):
        if self.settings is None:
            return 3600
        if Config.PUBLIC_MODE:
            config = await self.get_public_config()
            return config.get("dumb_channel_timeout", 3600)
        else:
            doc = await self.settings.find_one({"_id": "global_settings"})
            if doc:
                return doc.get("dumb_channel_timeout", 3600)
            return 3600

    async def update_dumb_channel_timeout(self, timeout_seconds: int):
        if self.settings is None:
            return
        try:
            if Config.PUBLIC_MODE:
                await self.update_public_config("dumb_channel_timeout", timeout_seconds)
            else:
                await self.settings.update_one(
                    {"_id": "global_settings"},
                    {"$set": {"dumb_channel_timeout": timeout_seconds}},
                    upsert=True,
                )
        except Exception as e:
            logger.error(f"Error updating dumb channel timeout: {e}")

    async def get_pro_session(self):
        if self.settings is None:
            return None
        doc = await self.settings.find_one({"_id": "xtv_pro_settings"})
        if doc:
            return {
                "session_string": doc.get("session_string"),
                "api_id": doc.get("api_id"),
                "api_hash": doc.get("api_hash"),
                "tunnel_id": doc.get("tunnel_id"),
                "tunnel_link": doc.get("tunnel_link"),
            }
        return None

    async def save_pro_tunnel(self, tunnel_id: int, tunnel_link: str):
        if self.settings is None:
            return
        await self.settings.update_one(
            {"_id": "xtv_pro_settings"},
            {"$set": {"tunnel_id": tunnel_id, "tunnel_link": tunnel_link}},
            upsert=True,
        )

    async def save_pro_session(
        self, session_string: str, api_id: int = None, api_hash: str = None
    ):
        if self.settings is None:
            return
        update_doc = {"session_string": session_string}
        if api_id and api_hash:
            update_doc["api_id"] = api_id
            update_doc["api_hash"] = api_hash

        await self.settings.update_one(
            {"_id": "xtv_pro_settings"}, {"$set": update_doc}, upsert=True
        )

    async def delete_pro_session(self):
        if self.settings is None:
            return
        await self.settings.delete_one({"_id": "xtv_pro_settings"})

    async def get_public_config(self):
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
                    "rate_limit_delay": 0,
                }
                await self.settings.insert_one(default_config)
                return default_config
            return doc
        except Exception as e:
            logger.error(f"Error fetching public config: {e}")
            return {}

    async def update_public_config(self, key, value):
        if self.settings is None:
            return
        try:
            await self.settings.update_one(
                {"_id": "public_mode_config"}, {"$set": {key: value}}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating public config: {e}")

    async def check_rate_limit(self, user_id: int) -> bool:
        if self.settings is None:
            return True
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
        if self.settings is None:
            return
        import time

        try:
            await self.settings.update_one(
                {"_id": f"user_{user_id}"},
                {"$set": {"last_used": time.time()}},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Error updating rate limit: {e}")


db = Database()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
