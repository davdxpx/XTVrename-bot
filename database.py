# --- Imports ---
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
from utils.log import get_logger
import ssl
import certifi

logger = get_logger("database")

# === Classes ===
class Database:
    def __init__(self):
        if not Config.MAIN_URI:
            logger.warning("MAIN_URI is not set in environment variables.")
            self.client = None
            self.db = None
            self.settings = None
            self.users = None
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
            self.settings = self.db["user_settings"]
            self.users = self.db["users"]
            self.daily_stats = self.db["daily_stats"]

    def _get_doc_id(self, user_id=None):
        if Config.PUBLIC_MODE and user_id is not None:
            return f"user_{user_id}"
        return "global_settings"

    async def migrate_old_db_to_new(self):
        if self.db is None: return

        global_doc = await self.settings.find_one({"_id": "global_settings"})
        if global_doc and global_doc.get("migration_to_users_done"):
            return

        old_settings = self.db["rename_bot_settings"]
        count = await old_settings.count_documents({})
        if count == 0:
            await self.settings.update_one({"_id": "global_settings"}, {"$set": {"migration_to_users_done": True}}, upsert=True)
            return

        logger.info("Migrating old rename_bot_settings to user_settings and users collections...")

        async for doc in old_settings.find({}):
            doc_id = doc.get("_id")

            if doc_id in ["global_settings", "xtv_pro_settings", "public_mode_config"]:
                await self.settings.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)
                continue

            if isinstance(doc_id, str) and doc_id.startswith("user_"):
                try:
                    user_id = int(doc_id.replace("user_", ""))
                except ValueError:
                    continue

                await self.settings.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)

                user_doc = await self.users.find_one({"user_id": user_id})
                import time
                now = time.time()
                if not user_doc:
                    new_user = {
                        "user_id": user_id,
                        "updated_at": now,
                        "first_name": "Unknown",
                        "username": None,
                        "banned": False,
                        "is_premium": False,
                        "premium_plan": "standard",
                        "premium_expiry": None,
                        "trial_claimed": False,
                        "joined_at": now,
                        "history": [],
                        "referral_count": 0,
                    }
                    await self.users.insert_one(new_user)
                else:
                    if user_doc.get("is_premium") and "premium_plan" not in user_doc:
                        await self.users.update_one({"user_id": user_id}, {"$set": {"premium_plan": "standard"}})

        await self.settings.update_one({"_id": "global_settings"}, {"$set": {"migration_to_users_done": True}}, upsert=True)
        logger.info("Migration completed.")

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
                    "preferred_language": "en-US",
                    "preferred_separator": ".",
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

    async def get_preferred_language(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("preferred_language", "en-US")
        return "en-US"

    async def update_preferred_language(self, value, user_id=None):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id}, {"$set": {"preferred_language": value}}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating preferred language for {doc_id}: {e}")

    async def get_preferred_separator(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("preferred_separator", ".")
        return "."

    async def update_preferred_separator(self, value, user_id=None):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id}, {"$set": {"preferred_separator": value}}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating preferred separator for {doc_id}: {e}")

    async def get_workflow_mode(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("workflow_mode", "smart_media_mode")
        return "smart_media_mode"

    async def update_workflow_mode(self, mode: str, user_id=None):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id}, {"$set": {"workflow_mode": mode}}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating workflow mode for {doc_id}: {e}")

    async def has_completed_setup(self, user_id=None):
        settings = await self.get_settings(user_id)
        if settings:
            return settings.get("setup_completed", False)
        return False

    async def mark_setup_completed(self, user_id=None, completed: bool = True):
        if self.settings is None:
            return
        doc_id = self._get_doc_id(user_id)
        try:
            await self.settings.update_one(
                {"_id": doc_id}, {"$set": {"setup_completed": completed}}, upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating setup_completed for {doc_id}: {e}")

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
                    "bot_name": "𝕏TV Rename Bot",
                    "community_name": "Our Community",
                    "support_contact": "@davdxpx",
                    "force_sub_channel": None,
                    "force_sub_link": None,
                    "force_sub_username": None,
                    "force_sub_banner_file_id": None,
                    "force_sub_message_text": None,
                    "force_sub_button_label": None,
                    "force_sub_button_emoji": None,
                    "force_sub_channels": [],
                    "force_sub_welcome_text": None,
                    "daily_egress_mb": 0,
                    "daily_file_count": 0,
                    "global_daily_egress_mb": 0,
                    "premium_system_enabled": False,
                    "premium_trial_enabled": False,
                    "premium_trial_days": 1,
                    "premium_deluxe_enabled": False,
                    "currency_conversion_enabled": True,
                    "base_currency": "USD",
                    "stars_payment_enabled": False,
                    "xtv_pro_4gb_access": "all",
                    "premium_standard": {
                        "daily_egress_mb": 0,
                        "daily_file_count": 0,
                        "price_string": "0 USD",
                        "stars_price": 0,
                        "features": {
                            "priority_queue": False,
                            "xtv_pro_4gb": False,
                            "file_converter": True,
                            "audio_editor": True,
                            "watermarker": True,
                            "subtitle_extractor": True,
                        }
                    },
                    "premium_deluxe": {
                        "daily_egress_mb": 0,
                        "daily_file_count": 0,
                        "price_string": "0 USD",
                        "stars_price": 0,
                        "features": {
                            "priority_queue": True,
                            "xtv_pro_4gb": True,
                            "file_converter": True,
                            "audio_editor": True,
                            "watermarker": True,
                            "subtitle_extractor": True,
                        }
                    }
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

    async def get_global_daily_egress_limit(self) -> float:
        if self.settings is None:
            return 0.0

        if Config.PUBLIC_MODE:
            config = await self.get_public_config()
            return float(config.get("global_daily_egress_mb", 0))
        else:
            doc = await self.settings.find_one({"_id": "global_settings"})
            if doc:
                return float(doc.get("global_daily_egress_mb", 0))
            return 0.0

    async def update_global_daily_egress_limit(self, limit_mb: float):
        if self.settings is None:
            return
        try:
            if Config.PUBLIC_MODE:
                await self.update_public_config("global_daily_egress_mb", limit_mb)
            else:
                await self.settings.update_one(
                    {"_id": "global_settings"},
                    {"$set": {"global_daily_egress_mb": limit_mb}},
                    upsert=True,
                )
        except Exception as e:
            logger.error(f"Error updating global daily egress limit: {e}")

    async def get_feature_toggles(self):
        if self.settings is None:
            return {}
        try:
            if Config.PUBLIC_MODE:
                config = await self.get_public_config()
                return config.get("feature_toggles", {})
            else:
                doc = await self.settings.find_one({"_id": "global_settings"})
                if doc:
                    return doc.get("feature_toggles", {})
                return {}
        except Exception as e:
            logger.error(f"Error fetching feature toggles: {e}")
            return {}

    async def update_feature_toggle(self, feature_name: str, enabled: bool):
        if self.settings is None:
            return
        try:
            if Config.PUBLIC_MODE:
                await self.settings.update_one(
                    {"_id": "public_mode_config"},
                    {"$set": {f"feature_toggles.{feature_name}": enabled}},
                    upsert=True
                )
            else:
                await self.settings.update_one(
                    {"_id": "global_settings"},
                    {"$set": {f"feature_toggles.{feature_name}": enabled}},
                    upsert=True
                )
        except Exception as e:
            logger.error(f"Error updating feature toggle: {e}")

    async def get_user_usage(self, user_id: int) -> dict:
        if self.settings is None:
            return {}
        try:
            doc = await self.settings.find_one({"_id": f"user_{user_id}"})
            if not doc:
                return {}
            return doc.get("usage", {})
        except Exception as e:
            logger.error(f"Error fetching usage for user {user_id}: {e}")
            return {}

    async def get_global_usage_today(self) -> float:
        if self.settings is None:
            return 0.0

        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        try:
            doc = await self.daily_stats.find_one({"date": current_utc_date})
            if doc:
                return float(doc.get("egress_mb", 0.0)) + float(doc.get("reserved_egress_mb", 0.0))
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching global usage: {e}")
            return 0.0

    async def check_daily_quota(self, user_id: int, file_size_bytes: int) -> tuple[bool, str, dict]:
        if self.settings is None:
            return True, "", {}

        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        incoming_mb = file_size_bytes / (1024 * 1024)

        global_limit_mb = await self.get_global_daily_egress_limit()
        if global_limit_mb > 0:
            current_global_usage = await self.get_global_usage_today()
            if current_global_usage + incoming_mb > global_limit_mb:
                mb_limit_str = f"{global_limit_mb} MB"
                if global_limit_mb >= 1024:
                    mb_limit_str = f"{global_limit_mb / 1024:.2f} GB"

                return False, f"Global Bot Usage Limit reached for today ({mb_limit_str}). Please try again tomorrow.", {}

        if user_id == Config.CEO_ID or user_id in Config.ADMIN_IDS:
            return True, "", {}

        if not Config.PUBLIC_MODE:
            return True, "", {}

        config = await self.get_public_config()
        daily_egress_mb_limit = config.get("daily_egress_mb", 0)
        daily_file_count_limit = config.get("daily_file_count", 0)

        import time
        now = time.time()

        user_doc = await self.get_user(user_id)
        is_premium = False
        premium_plan = "standard"
        if user_doc:
            exp = user_doc.get("premium_expiry")
            if user_doc.get("is_premium") and (exp is None or exp > now):
                is_premium = True
                premium_plan = user_doc.get("premium_plan", "standard")

        premium_system_enabled = config.get("premium_system_enabled", False)

        if is_premium and premium_system_enabled:
            if premium_plan == "deluxe" and config.get("premium_deluxe_enabled", False):
                plan_settings = config.get("premium_deluxe", {})
            else:
                plan_settings = config.get("premium_standard", {})
            daily_egress_mb_limit = plan_settings.get("daily_egress_mb", 0)
            daily_file_count_limit = plan_settings.get("daily_file_count", 0)

        if daily_egress_mb_limit <= 0 and daily_file_count_limit <= 0:
            return True, "", {}

        try:
            doc = await self.settings.find_one({"_id": f"user_{user_id}"})
            usage = doc.get("usage", {}) if doc else {}

            if usage.get("date") != current_utc_date:
                usage["date"] = current_utc_date
                usage["egress_mb"] = 0.0
                usage["reserved_egress_mb"] = 0.0
                usage["file_count"] = 0
                usage["quota_hits"] = 0

                if "egress_mb_alltime" not in usage:
                    usage["egress_mb_alltime"] = 0.0
                if "file_count_alltime" not in usage:
                    usage["file_count_alltime"] = 0

                await self.settings.update_one(
                    {"_id": f"user_{user_id}"},
                    {"$set": {"usage": usage}},
                    upsert=True
                )

            current_utc = datetime.datetime.utcnow()
            tomorrow = current_utc + datetime.timedelta(days=1)
            midnight = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day)
            time_to_midnight = midnight - current_utc
            hours, remainder = divmod(int(time_to_midnight.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            reset_str = f"Resets at midnight UTC — roughly {hours}h {minutes}m from now."

            if daily_file_count_limit > 0 and usage.get("file_count", 0) >= daily_file_count_limit:
                await self.record_quota_hit(user_id)
                return False, f"You've reached your daily {daily_file_count_limit} file limit. {reset_str}", usage

            current_user_egress = usage.get("egress_mb", 0.0) + usage.get("reserved_egress_mb", 0.0)
            if daily_egress_mb_limit > 0 and (current_user_egress + incoming_mb) > daily_egress_mb_limit:
                await self.record_quota_hit(user_id)
                mb_limit_str = f"{daily_egress_mb_limit} MB"
                if daily_egress_mb_limit >= 1024:
                    mb_limit_str = f"{daily_egress_mb_limit / 1024:.2f} GB"
                return False, f"You've reached your daily {mb_limit_str} egress limit. {reset_str}", usage

            return True, "", usage

        except Exception as e:
            logger.error(f"Error checking daily quota for {user_id}: {e}")
            return True, "", {}

    async def reserve_quota(self, user_id: int, file_size_bytes: int):
        if self.settings is None:
            return

        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        incoming_mb = file_size_bytes / (1024 * 1024)

        try:

            await self.daily_stats.update_one(
                {"date": current_utc_date},
                {"$inc": {"reserved_egress_mb": incoming_mb}},
                upsert=True
            )

            user_doc = await self.settings.find_one({"_id": f"user_{user_id}"})
            usage = user_doc.get("usage", {}) if user_doc else {}

            if usage.get("date") != current_utc_date:
                await self.settings.update_one(
                    {"_id": f"user_{user_id}"},
                    {"$set": {
                        "usage.date": current_utc_date,
                        "usage.egress_mb": 0.0,
                        "usage.reserved_egress_mb": incoming_mb,
                        "usage.file_count": 0,
                        "usage.quota_hits": 0
                    }},
                    upsert=True
                )
            else:
                await self.settings.update_one(
                    {"_id": f"user_{user_id}"},
                    {"$inc": {"usage.reserved_egress_mb": incoming_mb}},
                    upsert=True
                )
        except Exception as e:
            logger.error(f"Error reserving quota: {e}")

    async def release_quota(self, user_id: int, file_size_bytes: int):
        if self.settings is None:
            return

        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        incoming_mb = file_size_bytes / (1024 * 1024)

        try:

            await self.daily_stats.update_one(
                {"date": current_utc_date},
                {"$inc": {"reserved_egress_mb": -incoming_mb}},
                upsert=True
            )

            await self.settings.update_one(
                {"_id": f"user_{user_id}"},
                {"$inc": {"usage.reserved_egress_mb": -incoming_mb}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error releasing quota: {e}")

    async def record_quota_hit(self, user_id: int):
        if self.settings is None:
            return

        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        try:

            await self.settings.update_one(
                {"_id": f"user_{user_id}"},
                {"$inc": {"usage.quota_hits": 1}},
                upsert=True
            )

            await self.daily_stats.update_one(
                {"date": current_utc_date},
                {"$inc": {"quota_hits": 1}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error recording quota hit: {e}")

    async def update_usage(self, user_id: int, processed_file_size_bytes: int, reserved_file_size_bytes: int = 0):
        if self.settings is None:
            return

        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        processed_mb = processed_file_size_bytes / (1024 * 1024)
        reserved_mb = reserved_file_size_bytes / (1024 * 1024)

        try:

            user_doc = await self.settings.find_one({"_id": f"user_{user_id}"})
            usage = user_doc.get("usage", {}) if user_doc else {}

            if usage.get("date") != current_utc_date:
                await self.settings.update_one(
                    {"_id": f"user_{user_id}"},
                    {"$set": {
                        "usage.date": current_utc_date,
                        "usage.egress_mb": 0.0,
                        "usage.reserved_egress_mb": 0.0,
                        "usage.file_count": 0,
                        "usage.quota_hits": 0
                    }},
                    upsert=True
                )

            await self.settings.update_one(
                {"_id": f"user_{user_id}"},
                {"$inc": {
                    "usage.egress_mb": processed_mb,
                    "usage.reserved_egress_mb": -reserved_mb,
                    "usage.file_count": 1,
                    "usage.egress_mb_alltime": processed_mb,
                    "usage.file_count_alltime": 1
                }},
                upsert=True
            )

            await self.daily_stats.update_one(
                {"date": current_utc_date},
                {"$inc": {
                    "egress_mb": processed_mb,
                    "reserved_egress_mb": -reserved_mb,
                    "file_count": 1
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating usage: {e}")

    async def get_daily_stats(self, limit=7):
        if self.settings is None:
            return []
        try:
            cursor = self.daily_stats.find({}).sort("date", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error fetching daily stats: {e}")
            return []

    async def get_top_users_today(self, limit=10, skip=0):
        if self.settings is None:
            return [], 0

        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        try:
            query = {
                "_id": {"$regex": "^user_"},
                "usage.date": current_utc_date,
                "usage.egress_mb": {"$gt": 0}
            }

            cursor = self.settings.find(query).sort("usage.egress_mb", -1).skip(skip).limit(limit)
            users = await cursor.to_list(length=limit)
            total = await self.settings.count_documents(query)

            return users, total
        except Exception as e:
            logger.error(f"Error fetching top users: {e}")
            return [], 0

    async def get_total_users(self):
        if self.settings is None:
            return 0
        try:
            return await self.settings.count_documents({"_id": {"$regex": "^user_"}})
        except Exception as e:
            return 0

    async def get_dashboard_stats(self):
        if self.settings is None:
            return {}

        import datetime
        current_utc_date = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        try:

            today_stats = await self.daily_stats.find_one({"date": current_utc_date}) or {}

            all_time_pipeline = [
                {"$group": {
                    "_id": None,
                    "total_egress": {"$sum": "$egress_mb"},
                    "total_files": {"$sum": "$file_count"}
                }}
            ]
            all_time_result = await self.daily_stats.aggregate(all_time_pipeline).to_list(1)
            all_time = all_time_result[0] if all_time_result else {"total_egress": 0, "total_files": 0}

            total_users = await self.get_total_users()

            public_config = await self.get_public_config()
            blocked_users = len(public_config.get("blocked_users", []))

            first_stat = await self.daily_stats.find_one({}, sort=[("date", 1)])
            bot_start_date = first_stat["date"] if first_stat else current_utc_date

            return {
                "total_users": total_users,
                "files_today": today_stats.get("file_count", 0),
                "egress_today_mb": today_stats.get("egress_mb", 0.0),
                "quota_hits_today": today_stats.get("quota_hits", 0),
                "total_files": all_time.get("total_files", 0),
                "total_egress_mb": all_time.get("total_egress", 0.0),
                "blocked_users": blocked_users,
                "bot_start_date": bot_start_date
            }
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return {}

    async def block_user(self, user_id: int):
        if self.settings is None:
            return
        try:
            await self.settings.update_one(
                {"_id": "public_mode_config"},
                {"$addToSet": {"blocked_users": user_id}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error blocking user: {e}")

    async def unblock_user(self, user_id: int):
        if self.settings is None:
            return
        try:
            await self.settings.update_one(
                {"_id": "public_mode_config"},
                {"$pull": {"blocked_users": user_id}}
            )
        except Exception as e:
            logger.error(f"Error unblocking user: {e}")

    async def is_user_blocked(self, user_id: int) -> bool:
        if self.settings is None:
            return False
        try:
            config = await self.get_public_config()
            return user_id in config.get("blocked_users", [])
        except Exception as e:
            return False

    async def reset_user_quota(self, user_id: int):
        if self.settings is None:
            return
        try:
            await self.settings.update_one(
                {"_id": f"user_{user_id}"},
                {"$set": {
                    "usage.egress_mb": 0.0,
                    "usage.file_count": 0,
                    "usage.quota_hits": 0
                }}
            )
        except Exception as e:
            logger.error(f"Error resetting user quota: {e}")

    async def get_all_users(self):
        if self.settings is None:
            return []
        users = []
        try:
            async for doc in self.settings.find({"_id": {"$regex": "^user_"}}):
                user_id_str = str(doc["_id"]).replace("user_", "")
                if user_id_str.isdigit():
                    users.append(int(user_id_str))
        except Exception as e:
            logger.error(f"Error fetching all users: {e}")
        return users

    async def ensure_user(self, user_id: int, first_name: str, username: str = None, last_name: str = None, language_code: str = None, is_bot: bool = False):
        if self.users is None:
            return
        import time
        now = time.time()

        user_doc = await self.users.find_one({"user_id": user_id})

        if not user_doc:
            new_user = {
                "user_id": user_id,
                "first_name": first_name,
                "last_name": last_name,
                "username": username,
                "language_code": language_code,
                "is_bot": is_bot,
                "banned": False,
                "is_premium": False,
                "premium_plan": "standard",
                "premium_expiry": None,
                "trial_claimed": False,
                "joined_at": now,
                "updated_at": now,
                "last_active": now,
                "history": [],
                "referral_count": 0,
            }
            await self.users.insert_one(new_user)
        else:
            update_fields = {
                "first_name": first_name,
                "last_name": last_name,
                "username": username,
                "language_code": language_code,
                "is_bot": is_bot,
                "updated_at": now,
                "last_active": now
            }

            if "banned" not in user_doc:
                update_fields["banned"] = False
            if "is_premium" not in user_doc:
                update_fields["is_premium"] = False
            if "premium_plan" not in user_doc:
                update_fields["premium_plan"] = "standard"
            if "premium_expiry" not in user_doc:
                update_fields["premium_expiry"] = None
            if "trial_claimed" not in user_doc:
                update_fields["trial_claimed"] = False
            if "joined_at" not in user_doc:
                update_fields["joined_at"] = now
            if "history" not in user_doc:
                update_fields["history"] = []
            if "referral_count" not in user_doc:
                update_fields["referral_count"] = 0

            await self.users.update_one(
                {"user_id": user_id},
                {"$set": update_fields}
            )

    async def get_user(self, user_id: int):
        if self.users is None:
            return None
        return await self.users.find_one({"user_id": user_id})

    async def get_users_paginated(self, filter_dict: dict, skip: int, limit: int, sort_by: str = "joined_at"):
        if self.users is None:
            return []
        sort_order = -1 if sort_by in ["joined_at", "updated_at"] else 1
        cursor = self.users.find(filter_dict).sort(sort_by, sort_order).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def count_users(self, filter_dict: dict):
        if self.users is None:
            return 0
        return await self.users.count_documents(filter_dict)

    async def search_users(self, query: str, limit: int = 10):
        if self.users is None:
            return []
        filter_dict = {}
        if query.isdigit():
            filter_dict = {"user_id": int(query)}
        else:
            filter_dict = {
                "$or": [
                    {"username": {"$regex": query, "$options": "i"}},
                    {"first_name": {"$regex": query, "$options": "i"}},
                ]
            }
        cursor = self.users.find(filter_dict).limit(limit)
        return await cursor.to_list(length=limit)

    async def add_premium_user(self, user_id: int, days: float, plan: str = "standard"):
        if self.users is None:
            return
        import time
        now = time.time()

        user_doc = await self.get_user(user_id)
        if not user_doc:
            return

        current_exp = user_doc.get("premium_expiry", 0)
        current_plan = user_doc.get("premium_plan", "standard")
        if current_exp and current_exp > now and current_plan == plan:
            new_exp = current_exp + (days * 86400)
        else:
            new_exp = now + (days * 86400)

        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "is_premium": True,
                "premium_plan": plan,
                "premium_expiry": new_exp
            }}
        )

    async def reset_user_premium(self, user_id: int):
        if self.users is None:
            return
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "is_premium": False,
                "premium_plan": "standard",
                "premium_expiry": None
            }}
        )

    async def delete_user_data(self, user_id: int):
        if self.users is None or self.settings is None:
            return
        await self.users.delete_one({"user_id": user_id})
        await self.settings.delete_one({"_id": f"user_{user_id}"})

    async def add_log(self, action: str, admin_id: int, description: str):

        logger.info(f"ADMIN_LOG [{action}] by {admin_id}: {description}")

db = Database()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
