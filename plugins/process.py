# --- Imports ---
import asyncio
import contextlib
import logging
import math
import os
import random
import re
import shutil
import string
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import MessageNotModified
from pyrogram.types import Message

from config import Config
from db import db
from utils.media.detect import apply_autofill, probe_audio_streams
from utils.media.ffmpeg_tools import execute_ffmpeg, generate_ffmpeg_command, probe_file
from utils.queue_manager import queue_manager
from utils.telegram.progress import progress_for_pyrogram
from utils.XTVengine import XTVEngine

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
            if (
                batch_id
                and queue_manager.is_batch_complete(batch_id)
                and not getattr(queue_manager.batches.get(batch_id), "summary_sent", False)
            ):
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
                    with contextlib.suppress(Exception):
                        await self.client.send_sticker(self.user_id, "CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")
                    if queue_manager.batches.get(batch_id):
                        queue_manager.batches.get(batch_id).summary_sent = True
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
                with contextlib.suppress(Exception):
                    await self.message.edit_text(
                        "❌ **System Error**\n\n`ffmpeg` binary not found. Contact administrator."
                    )
            except Exception:
                pass
            return False

        try:
            self.status_msg = await self.message.edit_text(
                "⏳ **Initializing Task...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> Allocating resources and configuring pipeline...\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
        except MessageNotModified:
            pass
        except FloodWait as e:
            logger.warning(f"FloodWait in _initialize: sleeping for {e.value}s")
            await asyncio.sleep(e.value + 1)
            with contextlib.suppress(Exception):
                self.status_msg = await self.message.edit_text(
                    "⏳ **Initializing Task...**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n\n"
                    "> Allocating resources and configuring pipeline...\n"
                    "\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"{XTVEngine.get_signature(mode=self.mode)}"
                )
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
            "📥 **Downloading Media...**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Establishing connection to Telegram servers...\n"
            "\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        ext = ".mkv"
        if self.original_name:
            orig_ext = os.path.splitext(self.original_name)[1].lower()
            if orig_ext:
                ext = orig_ext

        if self.is_subtitle and (not ext or ext not in [".srt", ".ass", ".vtt"]):
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
                    with contextlib.suppress(OSError):
                        os.remove(self.input_path)
                if attempt < max_retries:
                    await asyncio.sleep(5)
                    continue
                else:
                    await self._update_status(f"❌ **Network Error during Download**\n\n`{e}`")
                    return False

        return False

    async def _prepare_resources(self):
        await self._update_status(
            "🎨 **Preparing Resources...**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Optimizing thumbnails and configuring metadata...\n"
            "\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        if not self.thumb_path:
            self.thumb_path = os.path.join(
                self.download_dir, f"{self.user_id}_{self.message_id}_thumb.jpg"
            )

        if not self.is_subtitle and self.media_type != "audio":
            thumb_mode = self.settings.get("thumbnail_mode", "none") if self.settings else "none"

            if thumb_mode == "none":
                self.thumb_path = None
            else:
                thumb_binary = (
                    self.settings.get("thumbnail_binary") if self.settings else None
                )

                if thumb_mode == "custom" and thumb_binary:
                    def write_thumb():
                        with open(self.thumb_path, "wb") as f:
                            f.write(thumb_binary)
                    await asyncio.to_thread(write_thumb)
                elif thumb_mode == "auto" and self.poster_url:
                    try:
                        async with aiohttp.ClientSession() as session, session.get(self.poster_url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                def write_poster():
                                    with open(self.thumb_path, "wb") as f:
                                        f.write(data)
                                await asyncio.to_thread(write_poster)
                    except Exception as e:
                        logger.warning(f"Failed to download poster: {e}")
                else:
                    self.thumb_path = None

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

        # v1.6.0: Runtime audio-stream probe + auto-fill.
        # Safe no-op when ffprobe missing, file absent, subtitle, or user locked fields.
        if (
            self.input_path
            and not self.is_subtitle
            and self.media_type not in ("audio", "convert", "extract_subtitles", "watermark")
            and not self.data.get("audio_locked")
            and not self.data.get("audio")
        ):
            try:
                detected = await probe_audio_streams(self.input_path)
                if detected:
                    self.data["detected_audio_runtime"] = detected
                    apply_autofill(self.data)
                    logger.info(
                        f"[autofill] user={self.user_id} msg={self.message_id} "
                        f"audio={self.data.get('audio')!r} (runtime-detected)"
                    )
            except Exception as e:
                logger.warning(f"probe_audio_streams failed: {e}")

        if "specials" in self.data:
            extracted_specials = self.data["specials"]
        else:
            extracted_specials = []
            if self.original_name:
                orig_name_upper = self.original_name.upper()
                specials_map = {
                    "WEB-DL": "WEB-DL",
                    "WEBRIP": "WEBRip",
                    "HDR": "HDR",
                    "REMUX": "REMUX",
                    "PROPER": "PROPER",
                    "REPACK": "REPACK",
                    "UNCUT": "UNCUT",
                    "BDRIP": "BDRip",
                    "BLURAY": "BluRay",
                    "BLUERAY": "BluRay",
                }
                for kw, label in specials_map.items():
                    if kw in orig_name_upper:
                        extracted_specials.append(label)
                extracted_specials = list(dict.fromkeys(extracted_specials))

        if "codec" in self.data:
            extracted_codec = [self.data["codec"]] if self.data["codec"] else []
        else:
            extracted_codec = []
            if self.original_name:
                orig_name_upper = self.original_name.upper()
                codec_map = {"X264": "x264", "X265": "x265", "HEVC": "HEVC"}
                for kw, label in codec_map.items():
                    if kw in orig_name_upper:
                        extracted_codec.append(label)

        if "audio" in self.data:
            extracted_audio = [self.data["audio"]] if self.data["audio"] else []
        else:
            extracted_audio = []
            if self.original_name:
                orig_name_upper = self.original_name.upper()
                audio_map = {
                    "DUAL": "DUAL",
                    "DUBBED": "Dubbed",
                    "MULTI": "Multi",
                    "MICDUB": "MicDub",
                    "LINEDUB": "LineDub",
                    "DTS": "DTS",
                    "AC3": "AC3",
                    "ATMOS": "Atmos",
                }
                if re.search(r'(?<!WEB-)\bDL\b', orig_name_upper):
                    extracted_audio.append("DL")
                for kw, label in audio_map.items():
                    if re.search(r'\b' + re.escape(kw) + r'\b', orig_name_upper):
                        extracted_audio.append(label)

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

            logger.info(
                f"[rename] user={self.user_id} mode=general "
                f"template={template!r} specials={specials_str!r} codec={codec_str!r} "
                f"audio={audio_str!r} quality={self.quality!r} "
                f"original={self.original_name!r} -> {base_name!r}"
            )

            final_filename = f"{base_name}{ext}"
            meta_title = base_name

        elif self.media_type in ["audio", "convert", "extract_subtitles", "watermark"]:
            final_filename = "to_be_generated"
            meta_title = "to_be_generated"

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

            logger.info(
                f"[rename] user={self.user_id} mode=series sub={self.is_subtitle} "
                f"template={template!r} specials={specials_str!r} codec={codec_str!r} "
                f"audio={audio_str!r} quality={self.quality!r} "
                f"season_episode={season_episode!r} original={self.original_name!r} "
                f"-> {base_name!r}"
            )

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

            logger.info(
                f"[rename] user={self.user_id} mode={self.media_type} sub={self.is_subtitle} "
                f"template={template!r} specials={specials_str!r} codec={codec_str!r} "
                f"audio={audio_str!r} quality={self.quality!r} year={year_str!r} "
                f"original={self.original_name!r} -> {base_name!r}"
            )

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
        if self.media_type not in ["convert", "extract_subtitles", "audio", "watermark", "trim", "voice_convert", "video_note"]:
            await self._update_status(
                "⚙️ **Processing Media...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> Injecting metadata and optimizing container...\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )

        total_duration = 0
        if self.media_type == "convert" or self.media_type == "extract_subtitles" or self.media_type == "watermark":
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
                    if percentage > 100:
                        percentage = 100
                    if percentage < 0:
                        percentage = 0

                    filled_blocks = int(percentage / 10)
                    empty_blocks = 10 - filled_blocks
                    bar = "█" * filled_blocks + "·" * empty_blocks

                    def format_time(seconds):
                        hours = int(seconds // 3600)
                        minutes = int((seconds % 3600) // 60)
                        secs = int(seconds % 60)
                        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

                    remaining = total_duration - current_time
                    filled = int(percentage / 10)
                    bar = "■" * filled + "□" * (10 - filled)

                    msg = (
                        "⚙️ **Processing Media...**\n"
                        "━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"**Progress:**  `{percentage:.1f}%`\n"
                        f"[{bar}]\n\n"
                        f"> **Elapsed:** `{format_time(current_time)}` · "
                        f"**Remaining:** `{format_time(remaining)}`\n"
                        f"> **Duration:** `{format_time(total_duration)}`\n"
                        f"\n━━━━━━━━━━━━━━━━━━━━\n"
                        f"{XTVEngine.get_signature(mode=self.mode)}"
                    )

                    await self._update_status(msg)
                    last_update_time = time.time()
                except Exception as e:
                    logger.debug(f"Failed to update ffmpeg progress: {e}")

        safe_title = re.sub(r'[\\/*?:"<>|,;\'!]', "", self.title)
        safe_title = safe_title.replace("&", "and")

        ext = ".mkv" if not self.is_subtitle else ".srt"
        if not self.is_subtitle and self.original_name:
            orig_ext = os.path.splitext(self.original_name)[1].lower()
            if orig_ext:
                ext = orig_ext
        if self.message.photo:
            ext = ".jpg"

        if self.media_type == "watermark":
            await self._update_status(
                "©️ **Applying Watermark...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> Applying customized watermark overlay...\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
            from tools.ImageWatermarker import watermark
            wtype = self.data.get("watermark_type")
            wcontent = self.data.get("watermark_content")
            pos = self.data.get("watermark_position", "bottomright")
            size = self.data.get("watermark_size", "medium")

            success, stderr, self.output_path, meta_title = await watermark(
                self.input_path, self.download_dir, safe_title, ext, wtype, wcontent, pos, size,
                self.user_id, self.active_client, progress_callback=ffmpeg_progress
            )
            self.metadata["title"] = meta_title

        elif self.media_type == "convert":
            await self._update_status(
                "🔀 **Converting Media...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> Initializing video stream processor...\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
            from tools.FileConverter import convert
            target_format = self.data.get("target_format", "mkv")

            success, stderr, self.output_path, meta_title = await convert(
                self.input_path, self.download_dir, safe_title, target_format,
                progress_callback=ffmpeg_progress,
                session_data=self.data,
            )
            self.metadata["title"] = meta_title

        elif self.media_type == "extract_subtitles":
            await self._update_status(
                "📝 **Extracting Subtitles...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> Scanning video streams for text tracks...\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
            from tools.SubtitleExtractor import extract_subtitles

            success, stderr, self.output_path, meta_title = await extract_subtitles(
                self.input_path, self.download_dir, safe_title, progress_callback=ffmpeg_progress
            )
            self.metadata["title"] = meta_title

        elif self.media_type == "audio":
            await self._update_status(
                "🎵 **Editing Audio Metadata...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> Injecting metadata tags and cover art...\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
            from tools.AudioMetadataEditor import edit_audio_metadata
            thumb = self.thumb_path if (self.thumb_path and os.path.exists(self.thumb_path)) else None
            success, stderr, self.output_path, meta_title = await edit_audio_metadata(
                self.input_path, self.download_dir, safe_title, ext, self.metadata, thumb, progress_callback=ffmpeg_progress
            )
            self.metadata["title"] = meta_title

        elif self.media_type == "trim":
            await self._update_status(
                "✂️ **Trimming Video...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                f"> ▶️ **Start:** `{self.data.get('trim_start', '00:00:00')}`\n"
                f"> ⏹️ **End:** `{self.data.get('trim_end', '00:00:00')}`\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
            from tools.VideoTrimmer import trim
            success, stderr, self.output_path, meta_title = await trim(
                self.input_path, self.download_dir, safe_title,
                self.data.get("trim_start", "00:00:00"),
                self.data.get("trim_end", "00:00:00"),
                progress_callback=ffmpeg_progress
            )
            self.metadata["title"] = meta_title

        elif self.media_type == "voice_convert":
            await self._update_status(
                "🎙️ **Converting to Voice Note...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> Converting audio to Telegram voice format...\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
            from tools.VoiceNoteConverter import convert_to_voice
            success, stderr, self.output_path, meta_title = await convert_to_voice(
                self.input_path, self.download_dir, safe_title, progress_callback=ffmpeg_progress
            )
            self.metadata["title"] = meta_title

        elif self.media_type == "video_note":
            await self._update_status(
                "⭕ **Converting to Video Note...**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> Cropping to square and encoding round video...\n"
                "\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{XTVEngine.get_signature(mode=self.mode)}"
            )
            from tools.VideoNoteConverter import convert_to_video_note
            success, stderr, self.output_path, meta_title = await convert_to_video_note(
                self.input_path, self.download_dir, safe_title, progress_callback=ffmpeg_progress
            )
            self.metadata["title"] = meta_title

        else:
            cmd, err = await generate_ffmpeg_command(
                input_path=self.input_path,
                output_path=self.output_path,
                metadata=self.metadata,
                thumbnail_path=(
                    self.thumb_path
                    if (
                        self.thumb_path
                        and os.path.exists(self.thumb_path)
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

        if self.media_type == "extract_subtitles" and (
            not os.path.exists(self.output_path) or os.path.getsize(self.output_path) == 0
        ):
            logger.error("Subtitle extraction failed: no subtitles found in stream.")
            await self._update_status("❌ **Extraction Failed**\n\nNo subtitles were found in this video.")
            return False

        return True

    async def _upload_media(self):
        await self._update_status(
            "📤 **Uploading Result...**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Transferring optimized asset to Telegram...\n"
            "\n━━━━━━━━━━━━━━━━━━━━\n"
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
                    with contextlib.suppress(Exception):
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

                # Voice note: send as voice message
                if self.media_type == "voice_convert":
                    media_msg = await self.active_client.send_voice(
                        chat_id=target_chat_id,
                        voice=self.output_path,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            "📤 **Uploading Voice Note...**",
                            self.status_msg,
                            upload_start,
                            self.mode,
                            self.is_priority,
                        ),
                    )
                    break

                # Video note: send as round video
                if self.media_type == "video_note":
                    media_msg = await self.active_client.send_video_note(
                        chat_id=target_chat_id,
                        video_note=self.output_path,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            "📤 **Uploading Video Note...**",
                            self.status_msg,
                            upload_start,
                            self.mode,
                            self.is_priority,
                        ),
                    )
                    break

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
            storage_channel = db_channel_id

            try:
                if db_channel_id:
                    from pyrogram.errors import PeerIdInvalid
                    try:
                        db_msg = await self.client.copy_message(
                            chat_id=db_channel_id,
                            from_chat_id=media_msg.chat.id,
                            message_id=media_msg.id,
                        )
                    except PeerIdInvalid:
                        await self.client.get_chat(db_channel_id)
                        db_msg = await self.client.copy_message(
                            chat_id=db_channel_id,
                            from_chat_id=media_msg.chat.id,
                            message_id=media_msg.id,
                        )
                    saved_file_id = db_msg.id
                else:
                    # Fallback to the chat the user is in if no DB channel is configured
                    # The file was already sent to the user, so we just use that message.
                    # Note: If the user deletes this message from their history, it will break.
                    # But it ensures the file is "saved" in their myfiles automatically right out of the box.
                    storage_channel = target_chat_id
                    saved_file_id = media_msg.id

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
                dest_folder = self.data.get("dest_folder")
                skip_myfiles = False

                # Check if MyFiles system is globally enabled
                myfiles_enabled = await db.get_setting("myfiles_enabled", default=False)
                is_admin = (self.user_id == Config.CEO_ID or self.user_id in Config.ADMIN_IDS)
                if not myfiles_enabled and not is_admin:
                    skip_myfiles = True

                if dest_folder == "none":
                    skip_myfiles = True
                elif dest_folder and dest_folder != "root":
                    from bson.objectid import ObjectId
                    with contextlib.suppress(Exception):
                        folder_id = ObjectId(dest_folder)

                if (not dest_folder or dest_folder == "auto") and not skip_myfiles:
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
                    elif self.media_type == "audio":
                        artist = self.metadata.get("artist", "Unknown Artist").strip()
                        if not artist:
                            artist = "Unknown Artist"
                        folder = await db.folders.find_one({"user_id": self.user_id, "name": artist, "type": "music"})
                        if not folder:
                            res = await db.folders.insert_one({
                                "user_id": self.user_id,
                                "name": artist,
                                "type": "music",
                                "created_at": datetime.datetime.utcnow()
                            })
                            folder_id = res.inserted_id
                        else:
                            folder_id = folder["_id"]

                if not skip_myfiles:
                    # Smart System Filenames & TMDb Integration
                    internal_name = final_filename

                    try:
                        settings = await db.get_settings(self.user_id)
                        system_filename_template = settings.get("templates", {}).get("system_filename")

                        safe_title = re.sub(r'[\\/*?:"<>|,;\'!]', "", self.title) if self.title else ""
                        safe_title = safe_title.replace("&", "and")
                        year_str = str(self.year) if self.year else ""

                        if system_filename_template:
                            # Ensure episode is safely formatted for formatting string dict
                            ep_str_for_sys = "".join([f"E{int(e):02d}" for e in self.episode]) if isinstance(self.episode, list) else f"{self.episode:02d}" if self.episode else ""
                            sys_fmt_dict = {
                                "title": safe_title,
                                "year": year_str,
                                "season": f"{self.season:02d}" if self.season else "",
                                "episode": ep_str_for_sys,
                                "series_name": safe_title if self.media_type == "series" else "",
                            }

                            # Fallback replacing standard brackets if they were used
                            try:
                                base_name = system_filename_template.format(**sys_fmt_dict)
                            except KeyError:
                                # We don't have fmt_dict here anymore, fallback to a safe title format
                                base_name = f"{safe_title}" if safe_title else "unknown"

                            def clean_sys_filename(name, orig_template=""):
                                import re
                                name = re.sub(r'\[\s*\]', '', name)
                                name = re.sub(r'\(\s*\)', '', name)
                                name = re.sub(r'\{\s*\}', '', name)
                                name = re.sub(r'[\._\s]{2,}', " ", name)
                                name = name.strip('._ ')
                                return name

                            file_ext = os.path.splitext(self.output_path)[1].lower() if self.output_path else ".mkv"
                            internal_name = clean_sys_filename(base_name, system_filename_template) + file_ext
                        elif self.title:
                            file_ext = os.path.splitext(self.output_path)[1].lower() if self.output_path else ".mkv"
                            if self.media_type == "series":
                                ep_str = "".join([f"E{int(e):02d}" for e in self.episode]) if isinstance(self.episode, list) else f"E{self.episode:02d}" if self.episode else ""
                                internal_name = f"{self.title} S{self.season:02d}{ep_str}{file_ext}"
                            elif self.year:
                                internal_name = f"{self.title} ({self.year}){file_ext}"
                            else:
                                internal_name = f"{self.title}{file_ext}"
                    except Exception as e:
                        logger.warning(f"Error applying system filename template: {e}")

                    file_data = {
                        "user_id": self.user_id,
                        "file_name": internal_name,
                        "message_id": saved_file_id,
                        "channel_id": storage_channel,
                        "status": status,
                        "folder_id": folder_id,
                        "created_at": datetime.datetime.utcnow(),
                        "expires_at": expiry_date,
                        "tmdb_id": self.tmdb_id,
                        "poster_url": self.poster_url,
                        "media_type": self.media_type,
                        "season": self.season,
                        "episode": self.episode
                    }
                    await db.files.insert_one(file_data)
            except Exception as e:
                logger.error(f"Failed to save file to DB Channel {storage_channel}: {e}")

            # Attach the inserted file to the queue item
            if batch_id and item_id and 'file_data' in locals():
                q_item = queue_manager.batches.get(batch_id).get_item(item_id) if queue_manager.batches.get(batch_id) else None
                if q_item:
                    file_doc = await db.files.find_one({"file_name": file_data["file_name"], "user_id": self.user_id}, sort=[("created_at", -1)])
                    if file_doc:
                        q_item.db_file_id = str(file_doc["_id"])

            if batch_id and item_id:
                if not dumb_channel:
                    queue_manager.update_status(batch_id, item_id, "done_dumb")
                else:
                    queue_manager.update_status(batch_id, item_id, "done_user")

                if queue_manager.is_batch_complete(batch_id) and not getattr(
                    queue_manager.batches.get(batch_id), "summary_sent", False
                ):
                    try:
                        deep_link = None

                        # Gather all successfully processed file IDs from the queue
                        batch_obj = queue_manager.batches.get(batch_id)
                        if batch_obj:
                            success_ids = [getattr(i, "db_file_id", None) for i in batch_obj.items.values() if i.status in ["done", "done_dumb", "done_user"] and getattr(i, "db_file_id", None)]

                            if success_ids:
                                import uuid
                                config = await db.get_public_config() if Config.PUBLIC_MODE else await db.settings.find_one({"_id": "global_settings"})
                                user_doc = await db.get_user(self.user_id)
                                is_premium = user_doc.get("is_premium", False) if user_doc else False
                                plan = user_doc.get("premium_plan", "standard") if is_premium else "free"

                                plan_features = config.get(f"premium_{plan}", {}).get("features", {})
                                batch_sharing_enabled = plan_features.get("batch_sharing", False)
                                has_batch_pro = self.data.get("has_batch_pro", False)
                                is_global_admin = (self.user_id == Config.CEO_ID or self.user_id in Config.ADMIN_IDS)

                                if (batch_sharing_enabled and has_batch_pro) or is_global_admin or plan == "global":
                                    user_settings = await db.get_settings(self.user_id)
                                    use_anon = user_settings.get("link_anonymity", False) if user_settings else False

                                    if use_anon:
                                        group_id = f"{uuid.uuid4().hex[:16]}"
                                    else:
                                        group_id = f"{self.user_id}_{int(datetime.datetime.utcnow().timestamp())}"

                                    group_doc = {
                                        "group_id": group_id,
                                        "user_id": self.user_id,
                                        "files": success_ids,
                                        "created_at": datetime.datetime.utcnow()
                                    }

                                    # Add expiry if auto-expire links is enabled
                                    auto_expire = user_settings.get("privacy_auto_expire_links", False) if user_settings else False
                                    if auto_expire:
                                        dur = user_settings.get("privacy_link_expiry_duration", "24h") if user_settings else "24h"
                                        dur_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
                                        hours = dur_map.get(dur, 24)
                                        group_doc["expires_at"] = datetime.datetime.utcnow() + datetime.timedelta(hours=hours)

                                    await db.file_groups.insert_one(group_doc)

                                    bot_me = await self.client.get_me()
                                    bot_username = bot_me.username
                                    deep_link = f"https://t.me/{bot_username}?start=group_{group_id}"

                        summary_msg = queue_manager.get_batch_summary(batch_id, usage_text, deep_link)
                        await self.client.send_message(
                            self.user_id, summary_msg, disable_web_page_preview=True
                        )
                        with contextlib.suppress(Exception):
                            await self.client.send_sticker(self.user_id, "CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")
                        if queue_manager.batches.get(batch_id):
                            queue_manager.batches.get(batch_id).summary_sent = True
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
                        with contextlib.suppress(Exception):
                            await wait_msg.delete()

                    try:
                        from pyrogram.errors import PeerIdInvalid
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
                        except PeerIdInvalid:
                            await self.client.get_chat(dumb_channel)
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
                    with contextlib.suppress(Exception):
                        await self.client.send_sticker(self.user_id, "CAACAgIAAxkBAAEQa0xpgkMvycmQypya3zZxS5rU8tuKBQACwJ0AAjP9EEgYhDgLPnTykDgE")
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

    def _cancel_markup(self):
        """Inline keyboard with a Cancel button bound to this task.

        Returns None when the task has already entered a terminal state so
        final success/error messages don't carry a stale Cancel button.
        """
        if getattr(self, "_terminal_status", False):
            return None
        if not self.status_msg:
            return None
        try:
            from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        except Exception:
            return None
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "❌ Cancel Task",
                callback_data=f"cancel_task_{self.status_msg.id}",
            )
        ]])

    async def _update_status(self, text: str, *, terminal: bool = False):
        from pyrogram.errors import FloodWait, MessageIdInvalid
        if terminal:
            self._terminal_status = True
        markup = self._cancel_markup()
        for _attempt in range(3):
            try:
                if self.status_msg:
                    if markup is not None:
                        await self.status_msg.edit_text(text, reply_markup=markup)
                    else:
                        await self.status_msg.edit_text(text)
                return
            except FloodWait as e:
                logger.warning(f"FloodWait in _update_status: sleeping for {e.value}s")
                await asyncio.sleep(e.value + 1)
            except MessageIdInvalid:
                logger.warning("MessageIdInvalid in _update_status: message was likely deleted.")
                return
            except MessageNotModified:
                return
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
            with contextlib.suppress(Exception):
                await self.active_client.delete_channel(self.tunnel_id)

        if self.data.get("extract_dir") and self.data.get("batch_id"):
            extract_dir = self.data.get("extract_dir")
            batch_id = self.data.get("batch_id")

            if queue_manager.is_batch_complete(batch_id) and os.path.exists(extract_dir):
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

@Client.on_callback_query(lambda _, __, q: q.data and q.data.startswith("cancel_task_"))
async def handle_cancel_task(client, callback_query):
    """User pressed Cancel Task on a status message. Cancels the task
    registered for that status-message id (no-op if already done)."""
    from utils.tasks import cancel_by_key

    try:
        status_msg_id = int(callback_query.data.split("_", 2)[2])
    except (ValueError, IndexError):
        await callback_query.answer("Invalid cancel request.", show_alert=False)
        return

    cancelled = cancel_by_key(status_msg_id)
    if cancelled:
        await callback_query.answer("⛔️ Cancelling task...", show_alert=False)
    else:
        await callback_query.answer(
            "Task already finished or not cancellable.", show_alert=False
        )


async def process_file(client, message, data):
    """Entry point for file processing. Wrapped to ensure any unexpected
    failure (e.g. DB down before TaskProcessor can take over) still lands
    with a user-facing message instead of dying silently in a spawned task."""
    user_id = message.from_user.id if message.from_user else message.chat.id

    try:
        await db.ensure_user(
            user_id=user_id,
            first_name=message.from_user.first_name if message.from_user else message.chat.title,
            username=message.from_user.username if message.from_user else None,
            last_name=message.from_user.last_name if message.from_user else None,
            language_code=message.from_user.language_code if message.from_user else None,
            is_bot=message.from_user.is_bot if message.from_user else False,
        )
    except Exception as e:
        logger.exception(f"ensure_user failed for {user_id}: {e}")
        with contextlib.suppress(Exception):
            await message.edit_text(
                "❌ **Database Error**\n\n"
                "Could not initialize your session. Please try again in a moment.\n"
                "If this persists, notify an admin."
            )
        return

    processor = TaskProcessor(client, message, data)
    try:
        await processor.run()
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await message.edit_text("⛔️ **Task Cancelled** by user.")
        raise
    except Exception as e:
        logger.exception(f"process_file uncaught for user={user_id}: {e}")
        with contextlib.suppress(Exception):
            await message.edit_text(
                f"❌ **Unexpected Error**\n\n`{type(e).__name__}: {e}`\n\n"
                "The task was aborted. Your quota has been released."
            )

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
