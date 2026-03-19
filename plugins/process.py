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
from utils.ffmpeg_tools import generate_ffmpeg_command, execute_ffmpeg
from utils.progress import progress_for_pyrogram
from utils.XTVcore import XTVEngine
from utils.queue_manager import queue_manager

logger = logging.getLogger("TaskProcessor")

_SEMAPHORES: Dict[int, Dict[str, Optional[asyncio.Semaphore]]] = {}


def get_semaphore(user_id: int, phase: str) -> asyncio.Semaphore:
    if user_id not in _SEMAPHORES:
        _SEMAPHORES[user_id] = {"download": None, "process": None, "upload": None}

    if _SEMAPHORES[user_id][phase] is None:
        _SEMAPHORES[user_id][phase] = asyncio.Semaphore(3)

    return _SEMAPHORES[user_id][phase]


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
        try:
            if not await self._initialize():
                if batch_id and item_id:
                    queue_manager.update_status(batch_id, item_id, "failed")
                return

            async with get_semaphore(self.user_id, "download"):
                if not await self._download_media():
                    if batch_id and item_id:
                        queue_manager.update_status(batch_id, item_id, "failed")
                    return

            async with get_semaphore(self.user_id, "process"):
                await self._prepare_resources()
                if not await self._process_media():
                    if batch_id and item_id:
                        queue_manager.update_status(batch_id, item_id, "failed")
                    return

            async with get_semaphore(self.user_id, "upload"):
                await self._upload_media()

        except Exception as e:
            logger.exception(f"Critical error in task for user {self.user_id}: {e}")
            await self._update_status(f"❌ **Critical System Error**\n\n`{str(e)}`")
            if batch_id and item_id:
                queue_manager.update_status(batch_id, item_id, "failed")
        finally:
            await self._cleanup()
            if batch_id and queue_manager.is_batch_complete(batch_id):
                try:
                    usage = await db.get_user_usage(self.user_id)
                    config = await db.get_public_config()
                    daily_egress_mb_limit = config.get("daily_egress_mb", 0)
                    daily_file_count_limit = config.get("daily_file_count", 0)
                    global_limit_mb = await db.get_global_daily_egress_limit()

                    user_files = usage.get("file_count", 0)
                    user_egress_mb = usage.get("egress_mb", 0.0)

                    if self.user_id == Config.CEO_ID or self.user_id in Config.ADMIN_IDS:
                        if global_limit_mb > 0:
                            limit_str = f"{global_limit_mb} MB"
                            if global_limit_mb >= 1024:
                                limit_str = f"{global_limit_mb / 1024:.2f} GB"
                            used_str = f"{user_egress_mb:.2f} MB"
                            if user_egress_mb >= 1024:
                                used_str = f"{user_egress_mb / 1024:.2f} GB"
                            usage_text = f"Today: {user_files} files · {used_str} used of {limit_str} (Global Limit)"
                        else:
                            usage_text = f"Today: {user_files} files · {user_egress_mb:.2f} MB used (Unlimited)"
                    else:
                        if daily_egress_mb_limit <= 0 and daily_file_count_limit <= 0 and global_limit_mb <= 0:
                            usage_text = f"Today: {user_files} files · {user_egress_mb:.2f} MB used (No limits set)"
                        else:
                            limit_to_show = daily_egress_mb_limit
                            if global_limit_mb > 0 and (daily_egress_mb_limit <= 0 or global_limit_mb < daily_egress_mb_limit):
                                limit_to_show = global_limit_mb
                            if limit_to_show > 0:
                                limit_str = f"{limit_to_show} MB"
                                if limit_to_show >= 1024:
                                    limit_str = f"{limit_to_show / 1024:.2f} GB"
                            else:
                                limit_str = "Unlimited"
                            used_str = f"{user_egress_mb:.2f} MB"
                            if user_egress_mb >= 1024:
                                used_str = f"{user_egress_mb / 1024:.2f} GB"
                            usage_text = f"Today: {user_files} files · {used_str} used of {limit_str}"

                    summary_msg = queue_manager.get_batch_summary(batch_id, usage_text)
                    await self.client.send_message(self.user_id, summary_msg)
                except Exception as e:
                    logger.warning(f"Failed to send early batch completion msg: {e}")

    async def _initialize(self) -> bool:
        if not shutil.which("ffmpeg"):
            try:
                await self.message.edit_text(
                    "❌ **System Error**\n\n`ffmpeg` binary not found. Contact administrator."
                )
            except MessageNotModified:
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

        # If we have a local_file_path (from archive extraction), just move it instead of downloading
        if self.data.get("local_file_path"):
            local_path = self.data.get("local_file_path")
            if os.path.exists(local_path):
                import shutil
                # Use asyncio.to_thread to prevent blocking the event loop on large files
                await asyncio.to_thread(shutil.move, local_path, self.input_path)
                file_size = os.path.getsize(self.input_path)
                logger.info(f"Local file moved: {self.input_path} ({file_size} bytes)")

                # We need to artificially set file_size on the dummy message object so cleanup/quota works later
                if self.file_message:
                    # Create a dummy object with file_size attribute to satisfy quota check
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
                with open(self.thumb_path, "wb") as f:
                    f.write(thumb_binary)
            elif self.poster_url:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(self.poster_url) as resp:
                            if resp.status == 200:
                                with open(self.thumb_path, "wb") as f:
                                    f.write(await resp.read())
                except Exception as e:
                    logger.warning(f"Failed to download poster: {e}")

        safe_title = re.sub(r'[\\/*?:"<>|]', "", self.title)
        safe_title = safe_title.replace("&", "and")

        ext = ".mkv" if not self.is_subtitle else ".srt"
        if not self.is_subtitle and self.original_name:
            orig_ext = os.path.splitext(self.original_name)[1].lower()
            if orig_ext:
                ext = orig_ext

        if self.message.photo:
            ext = ".jpg"

        season_str = f"S{self.season:02d}" if self.season else ""
        episode_str = f"E{self.episode:02d}" if self.episode else ""
        season_episode = f"{season_str}{episode_str}"
        year_str = str(self.year) if self.year else ""

        fmt_dict = {
            "Title": safe_title,
            "Year": f"({year_str})" if year_str else "",
            "Quality": self.quality,
            "Season": season_str,
            "Episode": episode_str,
            "Season_Episode": season_episode,
            "Language": self.language,
            "Channel": self.channel,
            "filename": (
                os.path.splitext(self.original_name)[0] if self.original_name else ""
            ),
        }

        if self.media_type == "general":
            template = self.data.get("general_name", "{filename}")
            try:
                base_name = template.format(**fmt_dict)
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
            target_ext = f".{self.data.get('target_format', 'mkv')}"
            final_filename = f"{safe_title}{target_ext}"
            meta_title = f"{safe_title}"

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
            except KeyError as e:
                logger.warning(
                    f"KeyError {e} in template '{template}', using fallback."
                )
                base_name = (
                    f"{safe_title}.{season_episode}.{self.quality}_[{self.channel}]"
                    if not self.is_subtitle
                    else f"{safe_title}.{season_episode}.{self.language}"
                )

            if " " not in template and "." in template:
                base_name = base_name.replace(" ", ".")
                if "_" not in template:
                    base_name = base_name.replace("_", ".")
            base_name = base_name.replace("..", ".").replace(" .", ".").replace(". ", ".")

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
                if " " not in template and "." in template:
                    base_name = base_name.replace(" ", ".")
                    if "_" not in template:
                        base_name = base_name.replace("_", ".")
                base_name = re.sub(r"\s+", " ", base_name).strip()
                base_name = (
                    base_name.replace("..", ".").replace(" .", ".").replace(". ", ".")
                )
            except KeyError as e:
                logger.warning(
                    f"KeyError {e} in template '{template}', using fallback."
                )
                base_name = (
                    f"{safe_title}.{year_str}.{self.quality}_[{self.channel}]"
                    if not self.is_subtitle
                    else f"{safe_title}.{year_str}.{self.language}"
                )
                if " " not in template and "." in template:
                    base_name = base_name.replace(" ", ".")
                    if "_" not in template:
                        base_name = base_name.replace("_", ".")
                base_name = base_name.replace("..", ".").replace(" .", ".").replace(". ", ".")

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
            else:
                cmd.extend(["-c", "copy"])

            cmd.append(self.output_path)
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

        success, stderr = await execute_ffmpeg(cmd)
        if not success:
            err_msg = stderr.decode() if stderr else "Unknown Error"
            logger.error(f"FFmpeg execution failed: {err_msg}")
            await self._update_status(
                "❌ **Transcoding Failed**\n\nEngine reported an error during processing."
            )
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
                    ),
                )

            if is_tunneling:
                try:
                    await self.client.copy_message(
                        chat_id=self.user_id,
                        from_chat_id=self.tunnel_id,
                        message_id=media_msg.id,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to copy tunneled file to user {self.user_id}: {e}"
                    )
                    await self.client.send_message(
                        self.user_id,
                        f"❌ **Delivery Error**\n\nThe file was processed successfully but the bot failed to deliver it to you from the tunnel. Error: `{e}`",
                    )

            # --- USAGE TRACKING INJECTION ---
            usage_text = ""
            try:
                # Get the original file size from the message to release the reservation
                original_size = 0
                if self.file_message:
                    media = self.file_message.document or self.file_message.video or self.file_message.audio or self.file_message.photo
                    original_size = getattr(media, "file_size", 0) if media else 0

                # Update usage stats using the actual output size, and release the original reservation
                processed_size = os.path.getsize(self.output_path)
                await db.update_usage(self.user_id, processed_size, reserved_file_size_bytes=original_size)

                # Set success flag so cleanup doesn't release quota again
                self.processing_successful = True

                # Add usage to success message
                usage = await db.get_user_usage(self.user_id)
                config = await db.get_public_config()

                daily_egress_mb_limit = config.get("daily_egress_mb", 0)
                daily_file_count_limit = config.get("daily_file_count", 0)
                global_limit_mb = await db.get_global_daily_egress_limit()

                user_files = usage.get("file_count", 0)
                user_egress_mb = usage.get("egress_mb", 0.0)

                if self.user_id == Config.CEO_ID or self.user_id in Config.ADMIN_IDS:
                    if global_limit_mb > 0:
                        limit_str = f"{global_limit_mb} MB"
                        if global_limit_mb >= 1024:
                            limit_str = f"{global_limit_mb / 1024:.2f} GB"

                        used_str = f"{user_egress_mb:.2f} MB"
                        if user_egress_mb >= 1024:
                            used_str = f"{user_egress_mb / 1024:.2f} GB"

                        usage_text = f"Today: {user_files} files · {used_str} used of {limit_str} (Global Limit)"
                    else:
                        usage_text = f"Today: {user_files} files · {user_egress_mb:.2f} MB used (Unlimited)"
                else:
                    if daily_egress_mb_limit <= 0 and daily_file_count_limit <= 0 and global_limit_mb <= 0:
                        usage_text = f"Today: {user_files} files · {user_egress_mb:.2f} MB used (No limits set)"
                    else:
                        limit_to_show = daily_egress_mb_limit
                        if global_limit_mb > 0 and (daily_egress_mb_limit <= 0 or global_limit_mb < daily_egress_mb_limit):
                            limit_to_show = global_limit_mb

                        if limit_to_show > 0:
                            limit_str = f"{limit_to_show} MB"
                            if limit_to_show >= 1024:
                                limit_str = f"{limit_to_show / 1024:.2f} GB"
                        else:
                            limit_str = "Unlimited"

                        used_str = f"{user_egress_mb:.2f} MB"
                        if user_egress_mb >= 1024:
                            used_str = f"{user_egress_mb / 1024:.2f} GB"

                        usage_text = f"Today: {user_files} files · {used_str} used of {limit_str}"

            except Exception as usage_e:
                logger.error(
                    f"Error fetching/updating usage for success message: {usage_e}"
                )
            # --- END USAGE TRACKING INJECTION ---

            await self.status_msg.delete()

            batch_id = self.data.get("batch_id")
            item_id = self.data.get("item_id")
            dumb_channel = self.data.get("dumb_channel")

            if batch_id and item_id:
                if not dumb_channel:
                    queue_manager.update_status(batch_id, item_id, "done_dumb")
                else:
                    queue_manager.update_status(batch_id, item_id, "done_user")

                if queue_manager.is_batch_complete(batch_id):
                    try:
                        summary_msg = queue_manager.get_batch_summary(batch_id, usage_text)
                        await self.client.send_message(
                            self.user_id, summary_msg
                        )
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
                    # Fallback if no batch mechanism (should be rare)
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
        try:
            await self.status_msg.edit_text(text)
        except Exception as e:
            logger.warning(f"Failed to update status message: {e}")

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

        # Clean up the extraction directory if this is the last item in the batch
        if self.data.get("extract_dir") and self.data.get("batch_id"):
            extract_dir = self.data.get("extract_dir")
            batch_id = self.data.get("batch_id")

            # Use queue_manager to check if this is the last pending item
            # If all other items in the batch are completed or failed, we can safely delete the dir
            if queue_manager.is_batch_complete(batch_id):
                if os.path.exists(extract_dir):
                    try:
                        shutil.rmtree(extract_dir, ignore_errors=True)
                    except Exception as e:
                        logger.warning(f"Failed to remove extraction directory {extract_dir}: {e}")

        # If processing didn't complete successfully, release the reserved quota
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
    # Quota check and reservation is now done upstream in handle_file_upload
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
