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

from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.types import Message
from config import Config
from database import db
from utils.ffmpeg_tools import generate_ffmpeg_command, execute_ffmpeg
from utils.progress import progress_for_pyrogram
from utils.XTVcore import XTVEngine

# Configure structured logger
logger = logging.getLogger("TaskProcessor")

# Global Concurrency Control
# Semaphores are initialized lazily to ensure they bind to the correct event loop
_SEMAPHORES = {
    "download": None,
    "process": None,
    "upload": None
}

def get_semaphore(phase: str) -> asyncio.Semaphore:
    """Retrieve or create the semaphore for the given phase."""
    if _SEMAPHORES[phase] is None:
        _SEMAPHORES[phase] = asyncio.Semaphore(3)
    return _SEMAPHORES[phase]

class TaskProcessor:
    """
    Handles the end-to-end processing of a media file:
    Download -> Metadata/Thumbnail Preparation -> FFmpeg Processing -> Upload.
    Designed with a focus on clean architecture, robust error handling, and business-grade feedback.
    """

    def __init__(self, client: Client, message: Message, data: Dict[str, Any]):
        self.client = client
        self.message = message
        self.data = data

        self.user_id = message.chat.id
        self.message_id = message.id
        self.start_time = time.time()

        # Paths
        self.download_dir = Config.DOWNLOAD_DIR
        self.input_path: Optional[str] = None
        self.output_path: Optional[str] = None
        self.thumb_path: Optional[str] = None

        # Data Extraction
        self.media_type = data.get("type")
        self.is_subtitle = data.get("is_subtitle", False)
        self.language = data.get("language", "en")
        self.tmdb_id = data.get("tmdb_id")
        self.title = data.get("title")
        self.year = data.get("year")
        self.poster_url = data.get("poster")
        self.season = data.get("season")
        self.episode = data.get("episode")
        self.quality = data.get("quality", "720p")
        self.file_message = data.get("file_message")
        self.original_name = data.get("original_name", "unknown.mkv")

        # Runtime State
        self.status_msg: Optional[Message] = None
        self.settings: Optional[Dict] = None
        self.templates: Optional[Dict] = None
        self.filename_templates: Optional[Dict] = None
        self.channel: Optional[str] = None

        # Hybrid Workflow Logic
        self.mode = "core"
        self.active_client = self.client

        try:
             # Check for user_bot attached to client
             if getattr(self.client, "user_bot", None):
                 file_size = 0
                 media = self.file_message.document or self.file_message.video
                 if media:
                     file_size = media.file_size

                 # 2000 MB threshold (approx 2GB)
                 if file_size > 2000 * 1024 * 1024:
                     self.mode = "pro"
                     self.active_client = self.client.user_bot
                     logger.info(f"Activated PRO Mode for task {self.message_id} (Size: {file_size})")
        except Exception as e:
            logger.warning(f"Error determining mode: {e}")

    async def run(self):
        """Execute the full processing pipeline with concurrency limits."""
        try:
            # Phase 0: Initialization & Validation
            if not await self._initialize():
                return

            # Phase 1: Download
            # Acquire semaphore only for the duration of the download
            async with get_semaphore("download"):
                if not await self._download_media():
                    return

            # Phase 2: Metadata & Processing
            # Grouping resource prep and ffmpeg under 'process' semaphore
            async with get_semaphore("process"):
                await self._prepare_resources()
                if not await self._process_media():
                    return

            # Phase 3: Upload
            async with get_semaphore("upload"):
                await self._upload_media()

        except Exception as e:
            logger.exception(f"Critical error in task for user {self.user_id}: {e}")
            await self._update_status(f"❌ **Critical System Error**\n\n`{str(e)}`")
        finally:
            self._cleanup()

    async def _initialize(self) -> bool:
        """Check system requirements and initialize status."""
        if not shutil.which("ffmpeg"):
            await self.message.edit_text("❌ **System Error**\n\n`ffmpeg` binary not found. Contact administrator.")
            return False

        self.status_msg = await self.message.edit_text(
            "⏳ **Initializing Task...**\n"
            "Allocating resources and preparing environment.\n\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        # Load settings once
        self.settings = await db.get_settings()
        if self.settings:
            self.templates = self.settings.get("templates", Config.DEFAULT_TEMPLATES)
            self.filename_templates = self.settings.get("filename_templates", Config.DEFAULT_FILENAME_TEMPLATES)
            self.channel = self.settings.get("channel", Config.DEFAULT_CHANNEL)
        else:
            logger.warning("Database settings unavailable, using defaults.")
            self.templates = Config.DEFAULT_TEMPLATES
            self.filename_templates = Config.DEFAULT_FILENAME_TEMPLATES
            self.channel = Config.DEFAULT_CHANNEL

        return True

    async def _download_media(self) -> bool:
        """Download the media file from Telegram."""
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
             if not ext or ext not in ['.srt', '.ass', '.vtt']:
                 ext = ".srt"

        if self.message.photo:
            ext = ".jpg"

        self.input_path = os.path.join(self.download_dir, f"{self.user_id}_{self.message_id}_input{ext}")
        download_start = time.time()

        # Target Message Resolution for Userbot
        target_message = self.file_message
        if self.mode == "pro" and self.message.chat.type == ChatType.PRIVATE:
            try:
                bot_info = await self.client.get_me()
                bot_username = bot_info.username

                found = False
                original_media = self.file_message.document or self.file_message.video

                if original_media:
                    # Retry logic with delay
                    for attempt in range(3):
                        await asyncio.sleep(2) # Allow time for propagation
                        logger.info(f"Scanning Userbot history... Attempt {attempt+1}")

                        # Scan recent messages in Userbot's chat with Bot to find matching file
                        # Increased limit to ensure we catch it
                        async for msg in self.active_client.get_chat_history(bot_username, limit=50):
                            media = msg.document or msg.video
                            if media and media.file_unique_id == original_media.file_unique_id:
                                target_message = msg
                                found = True
                                logger.info(f"Resolved Userbot message ID: {msg.id}")
                                break
                        if found: break

                if not found:
                    logger.warning("Could not resolve message in Userbot history. Using original (risky).")
            except Exception as e:
                logger.error(f"Error resolving Userbot message: {e}")

        try:
            downloaded_path = await self.active_client.download_media(
                target_message,
                file_name=self.input_path,
                progress=progress_for_pyrogram,
                progress_args=("📥 **Downloading Media Content...**", self.status_msg, download_start, self.mode)
            )

            if downloaded_path and os.path.exists(downloaded_path):
                self.input_path = downloaded_path
                file_size = os.path.getsize(self.input_path)
                logger.info(f"Download success: {self.input_path} ({file_size} bytes)")

                if file_size == 0:
                    await self._update_status("❌ **Download Integrity Error**\n\nFile size is 0 bytes.")
                    return False
                return True
            else:
                logger.error(f"Download returned path but file missing: {self.input_path}")
                await self._update_status("❌ **Download Verification Failed**\n\nFile not found on disk.")
                return False

        except Exception as e:
            logger.error(f"Download failed: {e}")
            await self._update_status(f"❌ **Network Error during Download**\n\n`{e}`")
            return False

    async def _prepare_resources(self):
        """Prepare thumbnail and calculate final filename/metadata."""
        await self._update_status(
            "🎨 **Preparing Metadata Assets**\n\n"
            "Optimizing thumbnails and configuring metadata...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        # Thumbnail Handling
        self.thumb_path = os.path.join(self.download_dir, f"{self.user_id}_{self.message_id}_thumb.jpg")

        if not self.is_subtitle:
            thumb_binary = self.settings.get("thumbnail_binary") if self.settings else None

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

        # Filename & Metadata Calculation
        sanitized_title = self.title.replace(" ", ".")
        safe_title = re.sub(r'[\\/*?:"<>|]', '', sanitized_title)

        # Determine the file extension based on input or type
        ext = ".mkv" if not self.is_subtitle else ".srt"
        if not self.is_subtitle and self.original_name:
             orig_ext = os.path.splitext(self.original_name)[1].lower()
             if orig_ext:
                 ext = orig_ext

        if self.message.photo:
            ext = ".jpg"

        # Common format variables
        season_str = f"S{self.season:02d}" if self.season else ""
        episode_str = f"E{self.episode:02d}" if self.episode else ""
        season_episode = f"{season_str}{episode_str}"
        year_str = str(self.year) if self.year else ""

        # Formatting dictionary
        fmt_dict = {
            "Title": safe_title,
            "Year": f"({year_str})" if year_str else "",
            "Quality": self.quality,
            "Season": season_str,
            "Episode": episode_str,
            "Season_Episode": season_episode,
            "Language": self.language,
            "Channel": self.channel
        }

        # Clean up empty year space if needed
        # When year is empty, template.format(**fmt_dict) will result in "._{Channel}" or similar.
        # This will be cleaned below.

        # Select correct template and generate final filename
        if self.media_type == "series":
            if self.is_subtitle:
                template = self.filename_templates.get("subtitles_series", Config.DEFAULT_FILENAME_TEMPLATES["subtitles_series"])
            else:
                template = self.filename_templates.get("series", Config.DEFAULT_FILENAME_TEMPLATES["series"])

            # Use format with fallback for missing keys
            try:
                base_name = template.format(**fmt_dict)
            except KeyError as e:
                logger.warning(f"KeyError {e} in template '{template}', using fallback.")
                base_name = f"{safe_title}.{season_episode}.{self.quality}_[{self.channel}]" if not self.is_subtitle else f"{safe_title}.{season_episode}.{self.language}"

            final_filename = f"{base_name}{ext}"
            meta_title = self.templates.get("title", "").format(title=self.title, season_episode=season_episode)
        else:
            personal_type = self.data.get("personal_type")
            if personal_type:
                key = f"personal_{personal_type}"
                template = self.filename_templates.get(key, Config.DEFAULT_FILENAME_TEMPLATES[key])
            elif self.is_subtitle:
                template = self.filename_templates.get("subtitles_movies", Config.DEFAULT_FILENAME_TEMPLATES["subtitles_movies"])
            else:
                template = self.filename_templates.get("movies", Config.DEFAULT_FILENAME_TEMPLATES["movies"])

            try:
                base_name = template.format(**fmt_dict)
                # Cleanup potential double spaces from missing year
                base_name = re.sub(r'\s+', ' ', base_name).strip()
                base_name = base_name.replace(" .", ".").replace("..", ".")
            except KeyError as e:
                logger.warning(f"KeyError {e} in template '{template}', using fallback.")
                base_name = f"{safe_title}.{year_str}.{self.quality}_[{self.channel}]" if not self.is_subtitle else f"{safe_title}.{year_str}.{self.language}"

            final_filename = f"{base_name}{ext}"
            meta_title = self.templates.get("title", "").format(title=self.title, season_episode="").strip()

        self.output_path = os.path.join(self.download_dir, final_filename)

        # Conflict Resolution
        if os.path.exists(self.output_path):
             self.output_path = os.path.join(self.download_dir, f"{int(time.time())}_{final_filename}")

        self.metadata = {
            "title": meta_title,
            "author": self.templates.get("author", ""),
            "artist": self.templates.get("artist", ""),
            "encoded_by": "@XTVglobal",
            "video_title": self.templates.get("video", "Encoded By:- @XTVglobal"),
            "audio_title": self.templates.get("audio", "Audio By:- @XTVglobal - {lang}"),
            "subtitle_title": self.templates.get("subtitle", "Subtitled By:- @XTVglobal - {lang}"),
            "default_language": "English",
            "copyright": self.templates.get("copyright", "@XTVglobal")
        }

    async def _process_media(self) -> bool:
        """Run the FFmpeg processing command."""
        await self._update_status(
            "⚙️ **Executing Transcoding Matrix**\n\n"
            "Injecting metadata and optimizing container...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        cmd, err = await generate_ffmpeg_command(
            input_path=self.input_path,
            output_path=self.output_path,
            metadata=self.metadata,
            thumbnail_path=self.thumb_path if (os.path.exists(self.thumb_path) and not self.is_subtitle) else None
        )

        if not cmd:
            logger.error(f"FFmpeg command generation failed: {err}")
            await self._update_status(f"❌ **Processing Configuration Error**\n\n`{err}`")
            return False

        success, stderr = await execute_ffmpeg(cmd)
        if not success:
            err_msg = stderr.decode() if stderr else "Unknown Error"
            logger.error(f"FFmpeg execution failed: {err_msg}")
            await self._update_status("❌ **Transcoding Failed**\n\nEngine reported an error during processing.")
            return False

        return True

    async def _upload_media(self):
        """Upload the final file."""
        await self._update_status(
            "📤 **Finalizing & Uploading**\n\n"
            "Transferring optimized asset to cloud...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        upload_start = time.time()
        final_filename = os.path.basename(self.output_path)

        # Caption Generation
        caption = self._generate_caption(final_filename)

        # Target Chat Resolution
        target_chat_id = self.user_id
        if self.mode == "pro" and self.message.chat.type == ChatType.PRIVATE:
            try:
                bot_info = await self.client.get_me()
                target_chat_id = bot_info.username
            except Exception as e:
                logger.error(f"Failed to resolve bot username for upload: {e}")

        try:
            thumb = self.thumb_path if (self.thumb_path and os.path.exists(self.thumb_path) and not self.is_subtitle) else None

            send_as = self.data.get("send_as")

            if send_as == "photo" or (self.message.photo and not send_as):
                await self.active_client.send_photo(
                    chat_id=target_chat_id,
                    photo=self.output_path,
                    caption=caption,
                    progress=progress_for_pyrogram,
                    progress_args=("📤 **Uploading Photo...**", self.status_msg, upload_start, self.mode)
                )
            else:
                await self.active_client.send_document(
                    chat_id=target_chat_id,
                    document=self.output_path,
                    thumb=thumb,
                    caption=caption,
                    progress=progress_for_pyrogram,
                    progress_args=("📤 **Uploading Final File...**", self.status_msg, upload_start, self.mode)
                )

            await self.status_msg.delete()
            await self.message.reply_text(
                "✅ **Processing Complete**\n\n"
                f"📂 **File:** `{final_filename}`\n\n"
            )

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            await self._update_status(f"❌ **Upload Protocol Failed**\n\n`{e}`")

    def _generate_caption(self, filename: str) -> str:
        """Generate a secure caption based on templates."""
        template = self.templates.get("caption", "{random}")

        if "{random}" in template or template == "{random}":
            return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

        file_size = os.path.getsize(self.output_path)
        size_str = self._humanbytes(file_size)

        return template.format(
            filename=filename,
            size=size_str,
            duration="", # Placeholder
            random=''.join(random.choices(string.ascii_letters + string.digits, k=8))
        )

    @staticmethod
    def _humanbytes(size: int) -> str:
        if not size: return ""
        power = 2**10
        n = 0
        dic_power = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return str(round(size, 2)) + " " + dic_power[n] + 'B'

    async def _update_status(self, text: str):
        try:
            await self.status_msg.edit_text(text)
        except Exception as e:
            logger.warning(f"Failed to update status message: {e}")

    def _cleanup(self):
        """Clean up temporary files."""
        for path in [self.input_path, self.output_path, self.thumb_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {path}: {e}")

# Entry point for the plugin system
async def process_file(client, message, data):
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
