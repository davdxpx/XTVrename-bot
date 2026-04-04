# --- Imports ---
import os
import time
import asyncio
import re
import random
import string
import logging
import shutil
import aiohttp
from typing import Optional, Dict, Tuple, Any

from pyrogram.errors import MessageNotModified
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import Message
from config import Config
from database import db
from utils.ffmpeg_tools import generate_ffmpeg_command, execute_ffmpeg, probe_file
from utils.progress import progress_for_pyrogram
import math
from utils.XTVengine import XTVEngine
from utils.queue_manager import queue_manager

logger = logging.getLogger("TaskProcessor")

_SEMAPHORES: Dict[int, Dict[str, Optional[asyncio.Semaphore]]] = {}

# === Helper Functions ===
def get_semaphore(user_id: int, phase: str, is_priority: bool = False) -> asyncio.Semaphore:
    if user_id not in _SEMAPHORES:
        _SEMAPHORES[user_id] = {"download": None, "process": None, "upload": None}

    if _SEMAPHORES[user_id][phase] is None:
        limit = 10 if is_priority else 3
        _SEMAPHORES[user_id][phase] = asyncio.Semaphore(limit)

    return _SEMAPHORES[user_id][phase]

# === Classes ===
class TaskProcessor:

    def __init__(self, client: Client, message: Message, data: Dict[str, Any]):
        self.client = client
        self.message = message
        self.data = data

        self.user_id = message.chat.id
        self.message_id = message.id
        self.start_time = time.time()

        self.download_dir = Config.DOWNLOAD_DIR
        self.input_path: Optional[str] = None
        self.output_path: Optional[str] = None
        self.thumb_path: Optional[str] = None

        self.media_type = data.get("type")
        self.is_subtitle = data.get("is_subtitle", False)
        self.language = data.get("language", "en")
        self.tmdb_id = data.get("tmdb_id")
        self.original_name = data.get("original_name", "unknown.mkv")

        if data.get("title"):
            self.title = data.get("title")
        else:
            self.title = os.path.splitext(self.original_name)[0]

        self.year = data.get("year")
        self.poster_url = data.get("poster")
        self.season = data.get("season")
        self.episode = data.get("episode")
        self.quality = data.get("quality", "720p")
        self.file_message = data.get("file_message")

        self.status_msg: Optional[Message] = None
        self.settings: Optional[Dict] = None
        self.templates: Optional[Dict] = None
        self.filename_templates: Optional[Dict] = None
        self.channel: Optional[str] = None

        self.mode = "core"
        self.active_client = self.client
        self.tunnel_id = None
        self.tunneled_message_id = None
        self.is_priority = False

        try:
            user_bot = getattr(self.client, "user_bot", None)
            if user_bot:
                file_size = 0
                media = self.file_message.document or self.file_message.video
                if media:
                    file_size = media.file_size

                if file_size > 2000 * 1000 * 1000:
                    self.mode = "pro"
                    self.active_client = user_bot
                    logger.info(
                        f"Activated PRO Mode for task {self.message_id} (Size: {file_size})"
                    )
        except Exception as e:
            logger.warning(f"Error determining mode: {e}")

    async def run(self):
        batch_id = self.data.get("batch_id")
        item_id = self.data.get("item_id")

        file_size = 0
        if self.file_message:
            media = self.file_message.document or self.file_message.video or self.file_message.audio or self.file_message.photo
            if media:
                file_size = getattr(media, "file_size", 0)

        timeout_base = 3600
        timeout_multiplier = (file_size / (1024 * 1024 * 1024)) * 300 if file_size else 0
        phase_timeout = timeout_base + timeout_multiplier

        is_priority = False
        if Config.PUBLIC_MODE:
            user_doc = await db.get_user(self.user_id)
            if user_doc and user_doc.get("is_premium"):
                plan_name = user_doc.get("premium_plan", "standard")
                config = await db.get_public_config()
                if config.get("premium_system_enabled", False):
                    plan_settings = config.get(f"premium_{plan_name}", {})
                    is_priority = plan_settings.get("features", {}).get("priority_queue", False)
        self.is_priority = is_priority

        try:
            if not await self._initialize():
                if batch_id and item_id:
                    queue_manager.update_status(batch_id, item_id, "failed")
                return

            try:
                async with get_semaphore(self.user_id, "download", is_priority):
                    dl_success = await asyncio.wait_for(self._download_media(), timeout=phase_timeout)
                    if not dl_success:
                        if batch_id and item_id:
                            queue_manager.update_status(batch_id, item_id, "failed")
                        return
            except asyncio.TimeoutError:
                logger.error(f"Download phase timed out for {self.message_id}")
                await self._update_status("❌ **Download Timeout**\n\nTask exceeded maximum execution time.")
                if batch_id and item_id:
                    queue_manager.update_status(batch_id, item_id, "failed", "Timeout")
                return

            try:
                async with get_semaphore(self.user_id, "process", is_priority):
                    await asyncio.wait_for(self._prepare_resources(), timeout=1800)
                    proc_success = await asyncio.wait_for(self._process_media(), timeout=phase_timeout)
                    if not proc_success:
                        if batch_id and item_id:
                            queue_manager.update_status(batch_id, item_id, "failed")
                        return
            except asyncio.TimeoutError:
                logger.error(f"Process phase timed out for {self.message_id}")
                await self._update_status("❌ **Process Timeout**\n\nTask exceeded maximum execution time (FFmpeg stall).")
                if batch_id and item_id:
                    queue_manager.update_status(batch_id, item_id, "failed", "Timeout")
                return

            try:
                async with get_semaphore(self.user_id, "upload", is_priority):
                    await asyncio.wait_for(self._upload_media(), timeout=phase_timeout)
            except asyncio.TimeoutError:
                logger.error(f"Upload phase timed out for {self.message_id}")
                await self._update_status("❌ **Upload Timeout**\n\nTask exceeded maximum execution time.")
                if batch_id and item_id:
                    queue_manager.update_status(batch_id, item_id, "failed", "Timeout")
                return

        except Exception as e:
            logger.exception(f"Critical error in task for user {self.user_id}: {e}")
            await self._update_status(f"❌ **Critical System Error**\n\n`{str(e)}`")
            if batch_id and item_id:
                queue_manager.update_status(batch_id, item_id, "failed")
        finally:
            await self._cleanup()
            if batch_id and queue_manager.is_batch_complete(batch_id):
                if not getattr(queue_manager.batches.get(batch_id), "summary_sent", False):
                    try:
                        usage = await db.get_user_usage(self.user_id)
                        config = await db.get_public_config()
                        daily_egress_mb_limit = config.get("daily_egress_mb", 0)
                        daily_file_count_limit = config.get("daily_file_count", 0)
                        global_limit_mb = await db.get_global_daily_egress_limit()

                        now = time.time()
                        user_doc = await db.get_user(self.user_id)
                        is_premium = False
                        if user_doc:
                            exp = user_doc.get("premium_expiry")
                            if user_doc.get("is_premium") and (exp is None or exp > now):
                                is_premium = True

                        premium_system_enabled = config.get("premium_system_enabled", False)

                        if is_premium and premium_system_enabled:
                            daily_egress_mb_limit = config.get("premium_daily_egress_mb", 0)

                        user_files = usage.get("file_count", 0)
                        user_egress_mb = usage.get("egress_mb", 0.0)
                        global_usage_mb = await db.get_global_usage_today()

                        if self.user_id == Config.CEO_ID or self.user_id in Config.ADMIN_IDS:
                            if global_limit_mb > 0:
                                limit_str = f"{global_limit_mb} MB"
                                if global_limit_mb >= 1024:
                                    limit_str = f"{global_limit_mb / 1024:.2f} GB"
                                used_str = f"{global_usage_mb:.2f} MB"
                                if global_usage_mb >= 1024:
                                    used_str = f"{global_usage_mb / 1024:.2f} GB"
                                usage_text = f"Today: {user_files} files processed · {used_str} used of {limit_str} (Global Limit)"
                            else:
                                usage_text = f"Today: {user_files} files · {user_egress_mb:.2f} MB used (Unlimited)"
                        else:
                            if daily_egress_mb_limit <= 0 and daily_file_count_limit <= 0 and global_limit_mb <= 0:
                                usage_text = f"Today: {user_files} files · {user_egress_mb:.2f} MB used (No limits set)"
                            else:
                                limit_to_show = daily_egress_mb_limit
                                show_global = False
                                if global_limit_mb > 0 and (daily_egress_mb_limit <= 0 or global_limit_mb < daily_egress_mb_limit):
                                    limit_to_show = global_limit_mb
                                    show_global = True

                                if limit_to_show > 0:
                                    limit_str = f"{limit_to_show} MB"
                                    if limit_to_show >= 1024:
                                        limit_str = f"{limit_to_show / 1024:.2f} GB"
                                else:
                                    limit_str = "Unlimited"

                                if show_global:
                                    used_str = f"{global_usage_mb:.2f} MB"
                                    if global_usage_mb >= 1024:
                                        used_str = f"{global_usage_mb / 1024:.2f} GB"
                                else:
                                    used_str = f"{user_egress_mb:.2f} MB"
                                    if user_egress_mb >= 1024:
                                        used_str = f"{user_egress_mb / 1024:.2f} GB"

                                limit_type = " (Global Limit)" if show_global else ""
                                usage_text = f"Today: {user_files} files · {used_str} used of {limit_str}{limit_type}"

                        summary_msg = queue_manager.get_batch_summary(batch_id, usage_text)
                        await self.client.send_message(self.user_id, summary_msg)
                        if queue_manager.batches.get(batch_id):
                            setattr(queue_manager.batches.get(batch_id), "summary_sent", True)
                    except Exception as e:
                        logger.warning(f"Failed to send early batch completion msg: {e}")

    async def _initialize(self) -> bool:
        from pyrogram.errors import FloodWait
        if not shutil.which("ffmpeg"):
            try:
                await self.message.edit_text(
                    "❌ **System Error**\n\n`ffmpeg` binary not found. Contact administrator."
                )
            except MessageNotModified:
                pass
            except FloodWait as e:
                logger.warning(f"FloodWait in _initialize: sleeping for {e.value}s")
                await asyncio.sleep(e.value + 1)
                try:
                    await self.message.edit_text(
                        "❌ **System Error**\n\n`ffmpeg` binary not found. Contact administrator."
                    )
                except Exception:
                    pass
            except Exception:
                pass
            return False

        try:
            self.status_msg = await self.message.edit_text(
                "⏳ **Initializing Task...**\n"
                "Allocating resources and preparing environment.\n\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
        except MessageNotModified:
            pass
        except FloodWait as e:
            logger.warning(f"FloodWait in _initialize: sleeping for {e.value}s")
            await asyncio.sleep(e.value + 1)
            try:
                self.status_msg = await self.message.edit_text(
                    "⏳ **Initializing Task...**\n"
                    "Allocating resources and preparing environment.\n\n"
                    f"{XTVEngine.get_signature(mode=self.mode)}"
                )
            except Exception:
                pass
        except Exception:
            pass

        self.settings = await db.get_settings(self.user_id)
        if self.settings:
            self.templates = self.settings.get("templates", Config.DEFAULT_TEMPLATES)
            self.filename_templates = self.settings.get(
                "filename_templates", Config.DEFAULT_FILENAME_TEMPLATES
            )
            self.channel = self.settings.get("channel", Config.DEFAULT_CHANNEL)
        else:
            logger.warning("Database settings unavailable, using defaults.")
            self.templates = Config.DEFAULT_TEMPLATES
            self.filename_templates = Config.DEFAULT_FILENAME_TEMPLATES
            self.channel = Config.DEFAULT_CHANNEL

        return True

    async def _download_media(self) -> bool:
        await self._update_status(
            "📥 **Acquiring Media Resources**\n\n"
            "Establishing connection to Telegram servers...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        ext = ".mkv"
        if self.original_name:
            orig_ext = os.path.splitext(self.original_name)[1].lower()
            if orig_ext:
                ext = orig_ext

        if self.is_subtitle:
            if not ext or ext not in [".srt", ".ass", ".vtt"]:
                ext = ".srt"

        if self.message.photo:
            ext = ".jpg"

        self.input_path = os.path.join(
            self.download_dir, f"{self.user_id}_{self.message_id}_input{ext}"
        )
        download_start = time.time()

        if self.media_type == "audio":
            if not hasattr(self, "metadata"):
                self.metadata = {}

            if self.data.get("audio_thumb_id"):
                self.thumb_path = os.path.join(
                    self.download_dir, f"{self.user_id}_{self.message_id}_thumb.jpg"
                )
                await self.active_client.download_media(
                    self.data.get("audio_thumb_id"), file_name=self.thumb_path
                )

            self.metadata["title"] = self.data.get("audio_title", "")
            self.metadata["artist"] = self.data.get("audio_artist", "")
            if self.data.get("audio_album"):
                self.metadata["album"] = self.data.get("audio_album", "")

        if self.data.get("local_file_path"):
            local_path = self.data.get("local_file_path")
            if os.path.exists(local_path):
                import shutil

                await asyncio.to_thread(shutil.move, local_path, self.input_path)
                file_size = os.path.getsize(self.input_path)
                logger.info(f"Local file moved: {self.input_path} ({file_size} bytes)")

                if self.file_message:

                    class DummyMedia:
                        def __init__(self, size):
                            self.file_size = size

                    if not hasattr(self.file_message, "document") or self.file_message.document is None:
                        self.file_message.document = DummyMedia(file_size)
                    else:
                        self.file_message.document.file_size = file_size

                return True
            else:
                await self._update_status("❌ **Local File Error**\n\nThe extracted file was not found.")
                return False

        target_message = self.file_message
        if self.mode == "pro":
            try:
                bot_me = await self.client.get_me()
                bot_username = bot_me.username

                channel = await self.active_client.create_channel(
                    title=f"𝕏TV Pro Ephemeral {self.message_id}",
                    description="Temporary tunnel for 𝕏TV Bot.",
                )
                self.tunnel_id = channel.id

                from pyrogram.types import ChatPrivileges

                await self.active_client.promote_chat_member(
                    self.tunnel_id,
                    bot_username,
                    privileges=ChatPrivileges(
                        can_manage_chat=True,
                        can_delete_messages=True,
                        can_manage_video_chats=True,
                        can_restrict_members=True,
                        can_promote_members=True,
                        can_change_info=True,
                        can_post_messages=True,
                        can_edit_messages=True,
                        can_invite_users=True,
                        can_pin_messages=True,
                    ),
                )

                ping_msg = await self.active_client.send_message(
                    self.tunnel_id, "ping", disable_notification=True
                )
                await ping_msg.delete()
                await asyncio.sleep(1)

                tunnel_msg = await self.client.copy_message(
                    chat_id=self.tunnel_id,
                    from_chat_id=self.file_message.chat.id,
                    message_id=self.file_message.id,
                )

                target_message = await self.active_client.get_messages(
                    chat_id=self.tunnel_id, message_ids=tunnel_msg.id
                )

                if not target_message or target_message.empty:
                    logger.error(
                        f"Could not fetch copied message {tunnel_msg.id} from tunnel {self.tunnel_id} via Userbot."
                    )
                    await self._update_status(
                        "❌ **Tunnel Resolution Error**\n\nUserbot failed to see the file in the internal tunnel."
                    )
                    return False

                self.tunneled_message_id = tunnel_msg.id

            except Exception as e:
                logger.error(f"Error creating/resolving Ephemeral Tunnel: {e}")
                await self._update_status(f"❌ **Tunnel Bridge Error**\n\n`{e}`")
                return False

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                downloaded_path = await self.active_client.download_media(
                    target_message,
                    file_name=self.input_path,
                    progress=progress_for_pyrogram,
                    progress_args=(
                        f"📥 **Downloading Media Content...**\n(Attempt {attempt}/{max_retries})",
                        self.status_msg,
                        download_start,
                        self.mode,
                        self.is_priority,
                    ),
                )

                if downloaded_path and os.path.exists(downloaded_path):
                    self.input_path = downloaded_path
                    file_size = os.path.getsize(self.input_path)
                    logger.info(f"Download attempt {attempt} success: {self.input_path} ({file_size} bytes)")

                    if file_size == 0:
                        logger.warning(f"Download attempt {attempt} failed: File size is 0 bytes.")
                        os.remove(self.input_path)
                        if attempt < max_retries:
                            await asyncio.sleep(3)
                            continue
                        else:
                            await self._update_status(
                                "❌ **Download Integrity Error**\n\nFile size is 0 bytes after retries."
                            )
                            return False
                    return True
                else:
                    logger.error(f"Download attempt {attempt} returned path but file missing: {self.input_path}")
                    if attempt < max_retries:
                        await asyncio.sleep(3)
                        continue
                    else:
                        await self._update_status(
                            "❌ **Download Verification Failed**\n\nFile not found on disk."
                        )
                        return False

            except Exception as e:
                logger.error(f"Download attempt {attempt} failed: {e}")
                if os.path.exists(self.input_path):
                    try:
                        os.remove(self.input_path)
                    except:
                        pass
                if attempt < max_retries:
                    await asyncio.sleep(5)
                    continue
                else:
                    await self._update_status(f"❌ **Network Error during Download**\n\n`{e}`")
                    return False

        return False

    async def _prepare_resources(self):
        await self._update_status(
            "🎨 **Preparing Metadata Assets**\n\n"
            "Optimizing thumbnails and configuring metadata...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        if not self.thumb_path:
            self.thumb_path = os.path.join(
                self.download_dir, f"{self.user_id}_{self.message_id}_thumb.jpg"
            )

        if not self.is_subtitle and self.media_type != "audio":
            thumb_binary = (
                self.settings.get("thumbnail_binary") if self.settings else None
            )

            if thumb_binary:
                def write_thumb():
                    with open(self.thumb_path, "wb") as f:
                        f.write(thumb_binary)
                await asyncio.to_thread(write_thumb)
            elif self.poster_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(self.poster_url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                def write_poster():
                                    with open(self.thumb_path, "wb") as f:
                                        f.write(data)
                                await asyncio.to_thread(write_poster)
                except Exception as e:
                    logger.warning(f"Failed to download poster: {e}")

        safe_title = re.sub(r'[\\/*?:"<>|,;\'!]', "", self.title)
        safe_title = safe_title.replace("&", "and")

        ext = ".mkv" if not self.is_subtitle else ".srt"
        if not self.is_subtitle and self.original_name:
            orig_ext = os.path.splitext(self.original_name)[1].lower()
            if orig_ext:
                ext = orig_ext

        if self.message.photo:
            ext = ".jpg"

        season_str = f"S{self.season:02d}" if self.season else ""
        if isinstance(self.episode, list):
            episode_str = "".join([f"E{int(e):02d}" for e in self.episode])
        else:
            episode_str = f"E{self.episode:02d}" if self.episode else ""
        season_episode = f"{season_str}{episode_str}"
        year_str = str(self.year) if self.year else ""

        pref_sep = await db.get_preferred_separator(self.user_id) if hasattr(self, 'user_id') else "."

        if "specials" in self.data:
            extracted_specials = self.data["specials"]
        else:
            extracted_specials = []
            if self.original_name:
                orig_name_upper = self.original_name.upper()
                specials_keywords = ["BLURAY", "BLUERAY", "BDRIP", "WEB-DL", "WEBRIP", "HDR", "REMUX", "PROPER", "REPACK", "UNCUT"]
                for kw in specials_keywords:
                    if kw in orig_name_upper:
                        if kw == "WEB-DL": extracted_specials.append("WEB-DL")
                        elif kw == "WEBRIP": extracted_specials.append("WEBRip")
                        elif kw == "HDR": extracted_specials.append("HDR")
                        elif kw == "REMUX": extracted_specials.append("REMUX")
                        elif kw == "PROPER": extracted_specials.append("PROPER")
                        elif kw == "REPACK": extracted_specials.append("REPACK")
                        elif kw == "UNCUT": extracted_specials.append("UNCUT")
                        elif kw == "BDRIP": extracted_specials.append("BDRip")
                        else: extracted_specials.append("BluRay")
                extracted_specials = list(dict.fromkeys(extracted_specials))

        if "codec" in self.data:
            extracted_codec = [self.data["codec"]] if self.data["codec"] else []
        else:
            extracted_codec = []
            if self.original_name:
                orig_name_upper = self.original_name.upper()
                codec_keywords = ["X264", "X265", "HEVC"]
                for kw in codec_keywords:
                    if kw in orig_name_upper:
                        if kw == "X264": extracted_codec.append("x264")
                        elif kw == "X265": extracted_codec.append("x265")
                        elif kw == "HEVC": extracted_codec.append("HEVC")

        if "audio" in self.data:
            extracted_audio = [self.data["audio"]] if self.data["audio"] else []
        else:
            extracted_audio = []
            if self.original_name:
                orig_name_upper = self.original_name.upper()
                audio_keywords = ["DUAL", "DL", "DUBBED", "MULTI", "MICDUB", "LINEDUB", "DTS", "AC3", "ATMOS"]
                for kw in audio_keywords:
                    if kw == "DL":
                        if re.search(r'(?<!WEB-)\bDL\b', orig_name_upper):
                            extracted_audio.append("DL")
                    else:
                        if re.search(r'\b' + re.escape(kw) + r'\b', orig_name_upper):
                            if kw == "DUAL": extracted_audio.append("DUAL")
                            elif kw == "DUBBED": extracted_audio.append("Dubbed")
                            elif kw == "MULTI": extracted_audio.append("Multi")
                            elif kw == "MICDUB": extracted_audio.append("MicDub")
                            elif kw == "LINEDUB": extracted_audio.append("LineDub")
                            elif kw == "DTS": extracted_audio.append("DTS")
                            elif kw == "AC3": extracted_audio.append("AC3")
                            elif kw == "ATMOS": extracted_audio.append("Atmos")

        specials_str = pref_sep.join(extracted_specials)
        codec_str = pref_sep.join(extracted_codec)
        audio_str = pref_sep.join(extracted_audio)

        fmt_dict = {
            "Title": safe_title,
            "Year": year_str,
            "Quality": self.quality,
            "Season": season_str,
            "Episode": episode_str,
            "Season_Episode": season_episode,
            "Language": self.language,
            "Channel": self.channel,
            "Specials": specials_str,
            "Codec": codec_str,
            "Audio": audio_str,
            "filename": (
                os.path.splitext(self.original_name)[0] if self.original_name else ""
            ),
        }

        def clean_filename(name, orig_template=""):

            name = re.sub(r'\[\s*\]', '', name)
            name = re.sub(r'\(\s*\)', '', name)
            name = re.sub(r'\{\s*\}', '', name)

            name = re.sub(r'[\._\s]{2,}', pref_sep, name)

            if orig_template and " " not in orig_template:
                if "." in orig_template:
                    name = name.replace(" ", ".")
                    if "_" not in orig_template:
                        name = name.replace("_", ".")
                elif "_" in orig_template:
                    name = name.replace(" ", "_")
                    if "." not in orig_template:
                        name = name.replace(".", "_")

            name = name.strip('._ ')
            return name

        if self.media_type == "general":
            template = self.data.get("general_name", "{filename}")
            try:
                base_name = template.format(**fmt_dict)
                base_name = clean_filename(base_name, template)
            except KeyError as e:
                logger.warning(
                    f"KeyError {e} in general template '{template}', using fallback."
                )
                base_name = f"{safe_title}"

            final_filename = f"{base_name}{ext}"
            meta_title = base_name

        elif self.media_type == "audio":
            final_filename = f"{safe_title}{ext}"
            meta_title = self.metadata.get("title", safe_title)

        elif self.media_type == "convert":
            target_format = self.data.get('target_format', 'mkv')

            target_ext = f".{target_format}"
            if target_format in ["x264", "x265", "audionorm"]:
                target_ext = ".mkv"

            final_filename = f"{safe_title}{target_ext}"
            meta_title = f"{safe_title}"

        elif self.media_type == "extract_subtitles":
            final_filename = f"{safe_title}_subtitles.srt"
            meta_title = f"{safe_title} Subtitles"

        elif self.media_type == "watermark":
            final_filename = f"{safe_title}_watermarked{ext}"
            meta_title = f"{safe_title}"

        elif self.media_type == "series":
            if self.is_subtitle:
                template = self.filename_templates.get(
                    "subtitles_series",
                    Config.DEFAULT_FILENAME_TEMPLATES["subtitles_series"],
                )
            else:
                template = self.filename_templates.get(
                    "series", Config.DEFAULT_FILENAME_TEMPLATES["series"]
                )

            try:
                base_name = template.format(**fmt_dict)
                base_name = clean_filename(base_name, template)
            except KeyError as e:
                logger.warning(
                    f"KeyError {e} in template '{template}', using fallback."
                )
                fallback_template = (
                    "{Title}.{Season_Episode}.{Quality}_[{Channel}]"
                    if not self.is_subtitle
                    else "{Title}.{Season_Episode}.{Language}"
                )
                base_name = (
                    f"{safe_title}.{season_episode}.{self.quality}_[{self.channel}]"
                    if not self.is_subtitle
                    else f"{safe_title}.{season_episode}.{self.language}"
                )
                base_name = clean_filename(base_name, fallback_template)

            final_filename = f"{base_name}{ext}"
            meta_title = self.templates.get("title", "").format(
                title=self.title, season_episode=season_episode
            )
        else:
            personal_type = self.data.get("personal_type")
            if personal_type:
                key = f"personal_{personal_type}"
                template = self.filename_templates.get(
                    key, Config.DEFAULT_FILENAME_TEMPLATES[key]
                )
            elif self.is_subtitle:
                template = self.filename_templates.get(
                    "subtitles_movies",
                    Config.DEFAULT_FILENAME_TEMPLATES["subtitles_movies"],
                )
            else:
                template = self.filename_templates.get(
                    "movies", Config.DEFAULT_FILENAME_TEMPLATES["movies"]
                )

            try:
                base_name = template.format(**fmt_dict)
                base_name = clean_filename(base_name, template)
            except KeyError as e:
                logger.warning(
                    f"KeyError {e} in template '{template}', using fallback."
                )
                fallback_template = (
                    "{Title}.{Year}.{Quality}_[{Channel}]"
                    if not self.is_subtitle
                    else "{Title}.{Year}.{Language}"
                )
                base_name = (
                    f"{safe_title}.{year_str}.{self.quality}_[{self.channel}]"
                    if not self.is_subtitle
                    else f"{safe_title}.{year_str}.{self.language}"
                )
                base_name = clean_filename(base_name, fallback_template)

            final_filename = f"{base_name}{ext}"
            meta_title = (
                self.templates.get("title", "")
                .format(title=self.title, season_episode="")
                .strip()
            )

        self.output_path = os.path.join(self.download_dir, final_filename)

        if os.path.exists(self.output_path):
            self.output_path = os.path.join(
                self.download_dir, f"{int(time.time())}_{final_filename}"
            )

        if not hasattr(self, "metadata"):
            self.metadata = {}

        if "title" not in self.metadata:
            self.metadata["title"] = meta_title
        if "artist" not in self.metadata:
            self.metadata["artist"] = self.templates.get("artist", "")

        self.metadata.update(
            {
                "author": self.templates.get("author", ""),
                "encoded_by": "@XTVglobal",
                "video_title": self.templates.get("video", "Encoded By:- @XTVglobal"),
                "audio_title": self.templates.get(
                    "audio", "Audio By:- @XTVglobal - {lang}"
                ),
                "subtitle_title": self.templates.get(
                    "subtitle", "Subtitled By:- @XTVglobal - {lang}"
                ),
                "default_language": "English",
                "copyright": self.templates.get("copyright", "@XTVglobal"),
            }
        )

    async def _process_media(self) -> bool:
        if self.media_type == "convert":
            await self._update_status(
                "🔀 **Converting Media Format**\n\n"
                "Initializing video stream processor...\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
        elif self.media_type == "extract_subtitles":
            await self._update_status(
                "📝 **Extracting Subtitles**\n\n"
                "Scanning video streams for text tracks...\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
        else:
            await self._update_status(
                "⚙️ **Executing Transcoding Matrix**\n\n"
                "Injecting metadata and optimizing container...\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )

        if self.media_type == "watermark":
            wtype = self.data.get("watermark_type")
            wcontent = self.data.get("watermark_content")
            pos = self.data.get("watermark_position", "bottomright")
            size = self.data.get("watermark_size", "medium")

            cmd = ["ffmpeg", "-y", "-i", self.input_path]

            if wtype == "text":
                escaped_text = wcontent.replace("'", "\\'").replace(":", "\\:")

                if size == "small":
                    fontsize = "h/20"
                elif size == "large":
                    fontsize = "h/5"
                elif size in ["10", "20", "30"]:
                    factor = int(size) / 100
                    fontsize = f"h*{factor}"
                else:
                    fontsize = "h/10"

                if pos == "topleft":
                    x, y = "10", "10"
                elif pos == "topright":
                    x, y = "w-text_w-10", "10"
                elif pos == "bottomleft":
                    x, y = "10", "h-text_h-10"
                elif pos == "center":
                    x, y = "(w-text_w)/2", "(h-text_h)/2"
                else:
                    x, y = "w-text_w-10", "h-text_h-10"

                cmd.extend(
                    [
                        "-vf",
                        f"drawtext=text='{escaped_text}':fontcolor=white@0.8:fontsize={fontsize}:x={x}:y={y}:box=1:boxcolor=black@0.5:boxborderw=5",
                    ]
                )

            else:
                watermark_path = os.path.join(
                    self.download_dir, f"{self.user_id}_wm_overlay.png"
                )
                if wcontent:
                    await self.active_client.download_media(
                        wcontent, file_name=watermark_path
                    )

                if os.path.exists(watermark_path):
                    if size == "small":
                        scale_expr = "w='main_w*0.1':h='ow/a'"
                    elif size == "large":
                        scale_expr = "w='main_w*0.4':h='ow/a'"
                    elif size in ["10", "20", "30"]:
                        scale_expr = f"w='main_w*{int(size)/100}':h='ow/a'"
                    else:
                        scale_expr = "w='main_w*0.2':h='ow/a'"

                    if pos == "topleft":
                        overlay_expr = "10:10"
                    elif pos == "topright":
                        overlay_expr = "W-w-10:10"
                    elif pos == "bottomleft":
                        overlay_expr = "10:H-h-10"
                    elif pos == "center":
                        overlay_expr = "(W-w)/2:(H-h)/2"
                    else:
                        overlay_expr = "W-w-10:H-h-10"

                    cmd.extend(
                        [
                            "-i",
                            watermark_path,
                            "-filter_complex",
                            f"[1:v][0:v]scale2ref={scale_expr}[wm][vid];[vid][wm]overlay={overlay_expr}",
                        ]
                    )
                else:
                    logger.error("Watermark overlay image missing.")

            cmd.append(self.output_path)
            err = None
        elif self.media_type == "convert":
            target_format = self.data.get("target_format", "mkv")
            cmd = ["ffmpeg", "-y", "-i", self.input_path]

            if target_format == "mp3":
                cmd.extend(["-vn", "-c:a", "libmp3lame", "-q:a", "2"])
            elif target_format == "gif":
                cmd.extend(["-vf", "fps=10,scale=320:-1:flags=lanczos", "-c:v", "gif"])
            elif target_format in ["png", "jpg", "jpeg", "webp"]:
                cmd.extend(["-vframes", "1"])
            elif target_format == "x264":
                cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "copy", "-c:s", "copy"])
            elif target_format == "x265":
                cmd.extend(["-c:v", "libx265", "-preset", "fast", "-crf", "28", "-c:a", "copy", "-c:s", "copy"])
            elif target_format == "audionorm":
                cmd.extend(["-c:v", "copy", "-c:s", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k"])
            else:
                cmd.extend(["-c", "copy"])

            cmd.append(self.output_path)
            err = None
        elif self.media_type == "extract_subtitles":

            cmd = ["ffmpeg", "-y", "-i", self.input_path, "-map", "0:s:0?", "-c:s", "srt", self.output_path]
            err = None
        else:
            cmd, err = await generate_ffmpeg_command(
                input_path=self.input_path,
                output_path=self.output_path,
                metadata=self.metadata,
                thumbnail_path=(
                    self.thumb_path
                    if (
                        os.path.exists(self.thumb_path)
                        and not self.is_subtitle
                        and self.media_type != "convert"
                    )
                    else None
                ),
            )

        if not cmd:
            logger.error(f"FFmpeg command generation failed: {err}")
            await self._update_status(
                f"❌ **Processing Configuration Error**\n\n`{err}`"
            )
            return False

        total_duration = 0
        if self.media_type == "convert" or self.media_type == "extract_subtitles":
            try:
                probe, _ = await probe_file(self.input_path)
                if probe and "format" in probe and "duration" in probe["format"]:
                    total_duration = float(probe["format"]["duration"])
            except Exception as e:
                logger.warning(f"Could not get duration for progress: {e}")

        last_update_time = 0

        async def ffmpeg_progress(time_str):
            nonlocal last_update_time, total_duration

            if total_duration > 0 and (time.time() - last_update_time) > 5:
                try:

                    h, m, s = time_str.split(':')
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)

                    percentage = (current_time / total_duration) * 100
                    if percentage > 100: percentage = 100
                    if percentage < 0: percentage = 0

                    filled_blocks = int(percentage / 10)
                    empty_blocks = 10 - filled_blocks
                    bar = "█" * filled_blocks + "·" * empty_blocks

                    def format_time(seconds):
                        hours = int(seconds // 3600)
                        minutes = int((seconds % 3600) // 60)
                        secs = int(seconds % 60)
                        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

                    msg = (
                        "🔀 **Converting Media Format**\n\n"
                        "Processing video stream...\n"
                        f"Progress: [{bar}] {percentage:.1f}%\n"
                        f"Time: {format_time(current_time)} / {format_time(total_duration)}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"{XTVEngine.get_signature(mode=self.mode)}"
                    )

                    await self._update_status(msg)
                    last_update_time = time.time()
                except Exception as e:
                    logger.debug(f"Failed to update ffmpeg progress: {e}")

        if self.media_type == "convert":
            success, stderr = await execute_ffmpeg(cmd, progress_callback=ffmpeg_progress)
        else:
            success, stderr = await execute_ffmpeg(cmd)

        if not success:
            err_msg = "Unknown Error"
            if stderr:
                err_lines = stderr.decode(errors='replace').strip().split('\n')
                # Grab the last few relevant lines for the user
                err_msg = "\n".join(err_lines[-5:]).strip()
                if not err_msg:
                    err_msg = "Unknown Error"

            logger.error(f"FFmpeg execution failed: {err_msg}")

            # Truncate to avoid Telegram message length limits
            if len(err_msg) > 500:
                err_msg = err_msg[-500:] + "..."

            await self._update_status(
                f"❌ **Transcoding Failed**\n\nThe FFmpeg engine reported an error during processing:\n\n`{err_msg}`"
            )
            return False

        if self.media_type == "extract_subtitles":

            if not os.path.exists(self.output_path) or os.path.getsize(self.output_path) == 0:
                logger.error("Subtitle extraction failed: no subtitles found in stream.")
                await self._update_status("❌ **Extraction Failed**\n\nNo subtitles were found in this video.")
                return False

        return True

    async def _upload_media(self):
        await self._update_status(
            "📤 **Finalizing & Uploading**\n\n"
            "Transferring optimized asset to cloud...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        upload_start = time.time()
        final_filename = os.path.basename(self.output_path)

        caption = self._generate_caption(final_filename)

        target_chat_id = self.user_id
        is_tunneling = False

        if self.mode == "pro":
            is_tunneling = True
            if self.tunnel_id:
                target_chat_id = self.tunnel_id
            else:
                await self._update_status(
                    "❌ **Upload Configuration Error**\n\nPro Tunnel ID not initialized."
                )
                return

        from pyrogram.errors import FloodWait

        max_upload_retries = 3
        media_msg = None

        for upload_attempt in range(max_upload_retries):
            try:
                if is_tunneling:
                    try:
                        pass
                    except Exception:
                        pass

                thumb = (
                    self.thumb_path
                    if (
                        self.thumb_path
                        and os.path.exists(self.thumb_path)
                        and not self.is_subtitle
                    )
                    else None
                )

                send_as = self.data.get("send_as")

                file_ext = os.path.splitext(self.output_path)[1].lower()
                is_vid_ext = file_ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]
                is_aud_ext = file_ext in [".mp3", ".flac", ".m4a", ".wav", ".ogg"]
                is_img_ext = file_ext in [".jpg", ".jpeg", ".png", ".webp"]

                if send_as == "photo" or (
                    self.message.photo and not send_as and not is_vid_ext and not is_aud_ext
                ):
                    media_msg = await self.active_client.send_photo(
                        chat_id=target_chat_id,
                        photo=self.output_path,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            (
                                "📤 **Uploading Photo (Tunneling)...**"
                                if is_tunneling
                                else "📤 **Uploading Photo...**"
                            ),
                            self.status_msg,
                            upload_start,
                            self.mode,
                            self.is_priority,
                        ),
                    )
                elif send_as == "media":
                    if is_img_ext:
                        media_msg = await self.active_client.send_photo(
                            chat_id=target_chat_id,
                            photo=self.output_path,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                (
                                    "📤 **Uploading Photo (Tunneling)...**"
                                    if is_tunneling
                                    else "📤 **Uploading Photo...**"
                                ),
                                self.status_msg,
                                upload_start,
                                self.mode,
                                self.is_priority,
                            ),
                        )
                    elif is_vid_ext:
                        media_msg = await self.active_client.send_video(
                            chat_id=target_chat_id,
                            video=self.output_path,
                            thumb=thumb,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                (
                                    "📤 **Uploading Video (Tunneling)...**"
                                    if is_tunneling
                                    else "📤 **Uploading Video...**"
                                ),
                                self.status_msg,
                                upload_start,
                                self.mode,
                                self.is_priority,
                            ),
                        )
                    elif is_aud_ext:
                        media_msg = await self.active_client.send_audio(
                            chat_id=target_chat_id,
                            audio=self.output_path,
                            thumb=thumb,
                            caption=caption,
                            title=self.metadata.get("title"),
                            performer=self.metadata.get("artist"),
                            progress=progress_for_pyrogram,
                            progress_args=(
                                (
                                    "📤 **Uploading Audio (Tunneling)...**"
                                    if is_tunneling
                                    else "📤 **Uploading Audio...**"
                                ),
                                self.status_msg,
                                upload_start,
                                self.mode,
                                self.is_priority,
                            ),
                        )
                    else:
                        media_msg = await self.active_client.send_document(
                            chat_id=target_chat_id,
                            document=self.output_path,
                            thumb=thumb,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                (
                                    "📤 **Uploading Media (Tunneling)...**"
                                    if is_tunneling
                                    else "📤 **Uploading Media...**"
                                ),
                                self.status_msg,
                                upload_start,
                                self.mode,
                                self.is_priority,
                            ),
                        )
                else:
                    media_msg = await self.active_client.send_document(
                        chat_id=target_chat_id,
                        document=self.output_path,
                        thumb=thumb,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            (
                                "📤 **Uploading Final File (Tunneling)...**"
                                if is_tunneling
                                else "📤 **Uploading Final File...**"
                            ),
                            self.status_msg,
                            upload_start,
                            self.mode,
                            self.is_priority,
                        ),
                    )

                if is_tunneling:
                    for tunnel_copy_attempt in range(3):
                        try:
                            await self.client.copy_message(
                                chat_id=self.user_id,
                                from_chat_id=self.tunnel_id,
                                message_id=media_msg.id,
                            )
                            break
                        except FloodWait as e:
                            logger.warning(f"FloodWait during tunnel copy: sleeping {e.value}s")
                            await asyncio.sleep(e.value + 1)
                        except Exception as e:
                            logger.error(
                                f"Failed to copy tunneled file to user {self.user_id}: {e}"
                            )
                            if tunnel_copy_attempt == 2:
                                await self.client.send_message(
                                    self.user_id,
                                    f"❌ **Delivery Error**\n\nThe file was processed successfully but the bot failed to deliver it to you from the tunnel. Error: `{e}`",
                                )
                break
            except FloodWait as e:
                logger.warning(f"FloodWait during upload: sleeping {e.value}s before retrying")
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                if upload_attempt == max_upload_retries - 1:
                    raise e
                logger.warning(f"Upload attempt {upload_attempt + 1} failed: {e}. Retrying...")
                await asyncio.sleep(5)

        try:

            file_chat_id = self.data.get("file_chat_id")
            file_message_id = self.data.get("file_message_id")
            if file_chat_id and file_message_id:
                try:
                    await self.client.delete_messages(chat_id=file_chat_id, message_ids=file_message_id)
                except Exception as del_err:
                    logger.warning(f"Failed to auto-delete original message: {del_err}")

            usage_text = ""
            try:

                original_size = 0
                if self.file_message:
                    media = self.file_message.document or self.file_message.video or self.file_message.audio or self.file_message.photo
                    original_size = getattr(media, "file_size", 0) if media else 0

                processed_size = os.path.getsize(self.output_path)

                await db.update_usage(self.user_id, processed_size, reserved_file_size_bytes=original_size)

                self.processing_successful = True

                usage = await db.get_user_usage(self.user_id)
                config = await db.get_public_config()

                daily_egress_mb_limit = config.get("daily_egress_mb", 0)
                daily_file_count_limit = config.get("daily_file_count", 0)
                global_limit_mb = await db.get_global_daily_egress_limit()

                user_files = usage.get("file_count", 0)
                user_egress_mb = usage.get("egress_mb", 0.0)

                now = time.time()
                user_doc = await db.get_user(self.user_id)
                is_premium = False
                if user_doc:
                    exp = user_doc.get("premium_expiry")
                    if user_doc.get("is_premium") and (exp is None or exp > now):
                        is_premium = True

                premium_system_enabled = config.get("premium_system_enabled", False)

                if is_premium and premium_system_enabled:
                    daily_egress_mb_limit = config.get("premium_daily_egress_mb", 0)

                global_usage_mb = await db.get_global_usage_today()

                if self.user_id == Config.CEO_ID or self.user_id in Config.ADMIN_IDS:
                    if global_limit_mb > 0:
                        limit_str = f"{global_limit_mb} MB"
                        if global_limit_mb >= 1024:
                            limit_str = f"{global_limit_mb / 1024:.2f} GB"

                        used_str = f"{global_usage_mb:.2f} MB"
                        if global_usage_mb >= 1024:
                            used_str = f"{global_usage_mb / 1024:.2f} GB"

                        usage_text = f"Today: {user_files} files · {used_str} used of {limit_str} (Global Limit)"
                    else:
                        usage_text = f"Today: {user_files} files · {user_egress_mb:.2f} MB used (Unlimited)"
                else:
                    if daily_egress_mb_limit <= 0 and daily_file_count_limit <= 0 and global_limit_mb <= 0:
                        usage_text = f"Today: {user_files} files · {user_egress_mb:.2f} MB used (No limits set)"
                    else:
                        limit_to_show = daily_egress_mb_limit
                        show_global = False
                        if global_limit_mb > 0 and (daily_egress_mb_limit <= 0 or global_limit_mb < daily_egress_mb_limit):
                            limit_to_show = global_limit_mb
                            show_global = True

                        if limit_to_show > 0:
                            limit_str = f"{limit_to_show} MB"
                            if limit_to_show >= 1024:
                                limit_str = f"{limit_to_show / 1024:.2f} GB"
                        else:
                            limit_str = "Unlimited"

                        if show_global:
                            used_str = f"{global_usage_mb:.2f} MB"
                            if global_usage_mb >= 1024:
                                used_str = f"{global_usage_mb / 1024:.2f} GB"
                        else:
                            used_str = f"{user_egress_mb:.2f} MB"
                            if user_egress_mb >= 1024:
                                used_str = f"{user_egress_mb / 1024:.2f} GB"

                        limit_type = " (Global Limit)" if show_global else ""
                        usage_text = f"Today: {user_files} files · {used_str} used of {limit_str}{limit_type}"

            except Exception as usage_e:
                logger.error(
                    f"Error fetching/updating usage for success message: {usage_e}"
                )

            await self.status_msg.delete()

            batch_id = self.data.get("batch_id")
            item_id = self.data.get("item_id")
            dumb_channel = self.data.get("dumb_channel")

            import datetime
            user_doc = await db.get_user(self.user_id)
            if Config.PUBLIC_MODE:
                plan = user_doc.get("premium_plan", "standard") if user_doc and user_doc.get("is_premium") else "free"
            else:
                plan = "global"

            db_channel_id = await db.get_db_channel(plan)

            saved_file_id = None
            if db_channel_id:
                try:
                    if is_tunneling:
                        db_msg = await self.client.copy_message(
                            chat_id=db_channel_id,
                            from_chat_id=self.tunnel_id,
                            message_id=media_msg.id,
                        )
                    else:
                        db_msg = await self.client.copy_message(
                            chat_id=db_channel_id,
                            from_chat_id=media_msg.chat.id,
                            message_id=media_msg.id,
                        )
                    saved_file_id = db_msg.id

                    config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
                    limits = config.get("myfiles_limits", {}).get(plan, {})
                    perm_limit = limits.get("permanent_limit", 50)
                    expiry_days = limits.get("expiry_days", 10)

                    auto_perm = True
                    user_settings = await db.get_settings(self.user_id)
                    if user_settings and "myfiles_auto_permanent" in user_settings:
                        auto_perm = user_settings["myfiles_auto_permanent"]

                    perm_count = await db.files.count_documents({"user_id": self.user_id, "status": "permanent"})

                    status = "temporary"
                    if auto_perm and (perm_limit == -1 or perm_count < perm_limit):
                        status = "permanent"

                    expiry_date = None
                    if status == "temporary" and expiry_days != -1:
                        expiry_date = datetime.datetime.utcnow() + datetime.timedelta(days=expiry_days)

                    folder_id = None
                    if self.tmdb_id:
                        folder_type = "series" if self.media_type == "series" else "movies"
                        folder = await db.folders.find_one({"user_id": self.user_id, "tmdb_id": self.tmdb_id})
                        if not folder:
                            res = await db.folders.insert_one({
                                "user_id": self.user_id,
                                "name": self.title,
                                "type": folder_type,
                                "tmdb_id": self.tmdb_id,
                                "created_at": datetime.datetime.utcnow()
                            })
                            folder_id = res.inserted_id
                        else:
                            folder_id = folder["_id"]

                    file_data = {
                        "user_id": self.user_id,
                        "file_name": final_filename,
                        "message_id": saved_file_id,
                        "channel_id": db_channel_id,
                        "status": status,
                        "folder_id": folder_id,
                        "created_at": datetime.datetime.utcnow(),
                        "expires_at": expiry_date,
                    }
                    await db.files.insert_one(file_data)
                except Exception as e:
                    logger.error(f"Failed to save file to DB Channel {db_channel_id}: {e}")

            if batch_id and item_id:
                if not dumb_channel:
                    queue_manager.update_status(batch_id, item_id, "done_dumb")
                else:
                    queue_manager.update_status(batch_id, item_id, "done_user")

                if queue_manager.is_batch_complete(batch_id):
                    if not getattr(queue_manager.batches.get(batch_id), "summary_sent", False):
                        try:
                            summary_msg = queue_manager.get_batch_summary(batch_id, usage_text)
                            await self.client.send_message(
                                self.user_id, summary_msg
                            )
                            if queue_manager.batches.get(batch_id):
                                setattr(queue_manager.batches.get(batch_id), "summary_sent", True)
                        except Exception as e:
                            logger.warning(f"Failed to send batch completion msg: {e}")

                if dumb_channel:
                    wait_start = time.time()
                    timeout = await db.get_dumb_channel_timeout()
                    wait_msg = None
                    last_wait_text = None

                    while True:
                        blocking_item = queue_manager.get_blocking_item(
                            batch_id, item_id
                        )
                        if not blocking_item:
                            break

                        if time.time() - wait_start > timeout:
                            logger.warning(
                                f"Timeout waiting for dumb channel upload for {final_filename}"
                            )
                            if wait_msg:
                                await wait_msg.delete()
                            break

                        wait_text = f"⏳ **Waiting for {blocking_item.display_name} to finish To send it in the dumb channel**"

                        if not wait_msg:
                            wait_msg = await self.message.reply_text(wait_text)
                            last_wait_text = wait_text
                        elif last_wait_text != wait_text:
                            try:
                                await wait_msg.edit_text(wait_text)
                                last_wait_text = wait_text
                            except Exception as e:
                                logger.warning(f"Failed to edit wait message: {e}")

                        await asyncio.sleep(5)

                    if wait_msg:
                        try:
                            await wait_msg.delete()
                        except Exception:
                            pass

                    try:
                        if is_tunneling:
                            await self.client.copy_message(
                                chat_id=dumb_channel,
                                from_chat_id=self.tunnel_id,
                                message_id=media_msg.id,
                            )
                        else:
                            await self.client.copy_message(
                                chat_id=dumb_channel,
                                from_chat_id=media_msg.chat.id,
                                message_id=media_msg.id,
                            )
                        queue_manager.update_status(batch_id, item_id, "done_dumb")
                    except Exception as e:
                        logger.error(
                            f"Failed to copy {final_filename} to dumb channel {dumb_channel}: {e}"
                        )
                        queue_manager.update_status(batch_id, item_id, "failed", str(e))

            elif not batch_id:
                try:

                    await self.client.send_message(
                        self.user_id, f"✅ **Processing Complete!**\n\n📊 **Usage:** {usage_text.replace('Today: ', '')}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to send single completion msg: {e}")

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            await self._update_status(f"❌ **Upload Protocol Failed**\n\n`{e}`")
            batch_id = self.data.get("batch_id")
            item_id = self.data.get("item_id")
            if batch_id and item_id:
                queue_manager.update_status(batch_id, item_id, "failed", str(e))
        finally:
            if is_tunneling and self.tunnel_id:
                try:
                    await self.active_client.delete_channel(self.tunnel_id)
                    logger.info(f"Cleaned up ephemeral tunnel {self.tunnel_id}")
                except Exception as e:
                    logger.warning(
                        f"Failed to cleanup ephemeral tunnel {self.tunnel_id}: {e}"
                    )

    def _generate_caption(self, filename: str) -> str:
        template = self.templates.get("caption", "{random}")

        if "{random}" in template or template == "{random}":
            return "".join(random.choices(string.ascii_letters + string.digits, k=16))

        file_size = os.path.getsize(self.output_path)
        size_str = self._humanbytes(file_size)

        return template.format(
            filename=filename,
            size=size_str,
            duration="",
            random="".join(random.choices(string.ascii_letters + string.digits, k=8)),
        )

    @staticmethod
    def _humanbytes(size: int) -> str:
        if not size:
            return ""
        power = 2**10
        n = 0
        dic_power = {0: " ", 1: "K", 2: "M", 3: "G", 4: "T"}
        while size > power:
            size /= power
            n += 1
        return str(round(size, 2)) + " " + dic_power[n] + "B"

    async def _update_status(self, text: str):
        from pyrogram.errors import FloodWait
        for attempt in range(3):
            try:
                if self.status_msg:
                    await self.status_msg.edit_text(text)
                return
            except FloodWait as e:
                logger.warning(f"FloodWait in _update_status: sleeping for {e.value}s")
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                logger.warning(f"Failed to update status message: {e}")
                return

    async def _cleanup(self):
        for path in [self.input_path, self.output_path, self.thumb_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {path}: {e}")

        if self.mode == "pro" and self.tunnel_id:
            try:
                await self.active_client.delete_channel(self.tunnel_id)
            except Exception:
                pass

        if self.data.get("extract_dir") and self.data.get("batch_id"):
            extract_dir = self.data.get("extract_dir")
            batch_id = self.data.get("batch_id")

            if queue_manager.is_batch_complete(batch_id):
                if os.path.exists(extract_dir):
                    try:
                        shutil.rmtree(extract_dir, ignore_errors=True)
                    except Exception as e:
                        logger.warning(f"Failed to remove extraction directory {extract_dir}: {e}")

        if not getattr(self, "processing_successful", False):
            try:
                original_size = 0
                if self.file_message:
                    media = self.file_message.document or self.file_message.video or self.file_message.audio or self.file_message.photo
                    original_size = getattr(media, "file_size", 0) if media else 0

                if original_size > 0:
                    await db.release_quota(self.user_id, original_size)
            except Exception as e:
                logger.error(f"Failed to release quota in cleanup: {e}")

async def process_file(client, message, data):

    await db.ensure_user(
        user_id=message.from_user.id if message.from_user else message.chat.id,
        first_name=message.from_user.first_name if message.from_user else message.chat.title,
        username=message.from_user.username if message.from_user else None,
        last_name=message.from_user.last_name if message.from_user else None,
        language_code=message.from_user.language_code if message.from_user else None,
        is_bot=message.from_user.is_bot if message.from_user else False
    )

    processor = TaskProcessor(client, message, data)
    await processor.run()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
