from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
import logging

class Database:
    def __init__(self):
        if not Config.MAIN_URI:
            logging.warning("MAIN_URI is not set in environment variables.")
            self.client = None
            self.db = None
            self.settings = None
        else:
            self.client = AsyncIOMotorClient(Config.MAIN_URI)
            self.db = self.client[Config.DB_NAME]
            self.settings = self.db[Config.SETTINGS_COLLECTION]

    async def get_settings(self):
        if not self.settings:
            return None

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

    async def update_template(self, key, value):
        if not self.settings: return
        await self.settings.update_one(
            {"_id": "global_settings"},
            {"$set": {f"templates.{key}": value}},
            upsert=True
        )

    async def update_thumbnail(self, file_id, binary_data):
        if not self.settings: return
        await self.settings.update_one(
            {"_id": "global_settings"},
            {"$set": {"thumbnail_file_id": file_id, "thumbnail_binary": binary_data}},
            upsert=True
        )

    async def get_thumbnail(self):
        if not self.settings: return None, None
        doc = await self.settings.find_one({"_id": "global_settings"})
        if doc:
            return doc.get("thumbnail_binary"), doc.get("thumbnail_file_id")
        return None, None

    async def get_all_templates(self):
        settings = await self.get_settings()
        if settings:
            return settings.get("templates", Config.DEFAULT_TEMPLATES)
        return Config.DEFAULT_TEMPLATES

db = Database()
