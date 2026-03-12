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
from utils.queue_manager import queue_manager

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
        self.original_name = data.get("original_name", "unknown.mkv")

        # Fallback for title if not provided (e.g. in Audio, Convert, Watermark modes)
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

        # Runtime State
        self.status_msg: Optional[Message] = None
        self.settings: Optional[Dict] = None
        self.templates: Optional[Dict] = None
        self.filename_templates: Optional[Dict] = None
        self.channel: Optional[str] = None

        # Hybrid Workflow Logic
        self.mode = "core"
        self.active_client = self.client
        self.tunnel_id = None
        self.tunneled_message_id = None

        try:
             # Check for user_bot attached to client
             user_bot = getattr(self.client, "user_bot", None)
             if user_bot:
                 file_size = 0
                 media = self.file_message.document or self.file_message.video
                 if media:
                     file_size = media.file_size

                 # 2000 MB threshold (approx 2GB)
                 if file_size > 2000 * 1000 * 1000:
                     self.mode = "pro"
                     self.active_client = user_bot
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
            await self._cleanup()

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

        # Load settings once (with user_id support for PUBLIC_MODE)
        self.settings = await db.get_settings(self.user_id)
        if self.settings:
            self.templates = self.settings.get("templates", Config.DEFAULT_TEMPLATES)
            self.filename_templates = self.settings.get("filename_templates", Config.DEFAULT_FILENAME_TEMPLATES)
            self.channel = self.settings.get("channel", Config.DEFAULT_CHANNEL)
        else:
            logger.warning("Database settings unavailable, using defaults.")
            self.templates = Config.DEFAULT_TEMPLATES
            self.filename_templates = Config.DEFAULT_FILENAME_TEMPLATES
            self.channel = Config.DEFAULT_CHANNEL

        # Update rate limit if in Public Mode
        if Config.PUBLIC_MODE:
            await db.update_rate_limit(self.user_id)

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

        # For Audio Metadata Editor
        if self.media_type == "audio":
            if not hasattr(self, "metadata"):
                self.metadata = {}

            if self.data.get("audio_thumb_id"):
                self.thumb_path = os.path.join(self.download_dir, f"{self.user_id}_{self.message_id}_thumb.jpg")
                await self.active_client.download_media(self.data.get("audio_thumb_id"), file_name=self.thumb_path)

            # Setup specific metadata
            self.metadata["title"] = self.data.get("audio_title", "")
            self.metadata["artist"] = self.data.get("audio_artist", "")
            if self.data.get("audio_album"):
                self.metadata["album"] = self.data.get("audio_album", "")

        # Target Message Resolution for Userbot
        target_message = self.file_message
        if self.mode == "pro":
            try:
                # Create Ephemeral Tunnel Channel using Userbot
                bot_me = await self.client.get_me()
                bot_username = bot_me.username

                channel = await self.active_client.create_channel(
                    title=f"𝕏TV Pro Ephemeral {self.message_id}",
                    description="Temporary tunnel for XTV Bot."
                )
                self.tunnel_id = channel.id

                # Add main bot to channel and promote
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
                        can_pin_messages=True
                    )
                )

                # Send a ping from the Userbot to force Telegram to notify the Main Bot (as an admin) of the channel's existence.
                ping_msg = await self.active_client.send_message(self.tunnel_id, "ping", disable_notification=True)
                await ping_msg.delete()
                await asyncio.sleep(1) # Give Pyrogram a moment to process the update

                # Main Bot copies message to tunnel
                tunnel_msg = await self.client.copy_message(
                    chat_id=self.tunnel_id,
                    from_chat_id=self.file_message.chat.id,
                    message_id=self.file_message.id
                )

                # Userbot retrieves the copied message
                target_message = await self.active_client.get_messages(
                    chat_id=self.tunnel_id,
                    message_ids=tunnel_msg.id
                )

                if not target_message or target_message.empty:
                    logger.error(f"Could not fetch copied message {tunnel_msg.id} from tunnel {self.tunnel_id} via Userbot.")
                    await self._update_status("❌ **Tunnel Resolution Error**\n\nUserbot failed to see the file in the internal tunnel.")
                    return False

                self.tunneled_message_id = tunnel_msg.id

            except Exception as e:
                logger.error(f"Error creating/resolving Ephemeral Tunnel: {e}")
                await self._update_status(f"❌ **Tunnel Bridge Error**\n\n`{e}`")
                return False

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
        if not self.thumb_path:
            self.thumb_path = os.path.join(self.download_dir, f"{self.user_id}_{self.message_id}_thumb.jpg")

        if not self.is_subtitle and self.media_type != "audio":
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

        # Only sanitize filesystem-illegal characters. DO NOT replace spaces with dots by default.
        # The template itself should dictate formatting.
        safe_title = re.sub(r'[\\/*?:"<>|]', '', self.title)

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
            "Channel": self.channel,
            "filename": os.path.splitext(self.original_name)[0] if self.original_name else ""
        }

        # Select correct template and generate final filename
        if self.media_type == "general":
            template = self.data.get("general_name", "{filename}")
            try:
                base_name = template.format(**fmt_dict)
            except KeyError as e:
                logger.warning(f"KeyError {e} in general template '{template}', using fallback.")
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
                template = self.filename_templates.get("subtitles_series", Config.DEFAULT_FILENAME_TEMPLATES["subtitles_series"])
            else:
                template = self.filename_templates.get("series", Config.DEFAULT_FILENAME_TEMPLATES["series"])

            # Use format with fallback for missing keys
            try:
                base_name = template.format(**fmt_dict)
            except KeyError as e:
                logger.warning(f"KeyError {e} in template '{template}', using fallback.")
                base_name = f"{safe_title}.{season_episode}.{self.quality}_[{self.channel}]" if not self.is_subtitle else f"{safe_title}.{season_episode}.{self.language}"

            # If template didn't use spaces, but the user expected dots (e.g. the default `{Title}.{Year}`),
            # make sure the spaces in {Title} match the delimiter used in the template if no spaces exist.
            # But DO NOT mangle brackets like `[{Channel}]`.
            if " " not in template and "." in template:
                base_name = base_name.replace(" ", ".")

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
                if " " not in template and "." in template:
                    base_name = base_name.replace(" ", ".")
                # Cleanup potential double spaces/dots from missing year
                base_name = re.sub(r'\s+', ' ', base_name).strip()
                base_name = base_name.replace("..", ".").replace(" .", ".").replace(". ", ".")
            except KeyError as e:
                logger.warning(f"KeyError {e} in template '{template}', using fallback.")
                base_name = f"{safe_title}.{year_str}.{self.quality}_[{self.channel}]" if not self.is_subtitle else f"{safe_title}.{year_str}.{self.language}"
                if " " not in template and "." in template:
                    base_name = base_name.replace(" ", ".")

            final_filename = f"{base_name}{ext}"
            meta_title = self.templates.get("title", "").format(title=self.title, season_episode="").strip()

        self.output_path = os.path.join(self.download_dir, final_filename)

        # Conflict Resolution
        if os.path.exists(self.output_path):
             self.output_path = os.path.join(self.download_dir, f"{int(time.time())}_{final_filename}")

        if not hasattr(self, "metadata"):
            self.metadata = {}

        # Don't overwrite title/artist if set by audio editor
        if "title" not in self.metadata:
            self.metadata["title"] = meta_title
        if "artist" not in self.metadata:
            self.metadata["artist"] = self.templates.get("artist", "")

        self.metadata.update({
            "author": self.templates.get("author", ""),
            "encoded_by": "@XTVglobal",
            "video_title": self.templates.get("video", "Encoded By:- @XTVglobal"),
            "audio_title": self.templates.get("audio", "Audio By:- @XTVglobal - {lang}"),
            "subtitle_title": self.templates.get("subtitle", "Subtitled By:- @XTVglobal - {lang}"),
            "default_language": "English",
            "copyright": self.templates.get("copyright", "@XTVglobal")
        })

    async def _process_media(self) -> bool:
        """Run the FFmpeg processing command."""
        await self._update_status(
            "⚙️ **Executing Transcoding Matrix**\n\n"
            "Injecting metadata and optimizing container...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{XTVEngine.get_signature(mode=self.mode)}"
        )

        if self.media_type == "watermark":
            wtype = self.data.get("watermark_type")
            wcontent = self.data.get("watermark_content")

            cmd = ["ffmpeg", "-y", "-i", self.input_path]

            if wtype == "text":
                # Ensure the text is escaped for ffmpeg
                escaped_text = wcontent.replace("'", "\\'").replace(":", "\\:")
                # Draw text centered, simple styling
                cmd.extend(["-vf", f"drawtext=text='{escaped_text}':fontcolor=white@0.8:fontsize=h/10:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5:boxborderw=5"])
            else:
                # Image watermark
                watermark_path = os.path.join(self.download_dir, f"{self.user_id}_wm_overlay.png")
                # We need to download it first
                if wcontent:
                    await self.active_client.download_media(wcontent, file_name=watermark_path)

                if os.path.exists(watermark_path):
                    cmd.extend(["-i", watermark_path, "-filter_complex", "overlay=W-w-10:H-h-10"]) # Bottom right overlay
                else:
                    logger.error("Watermark overlay image missing.")

            cmd.append(self.output_path)
            err = None
        elif self.media_type == "convert":
            # For conversion, use a simplified ffmpeg command bypassing complex metadata mapping
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
                thumbnail_path=self.thumb_path if (os.path.exists(self.thumb_path) and not self.is_subtitle and self.media_type != "convert") else None
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

        # Target Chat Resolution & Tunneling
        # In Core mode: Bot uploads directly to the User (or group).
        # In Pro mode: Userbot uploads to the designated tunnel channel,
        # then the Bot copies the file to the User. This hides the Userbot's identity from the user.
        target_chat_id = self.user_id
        is_tunneling = False

        if self.mode == "pro":
            is_tunneling = True
            if self.tunnel_id:
                target_chat_id = self.tunnel_id
            else:
                await self._update_status("❌ **Upload Configuration Error**\n\nPro Tunnel ID not initialized.")
                return

        try:
            # Force Userbot to cache peer if it doesn't have it (e.g. ephemeral restart issue)
            if is_tunneling:
                try:
                    # Userbot already cached this during download, but we wrap it just in case
                    pass
                except Exception:
                    pass

            thumb = self.thumb_path if (self.thumb_path and os.path.exists(self.thumb_path) and not self.is_subtitle) else None

            send_as = self.data.get("send_as")

            # Determine mime/ext for smart sending
            file_ext = os.path.splitext(self.output_path)[1].lower()
            is_vid_ext = file_ext in [".mp4", ".mkv", ".webm", ".avi", ".mov"]
            is_aud_ext = file_ext in [".mp3", ".flac", ".m4a", ".wav", ".ogg"]
            is_img_ext = file_ext in [".jpg", ".jpeg", ".png", ".webp"]

            if send_as == "photo" or (self.message.photo and not send_as and not is_vid_ext and not is_aud_ext):
                media_msg = await self.active_client.send_photo(
                    chat_id=target_chat_id,
                    photo=self.output_path,
                    caption=caption,
                    progress=progress_for_pyrogram,
                    progress_args=("📤 **Uploading Photo (Tunneling)...**" if is_tunneling else "📤 **Uploading Photo...**", self.status_msg, upload_start, self.mode)
                )
            elif send_as == "media":
                if is_img_ext:
                    media_msg = await self.active_client.send_photo(
                        chat_id=target_chat_id,
                        photo=self.output_path,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=("📤 **Uploading Photo (Tunneling)...**" if is_tunneling else "📤 **Uploading Photo...**", self.status_msg, upload_start, self.mode)
                    )
                elif is_vid_ext:
                    media_msg = await self.active_client.send_video(
                        chat_id=target_chat_id,
                        video=self.output_path,
                        thumb=thumb,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=("📤 **Uploading Video (Tunneling)...**" if is_tunneling else "📤 **Uploading Video...**", self.status_msg, upload_start, self.mode)
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
                        progress_args=("📤 **Uploading Audio (Tunneling)...**" if is_tunneling else "📤 **Uploading Audio...**", self.status_msg, upload_start, self.mode)
                    )
                else:
                    # Fallback to document if it's media but not recognized as explicit audio/video
                    media_msg = await self.active_client.send_document(
                        chat_id=target_chat_id,
                        document=self.output_path,
                        thumb=thumb,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=("📤 **Uploading Media (Tunneling)...**" if is_tunneling else "📤 **Uploading Media...**", self.status_msg, upload_start, self.mode)
                    )
            else:
                media_msg = await self.active_client.send_document(
                    chat_id=target_chat_id,
                    document=self.output_path,
                    thumb=thumb,
                    caption=caption,
                    progress=progress_for_pyrogram,
                    progress_args=("📤 **Uploading Final File (Tunneling)...**" if is_tunneling else "📤 **Uploading Final File...**", self.status_msg, upload_start, self.mode)
                )

            # If tunneling via Pro mode, the file is now in the internal tunnel channel.
            # The Main Bot must now copy it to the end-user to hide the Userbot.
            # Because both are in the same tunnel channel, the message IDs are identical.
            if is_tunneling:
                try:
                    await self.client.copy_message(
                        chat_id=self.user_id,
                        from_chat_id=self.tunnel_id,
                        message_id=media_msg.id
                    )
                except Exception as e:
                    logger.error(f"Failed to copy tunneled file to user {self.user_id}: {e}")
                    await self.client.send_message(self.user_id, f"❌ **Delivery Error**\n\nThe file was processed successfully but the bot failed to deliver it to you from the tunnel. Error: `{e}`")

            await self.status_msg.delete()

            # Handle Dumb Channel Forwarding if applicable
            batch_id = self.data.get("batch_id")
            item_id = self.data.get("item_id")
            dumb_channel = self.data.get("dumb_channel")

            if batch_id and item_id:
                if not dumb_channel:
                    queue_manager.update_status(batch_id, item_id, "done_dumb")
                else:
                    queue_manager.update_status(batch_id, item_id, "done_user")

                    # Enter wait loop for earlier items in the batch
                    wait_start = time.time()
                    timeout = await db.get_dumb_channel_timeout()
                    wait_msg = None
                    last_wait_text = None

                    while True:
                        blocking_item = queue_manager.get_blocking_item(batch_id, item_id)
                        if not blocking_item:
                            break # We are clear to send

                        if time.time() - wait_start > timeout:
                            logger.warning(f"Timeout waiting for dumb channel upload for {final_filename}")
                            if wait_msg:
                                await wait_msg.delete()
                            break

                        wait_text = f"⏳ **Waiting for {blocking_item.display_name} to finish To send it in the dumb channel**"

                        if not wait_msg:
                            wait_msg = await self.message.reply_text(wait_text)
                            last_wait_text = wait_text
                        elif last_wait_text != wait_text:
                            # Update message if the blocking item changed, catching potential errors
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

                    # Now send to dumb channel
                    try:
                        if is_tunneling:
                            await self.client.copy_message(
                                chat_id=dumb_channel,
                                from_chat_id=self.tunnel_id,
                                message_id=media_msg.id
                            )
                        else:
                            await self.client.copy_message(
                                chat_id=dumb_channel,
                                from_chat_id=media_msg.chat.id,
                                message_id=media_msg.id
                            )
                        queue_manager.update_status(batch_id, item_id, "done_dumb")
                    except Exception as e:
                        logger.error(f"Failed to copy {final_filename} to dumb channel {dumb_channel}: {e}")
                        queue_manager.update_status(batch_id, item_id, "failed", str(e))

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
                    logger.warning(f"Failed to cleanup ephemeral tunnel {self.tunnel_id}: {e}")

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

    async def _cleanup(self):
        """Clean up temporary files and tunnel."""
        for path in [self.input_path, self.output_path, self.thumb_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {path}: {e}")

        # Fallback to ensure tunnel is deleted if process failed mid-way
        if self.mode == "pro" and self.tunnel_id:
            try:
                await self.active_client.delete_channel(self.tunnel_id)
            except Exception:
                pass

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
