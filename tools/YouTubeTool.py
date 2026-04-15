# --- Imports ---
import os
import re
import time
import asyncio
from pyrogram import Client, filters, StopPropagation
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from plugins.user_setup import track_tool_usage
from utils.state import set_state, get_state, get_data, update_data, clear_session
from utils.log import get_logger

# yt-dlp is an optional runtime dependency. Import lazily so main.py can still
# load the module even if the package is missing on the host.
try:
    import yt_dlp  # type: ignore
    _YTDLP_AVAILABLE = True
    _YTDLP_IMPORT_ERROR = None
except Exception as _e:  # pragma: no cover - only triggers when dep is absent
    yt_dlp = None
    _YTDLP_AVAILABLE = False
    _YTDLP_IMPORT_ERROR = str(_e)

logger = get_logger("tools.YouTubeTool")

# --- Constants ---
YT_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?"
    r"(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/\S+",
    re.IGNORECASE,
)

VIDEO_QUALITIES = [
    ("360", "360p"),
    ("480", "480p"),
    ("720", "720p"),
    ("1080", "1080p"),
    ("best", "Best available"),
]

AUDIO_BITRATES = [
    ("128", "128 kbps"),
    ("192", "192 kbps"),
    ("320", "320 kbps"),
]

SUBTITLE_LANGUAGES = [
    ("en", "🇬🇧 English"),
    ("es", "🇪🇸 Spanish"),
    ("fr", "🇫🇷 French"),
    ("de", "🇩🇪 German"),
    ("hi", "🇮🇳 Hindi"),
    ("pt", "🇵🇹 Portuguese"),
    ("it", "🇮🇹 Italian"),
    ("ja", "🇯🇵 Japanese"),
    ("ko", "🇰🇷 Korean"),
    ("zh", "🇨🇳 Chinese"),
    ("ru", "🇷🇺 Russian"),
    ("ar", "🇸🇦 Arabic"),
]

# Plan-based max filesize (in bytes). Telegram bot limit is 2 GB; XTV Pro userbot
# pushes this to 4 GB for Deluxe.
MAX_SIZE_STANDARD = 2 * 1024 * 1024 * 1024
MAX_SIZE_DELUXE = 4 * 1024 * 1024 * 1024

# Progress update throttling
_PROGRESS_INTERVAL = 3.0  # seconds between status message edits


# === Helper Functions ===
def extract_first_url(text: str) -> str | None:
    """Return the first YouTube URL found in a text, or None."""
    if not text:
        return None
    m = YT_URL_REGEX.search(text)
    if not m:
        return None
    url = m.group(0)
    # Normalize so yt-dlp always has a scheme
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def is_youtube_url(text: str) -> bool:
    return extract_first_url(text) is not None


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Strip characters that cause issues on the filesystem / Telegram."""
    if not name:
        return "youtube"
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = name.strip(" .")
    if not name:
        name = "youtube"
    return name[:max_len]


async def get_user_max_filesize(user_id: int) -> int:
    """Return the max download size (bytes) allowed for this user's plan.

    Standard users / non-premium get 2 GB. Deluxe users with XTV Pro 4GB enabled
    get 4 GB. Falls back to 2 GB on any lookup error so we never exceed the
    Telegram bot hard limit unintentionally.
    """
    try:
        if not Config.PUBLIC_MODE:
            return MAX_SIZE_STANDARD
        from database import db
        user_doc = await db.get_user(user_id)
        if not user_doc or not user_doc.get("is_premium"):
            return MAX_SIZE_STANDARD
        plan_name = user_doc.get("premium_plan", "standard")
        config = await db.get_public_config()
        plan_settings = config.get(f"premium_{plan_name}", {})
        features = plan_settings.get("features", {})
        if features.get("xtv_pro_4gb"):
            return MAX_SIZE_DELUXE
        return MAX_SIZE_STANDARD
    except Exception as e:
        logger.debug(f"get_user_max_filesize fallback: {e}")
        return MAX_SIZE_STANDARD


def _ytdlp_missing_text() -> str:
    return (
        "❌ **YouTube support is not installed on this server.**\n\n"
        "> The `yt-dlp` package is missing.\n"
        "> Ask the administrator to run `pip install -r requirements.txt`."
    )


def _sync_extract_info(url: str) -> dict | None:
    """Blocking yt-dlp info extraction. Runs in a thread."""
    if not _YTDLP_AVAILABLE:
        return None
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.warning(f"yt-dlp extract_info failed for {url}: {e}")
        return None


async def extract_video_info(url: str) -> dict | None:
    """Fetch video metadata without downloading. Returns the yt-dlp info dict."""
    if not _YTDLP_AVAILABLE:
        return None
    return await asyncio.to_thread(_sync_extract_info, url)


def _human_bytes(n: int | float) -> str:
    try:
        n = float(n or 0)
    except Exception:
        return "?"
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if n < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PiB"


class _ProgressState:
    """Holds throttling + latest-snapshot for yt-dlp progress hooks.

    yt-dlp's progress_hooks run in the download thread — we cannot `await` from
    there. Instead we stash the most recent snapshot and drain it from the event
    loop via a separate coroutine.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, status_msg, title_hint: str = ""):
        self.loop = loop
        self.status_msg = status_msg
        self.title_hint = title_hint
        self.latest: dict | None = None
        self.last_edit = 0.0
        self.closed = False

    def hook(self, d: dict) -> None:
        """yt-dlp progress hook entry (sync, runs off-loop)."""
        try:
            self.latest = d
        except Exception:
            pass

    async def pump(self) -> None:
        """Periodically edits the status message with the latest progress."""
        while not self.closed:
            await asyncio.sleep(_PROGRESS_INTERVAL)
            d = self.latest
            if not d:
                continue
            if (time.time() - self.last_edit) < _PROGRESS_INTERVAL:
                continue
            text = self._format(d)
            if not text:
                continue
            try:
                await self.status_msg.edit_text(text)
                self.last_edit = time.time()
            except MessageNotModified:
                pass
            except Exception as e:
                logger.debug(f"Progress edit failed: {e}")

    def _format(self, d: dict) -> str | None:
        status = d.get("status")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            pct = (downloaded / total * 100) if total else 0
            bar_len = 14
            filled = int(bar_len * pct / 100) if pct else 0
            bar = "█" * filled + "░" * (bar_len - filled)
            title_line = f"**{self.title_hint}**\n" if self.title_hint else ""
            return (
                f"⬇️ **Downloading from YouTube**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{title_line}"
                f"`{bar}` {pct:5.1f}%\n"
                f"• Size: `{_human_bytes(downloaded)} / {_human_bytes(total) if total else '?'}`\n"
                f"• Speed: `{_human_bytes(speed)}/s`\n"
                f"• ETA: `{int(eta)}s`"
            )
        if status == "finished":
            return (
                f"✅ **Download complete — post-processing...**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"> Converting / muxing, please wait."
            )
        return None


def _sync_download_video(url: str, quality: str, output_dir: str, max_size: int,
                         hook) -> tuple[bool, str, dict | None]:
    """Blocking yt-dlp video download. Runs in a thread.

    Returns: (success, file_path_or_error_message, info_dict)
    """
    if not _YTDLP_AVAILABLE:
        return False, _YTDLP_IMPORT_ERROR or "yt-dlp not installed", None

    if quality == "best":
        fmt = f"bestvideo[filesize<?{max_size}]+bestaudio/best[filesize<?{max_size}]/best"
    else:
        try:
            h = int(quality)
        except ValueError:
            h = 720
        fmt = (
            f"bestvideo[height<={h}][filesize<?{max_size}]+bestaudio/"
            f"best[height<={h}][filesize<?{max_size}]/best[height<={h}]/best"
        )

    out_tmpl = os.path.join(output_dir, "%(title).80s [%(id)s].%(ext)s")
    opts = {
        "format": fmt,
        "outtmpl": out_tmpl,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
        "max_filesize": max_size,
        "progress_hooks": [hook] if hook else [],
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
            {"key": "EmbedThumbnail"},
            {"key": "FFmpegMetadata"},
        ],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return False, "No info returned from yt-dlp.", None
            filepath = ydl.prepare_filename(info)
            # yt-dlp may have converted the container — swap extension to .mp4
            base, _ = os.path.splitext(filepath)
            mp4_path = base + ".mp4"
            if os.path.exists(mp4_path):
                filepath = mp4_path
            if not os.path.exists(filepath):
                return False, f"Output file not found: {filepath}", info
            return True, filepath, info
    except yt_dlp.utils.DownloadError as e:
        return False, f"Download failed: {e}", None
    except Exception as e:
        logger.exception("yt-dlp video download crashed")
        return False, f"Unexpected error: {e}", None


async def download_video(url: str, quality: str, output_dir: str, max_size: int,
                         progress_state: _ProgressState | None = None
                         ) -> tuple[bool, str, dict | None]:
    hook = progress_state.hook if progress_state else None
    return await asyncio.to_thread(_sync_download_video, url, quality, output_dir, max_size, hook)


def _sync_download_audio(url: str, bitrate: str, output_dir: str, max_size: int,
                         hook) -> tuple[bool, str, dict | None]:
    """Blocking yt-dlp audio download → MP3 with requested bitrate."""
    if not _YTDLP_AVAILABLE:
        return False, _YTDLP_IMPORT_ERROR or "yt-dlp not installed", None

    out_tmpl = os.path.join(output_dir, "%(title).80s [%(id)s].%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_tmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": max_size,
        "progress_hooks": [hook] if hook else [],
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": str(bitrate)},
            {"key": "EmbedThumbnail"},
            {"key": "FFmpegMetadata"},
        ],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return False, "No info returned from yt-dlp.", None
            filepath = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filepath)
            mp3_path = base + ".mp3"
            if os.path.exists(mp3_path):
                filepath = mp3_path
            if not os.path.exists(filepath):
                return False, f"Output file not found: {filepath}", info
            return True, filepath, info
    except yt_dlp.utils.DownloadError as e:
        return False, f"Download failed: {e}", None
    except Exception as e:
        logger.exception("yt-dlp audio download crashed")
        return False, f"Unexpected error: {e}", None


async def download_audio(url: str, bitrate: str, output_dir: str, max_size: int,
                         progress_state: _ProgressState | None = None
                         ) -> tuple[bool, str, dict | None]:
    hook = progress_state.hook if progress_state else None
    return await asyncio.to_thread(_sync_download_audio, url, bitrate, output_dir, max_size, hook)


def _sync_download_thumbnail(url: str, output_dir: str) -> tuple[bool, str, dict | None]:
    """Fetch the best available thumbnail as a JPG file using yt-dlp + requests."""
    if not _YTDLP_AVAILABLE:
        return False, _YTDLP_IMPORT_ERROR or "yt-dlp not installed", None
    try:
        info = _sync_extract_info(url)
        if not info:
            return False, "Could not fetch video metadata.", None

        # Prefer maxresdefault construction over arbitrary thumbnails list
        thumb_url = None
        video_id = info.get("id")
        if video_id:
            thumb_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"

        candidates = []
        if thumb_url:
            candidates.append(thumb_url)
        for t in (info.get("thumbnails") or []):
            u = t.get("url")
            if u and u not in candidates:
                candidates.append(u)
        if info.get("thumbnail") and info["thumbnail"] not in candidates:
            candidates.append(info["thumbnail"])

        import requests  # already in requirements.txt
        title = sanitize_filename(info.get("title") or video_id or "youtube")
        out_path = os.path.join(output_dir, f"{title}_thumbnail.jpg")

        last_err = None
        for cand in candidates:
            try:
                r = requests.get(cand, timeout=20, stream=True)
                if r.status_code == 200 and int(r.headers.get("content-length", 1)) > 1024:
                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(1024 * 64):
                            if chunk:
                                f.write(chunk)
                    if os.path.getsize(out_path) > 1024:
                        return True, out_path, info
                else:
                    last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = str(e)
                continue
        return False, f"No thumbnail could be fetched ({last_err}).", info
    except Exception as e:
        logger.exception("Thumbnail fetch crashed")
        return False, f"Unexpected error: {e}", None


async def download_thumbnail(url: str, output_dir: str) -> tuple[bool, str, dict | None]:
    return await asyncio.to_thread(_sync_download_thumbnail, url, output_dir)


def _sync_download_subtitles(url: str, lang: str, output_dir: str
                             ) -> tuple[bool, str, dict | None]:
    """Download subtitles/captions as an SRT file. Falls back to auto-captions."""
    if not _YTDLP_AVAILABLE:
        return False, _YTDLP_IMPORT_ERROR or "yt-dlp not installed", None

    out_tmpl = os.path.join(output_dir, "%(title).80s [%(id)s].%(ext)s")
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [lang],
        "subtitlesformat": "srt/best",
        "convertsubtitles": "srt",
        "outtmpl": out_tmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegSubtitlesConvertor", "format": "srt"},
        ],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return False, "No info returned from yt-dlp.", None

            base = ydl.prepare_filename(info)
            base_noext, _ = os.path.splitext(base)

            # yt-dlp writes `<base>.<lang>.srt`. Try exact match first, then
            # any srt starting with our base (covers `en-US`, `en-orig`, …).
            candidate = f"{base_noext}.{lang}.srt"
            if os.path.exists(candidate):
                return True, candidate, info

            try:
                dir_ = os.path.dirname(base_noext) or "."
                prefix = os.path.basename(base_noext) + "."
                for fn in os.listdir(dir_):
                    if fn.startswith(prefix) and fn.endswith(".srt"):
                        return True, os.path.join(dir_, fn), info
            except Exception:
                pass

            return False, f"No subtitles found for language '{lang}'.", info
    except yt_dlp.utils.DownloadError as e:
        return False, f"Subtitle download failed: {e}", None
    except Exception as e:
        logger.exception("yt-dlp subtitle download crashed")
        return False, f"Unexpected error: {e}", None


async def download_subtitles(url: str, lang: str, output_dir: str
                             ) -> tuple[bool, str, dict | None]:
    return await asyncio.to_thread(_sync_download_subtitles, url, lang, output_dir)


def _format_duration(seconds) -> str:
    try:
        s = int(seconds or 0)
    except Exception:
        return "?"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{sec:02d}"
    return f"{m:d}:{sec:02d}"


def _format_number(n) -> str:
    try:
        n = int(n)
    except Exception:
        return "?"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _cancel_row() -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton("❌ Cancel", callback_data="yt_cancel")]]


def _mode_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Video", callback_data="yt_mode_video"),
         InlineKeyboardButton("🎵 Audio (MP3)", callback_data="yt_mode_audio")],
        [InlineKeyboardButton("🖼 Thumbnail", callback_data="yt_mode_thumb"),
         InlineKeyboardButton("📝 Subtitles", callback_data="yt_mode_subs")],
        [InlineKeyboardButton("ℹ️ Video Info", callback_data="yt_mode_info")],
        [InlineKeyboardButton("❌ Cancel", callback_data="yt_cancel")],
    ])


def _result_menu_markup() -> InlineKeyboardMarkup:
    """Markup shown below a delivered YouTube result (thumbnail/audio/video/
    subs/info). Lets the user go back to the per-URL mode menu, start over
    with a new link, or finish."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="yt_back_mode"),
         InlineKeyboardButton("🔗 New YouTube Link", callback_data="yt_new_link")],
        [InlineKeyboardButton("❌ Close", callback_data="yt_cancel")],
    ])


def _mode_menu_text(title: str, uploader: str, duration: str) -> str:
    return (
        f"▶️ **YouTube Tool**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**🎬 {title}**\n"
        f"__by {uploader} · ⏱ {duration}__\n\n"
        f"Choose what you want to do:"
    )


def _quality_menu_markup() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for code, label in VIDEO_QUALITIES:
        row.append(InlineKeyboardButton(label, callback_data=f"yt_quality_{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="yt_cancel")])
    return InlineKeyboardMarkup(rows)


def _bitrate_menu_markup() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"yt_audio_bitrate_{code}")]
            for code, label in AUDIO_BITRATES]
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="yt_cancel")])
    return InlineKeyboardMarkup(rows)


def _sub_lang_menu_markup() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for code, label in SUBTITLE_LANGUAGES:
        row.append(InlineKeyboardButton(label, callback_data=f"yt_sub_lang_{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="yt_cancel")])
    return InlineKeyboardMarkup(rows)


# === Menu Handlers ===
@Client.on_callback_query(filters.regex(r"^youtube_tool_menu$"))
async def handle_youtube_tool_menu(client, callback_query):
    await track_tool_usage(callback_query.from_user.id, "youtube_tool")
    await callback_query.answer()
    user_id = callback_query.from_user.id
    clear_session(user_id)

    if not _YTDLP_AVAILABLE:
        try:
            await callback_query.message.edit_text(
                _ytdlp_missing_text(),
                reply_markup=InlineKeyboardMarkup(_cancel_row()),
            )
        except MessageNotModified:
            pass
        return

    set_state(user_id, "awaiting_youtube_url")
    try:
        await callback_query.message.edit_text(
            "▶️ **YouTube Tool**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Send me a **YouTube URL** to begin.\n\n"
            "**What I can do:**\n"
            "🎬 Download video (up to 1080p / best)\n"
            "🎵 Extract audio as MP3 (128 / 192 / 320 kbps)\n"
            "🖼 Grab the HD thumbnail\n"
            "📝 Download subtitles (multiple languages)\n"
            "ℹ️ Show video info & metadata\n\n"
            "__Tip: You can also paste a YouTube URL any time to get this menu automatically.__",
            reply_markup=InlineKeyboardMarkup(_cancel_row()),
            disable_web_page_preview=True,
        )
    except MessageNotModified:
        pass


def format_video_info(info: dict) -> str:
    """Render a yt-dlp info dict as a readable Telegram message."""
    if not info:
        return "❌ No metadata available."

    title = info.get("title") or "Untitled"
    uploader = info.get("uploader") or info.get("channel") or "Unknown"
    duration = _format_duration(info.get("duration"))
    views = _format_number(info.get("view_count"))
    likes = _format_number(info.get("like_count"))
    upload_date = info.get("upload_date") or ""
    if upload_date and len(upload_date) == 8:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

    description = (info.get("description") or "").strip()
    if len(description) > 600:
        description = description[:600] + "…"

    tags = info.get("tags") or []
    tags_str = ", ".join(f"#{t.replace(' ', '_')}" for t in tags[:10]) if tags else "—"

    chapters = info.get("chapters") or []
    chapters_str = ""
    if chapters:
        lines = []
        for c in chapters[:10]:
            start = _format_duration(c.get("start_time"))
            name = (c.get("title") or "").strip()
            if name:
                lines.append(f"  • `{start}` — {name}")
        if len(chapters) > 10:
            lines.append(f"  • … and {len(chapters) - 10} more")
        if lines:
            chapters_str = "\n\n**📚 Chapters:**\n" + "\n".join(lines)

    return (
        f"ℹ️ **Video Info**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"**Title:** {title}\n"
        f"**Uploader:** {uploader}\n"
        f"**Duration:** `{duration}`\n"
        f"**Views:** `{views}`  ·  **Likes:** `{likes}`\n"
        f"**Uploaded:** `{upload_date or '?'}`\n\n"
        f"**Tags:** {tags_str}"
        f"{chapters_str}\n\n"
        f"**Description:**\n{description or '—'}"
    )


# === URL Input Handler ===
@Client.on_message(filters.text & filters.private & ~filters.command([
    "start", "help", "info", "end", "settings", "myfiles",
    "r", "rename", "a", "audio", "c", "convert", "w", "watermark",
    "s", "subtitle", "t", "trim", "mi", "mediainfo", "v", "voice",
    "vn", "videonote", "g", "general", "p", "personal",
    "yt", "youtube",
]), group=1)
async def handle_youtube_url_input(client, message):
    """Handles URL input while user is in the YouTube-tool awaiting-URL state."""
    user_id = message.from_user.id
    state = get_state(user_id)
    if state != "awaiting_youtube_url":
        return  # not our flow

    url = extract_first_url(message.text or "")
    if not url:
        await message.reply_text(
            "⚠️ That doesn't look like a YouTube URL.\n"
            "Please send a link from `youtube.com`, `youtu.be` or `youtube-nocookie.com`.",
            reply_markup=InlineKeyboardMarkup(_cancel_row()),
        )
        raise StopPropagation

    update_data(user_id, "youtube_url", url)
    status_msg = await message.reply_text(
        "🔎 **Fetching video info...**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "> Please wait a moment.",
        reply_markup=InlineKeyboardMarkup(_cancel_row()),
    )

    info = await extract_video_info(url)
    if not info:
        set_state(user_id, "awaiting_youtube_url")
        try:
            await status_msg.edit_text(
                "❌ Could not fetch video info.\n\n"
                "The link might be invalid, private, age-restricted, or "
                "region-blocked. Send another URL or cancel.",
                reply_markup=InlineKeyboardMarkup(_cancel_row()),
            )
        except MessageNotModified:
            pass
        return

    update_data(user_id, "video_title", info.get("title") or "Untitled")
    update_data(user_id, "video_id", info.get("id"))
    update_data(user_id, "video_duration", info.get("duration") or 0)
    update_data(user_id, "video_uploader", info.get("uploader") or info.get("channel") or "Unknown")
    set_state(user_id, "awaiting_yt_mode")

    title = info.get("title") or "Untitled"
    uploader = info.get("uploader") or info.get("channel") or "Unknown"
    duration = _format_duration(info.get("duration"))

    try:
        await status_msg.edit_text(
            f"▶️ **YouTube Tool**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**🎬 {title}**\n"
            f"__by {uploader} · ⏱ {duration}__\n\n"
            f"Choose what you want to do:",
            reply_markup=_mode_menu_markup(),
            disable_web_page_preview=True,
        )
    except MessageNotModified:
        pass
    raise StopPropagation


# === Mode Selection Callbacks ===
@Client.on_callback_query(filters.regex(r"^yt_mode_(video|audio|thumb|subs|info)$"))
async def handle_yt_mode(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    mode = data.replace("yt_mode_", "")

    session = get_data(user_id)
    url = session.get("youtube_url") if session else None
    if not url:
        return await callback_query.answer(
            "⚠️ Session expired. Please start again.", show_alert=True
        )
    await callback_query.answer()
    update_data(user_id, "youtube_mode", mode)

    if mode == "video":
        set_state(user_id, "awaiting_yt_quality")
        try:
            await callback_query.message.edit_text(
                "🎬 **Video Download**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Pick a quality. Higher quality → larger file.\n"
                "> Files over your plan's limit will fail to upload.",
                reply_markup=_quality_menu_markup(),
            )
        except MessageNotModified:
            pass
        return

    if mode == "audio":
        set_state(user_id, "awaiting_yt_audio_bitrate")
        try:
            await callback_query.message.edit_text(
                "🎵 **Audio (MP3) Download**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Pick an MP3 bitrate:",
                reply_markup=_bitrate_menu_markup(),
            )
        except MessageNotModified:
            pass
        return

    if mode == "subs":
        set_state(user_id, "awaiting_yt_sub_lang")
        try:
            await callback_query.message.edit_text(
                "📝 **Subtitle Download**\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Pick a language. If no manual subtitles exist I'll try "
                "auto-generated ones.",
                reply_markup=_sub_lang_menu_markup(),
            )
        except MessageNotModified:
            pass
        return

    if mode == "thumb":
        await _run_thumbnail_download(client, callback_query.message, user_id, url)
        return

    if mode == "info":
        await _run_info_display(client, callback_query.message, user_id, url)
        return


# === Processing Runners ===
def _safe_remove(path: str | None) -> None:
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logger.debug(f"Failed to remove temp file {path}: {e}")


@Client.on_callback_query(filters.regex(r"^yt_quality_(360|480|720|1080|best)$"))
async def handle_yt_quality(client, callback_query):
    user_id = callback_query.from_user.id
    quality = callback_query.data.replace("yt_quality_", "")
    session = get_data(user_id)
    url = session.get("youtube_url") if session else None
    if not url:
        return await callback_query.answer(
            "⚠️ Session expired. Please start again.", show_alert=True
        )
    await callback_query.answer()
    await _run_video_download(client, callback_query.message, user_id, url, quality)


async def _run_video_download(client, status_msg, user_id: int, url: str, quality: str):
    title_hint = (get_data(user_id) or {}).get("video_title") or ""
    try:
        await status_msg.edit_text(
            f"🎬 **Preparing video download...**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**{title_hint}**\n"
            f"> Quality: `{quality}`\n\n"
            f"__Starting download...__",
        )
    except MessageNotModified:
        pass

    loop = asyncio.get_event_loop()
    progress = _ProgressState(loop, status_msg, title_hint=title_hint)
    pump_task = asyncio.create_task(progress.pump())

    max_size = await get_user_max_filesize(user_id)
    output_dir = Config.DOWNLOAD_DIR

    filepath = None
    info = None
    try:
        ok, result, info = await download_video(url, quality, output_dir, max_size, progress)
        progress.closed = True
        pump_task.cancel()
        if not ok:
            try:
                await status_msg.edit_text(
                    f"❌ **Video download failed.**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"`{result}`",
                    reply_markup=_result_menu_markup(),
                )
            except MessageNotModified:
                pass
            return
        filepath = result

        await status_msg.edit_text(
            f"⬆️ **Uploading to Telegram...**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**{title_hint}**"
        )

        caption = (
            f"🎬 **{info.get('title') or 'YouTube Video'}**\n"
            f"__{info.get('uploader') or ''}__\n"
            f"Quality: `{quality}`"
        )
        try:
            await client.send_video(
                chat_id=user_id,
                video=filepath,
                caption=caption,
                duration=int(info.get("duration") or 0),
                supports_streaming=True,
            )
        except Exception as e:
            logger.warning(f"send_video failed, falling back to send_document: {e}")
            await client.send_document(chat_id=user_id, document=filepath, caption=caption)

        try:
            await status_msg.edit_text(
                "✅ **Video delivered above.**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Choose next action:",
                reply_markup=_result_menu_markup(),
            )
        except MessageNotModified:
            pass
    except Exception as e:
        logger.exception("Video download pipeline crashed")
        try:
            await status_msg.edit_text(
                f"❌ Unexpected error: `{e}`",
                reply_markup=_result_menu_markup(),
            )
        except Exception:
            pass
    finally:
        progress.closed = True
        if not pump_task.done():
            pump_task.cancel()
        _safe_remove(filepath)
        set_state(user_id, "awaiting_yt_result")


@Client.on_callback_query(filters.regex(r"^yt_audio_bitrate_(128|192|320)$"))
async def handle_yt_audio_bitrate(client, callback_query):
    user_id = callback_query.from_user.id
    bitrate = callback_query.data.replace("yt_audio_bitrate_", "")
    session = get_data(user_id)
    url = session.get("youtube_url") if session else None
    if not url:
        return await callback_query.answer(
            "⚠️ Session expired. Please start again.", show_alert=True
        )
    await callback_query.answer()
    await _run_audio_download(client, callback_query.message, user_id, url, bitrate)


async def _run_audio_download(client, status_msg, user_id: int, url: str, bitrate: str):
    title_hint = (get_data(user_id) or {}).get("video_title") or ""
    try:
        await status_msg.edit_text(
            f"🎵 **Preparing audio download...**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**{title_hint}**\n"
            f"> Bitrate: `{bitrate} kbps`\n\n"
            f"__Starting download...__"
        )
    except MessageNotModified:
        pass

    loop = asyncio.get_event_loop()
    progress = _ProgressState(loop, status_msg, title_hint=title_hint)
    pump_task = asyncio.create_task(progress.pump())

    max_size = await get_user_max_filesize(user_id)
    output_dir = Config.DOWNLOAD_DIR

    filepath = None
    info = None
    try:
        ok, result, info = await download_audio(url, bitrate, output_dir, max_size, progress)
        progress.closed = True
        pump_task.cancel()
        if not ok:
            try:
                await status_msg.edit_text(
                    f"❌ **Audio download failed.**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"`{result}`",
                    reply_markup=_result_menu_markup(),
                )
            except MessageNotModified:
                pass
            return
        filepath = result

        await status_msg.edit_text(
            f"⬆️ **Uploading MP3 to Telegram...**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**{title_hint}**"
        )

        caption = (
            f"🎵 **{info.get('title') or 'YouTube Audio'}**\n"
            f"__{info.get('uploader') or ''}__\n"
            f"Bitrate: `{bitrate} kbps`"
        )
        try:
            await client.send_audio(
                chat_id=user_id,
                audio=filepath,
                caption=caption,
                duration=int(info.get("duration") or 0),
                performer=info.get("uploader") or None,
                title=info.get("title") or None,
            )
        except Exception as e:
            logger.warning(f"send_audio failed, falling back to send_document: {e}")
            await client.send_document(chat_id=user_id, document=filepath, caption=caption)

        try:
            await status_msg.edit_text(
                "✅ **Audio delivered above.**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Choose next action:",
                reply_markup=_result_menu_markup(),
            )
        except MessageNotModified:
            pass
    except Exception as e:
        logger.exception("Audio download pipeline crashed")
        try:
            await status_msg.edit_text(
                f"❌ Unexpected error: `{e}`",
                reply_markup=_result_menu_markup(),
            )
        except Exception:
            pass
    finally:
        progress.closed = True
        if not pump_task.done():
            pump_task.cancel()
        _safe_remove(filepath)
        set_state(user_id, "awaiting_yt_result")


@Client.on_callback_query(filters.regex(r"^yt_sub_lang_([a-zA-Z\-]+)$"))
async def handle_yt_sub_lang(client, callback_query):
    user_id = callback_query.from_user.id
    lang = callback_query.data.replace("yt_sub_lang_", "")
    session = get_data(user_id)
    url = session.get("youtube_url") if session else None
    if not url:
        return await callback_query.answer(
            "⚠️ Session expired. Please start again.", show_alert=True
        )
    await callback_query.answer()
    await _run_subtitle_download(client, callback_query.message, user_id, url, lang)


async def _run_subtitle_download(client, status_msg, user_id: int, url: str, lang: str):
    title_hint = (get_data(user_id) or {}).get("video_title") or ""
    try:
        await status_msg.edit_text(
            f"📝 **Fetching subtitles...**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**{title_hint}**\n"
            f"> Language: `{lang}`"
        )
    except MessageNotModified:
        pass

    output_dir = Config.DOWNLOAD_DIR
    filepath = None
    try:
        ok, result, info = await download_subtitles(url, lang, output_dir)
        if not ok:
            try:
                await status_msg.edit_text(
                    f"❌ **Subtitle download failed.**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"`{result}`",
                    reply_markup=_result_menu_markup(),
                )
            except MessageNotModified:
                pass
            return
        filepath = result

        caption = (
            f"📝 **Subtitles — {info.get('title') or 'YouTube Video'}**\n"
            f"Language: `{lang}`"
        )
        try:
            await client.send_document(chat_id=user_id, document=filepath, caption=caption)
        except Exception as e:
            logger.exception("Subtitle send_document failed")
            try:
                await status_msg.edit_text(
                    f"❌ Upload failed: `{e}`",
                    reply_markup=_result_menu_markup(),
                )
            except Exception:
                pass
            return

        try:
            await status_msg.edit_text(
                "✅ **Subtitles delivered above.**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Choose next action:",
                reply_markup=_result_menu_markup(),
            )
        except MessageNotModified:
            pass
    except Exception as e:
        logger.exception("Subtitle pipeline crashed")
        try:
            await status_msg.edit_text(
                f"❌ Unexpected error: `{e}`",
                reply_markup=_result_menu_markup(),
            )
        except Exception:
            pass
    finally:
        _safe_remove(filepath)
        set_state(user_id, "awaiting_yt_result")


async def _run_thumbnail_download(client, status_msg, user_id: int, url: str):
    title_hint = (get_data(user_id) or {}).get("video_title") or ""
    try:
        await status_msg.edit_text(
            f"🖼 **Fetching thumbnail...**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"**{title_hint}**"
        )
    except MessageNotModified:
        pass

    output_dir = Config.DOWNLOAD_DIR
    filepath = None
    try:
        ok, result, info = await download_thumbnail(url, output_dir)
        if not ok:
            try:
                await status_msg.edit_text(
                    f"❌ **Thumbnail download failed.**\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"`{result}`",
                    reply_markup=_result_menu_markup(),
                )
            except MessageNotModified:
                pass
            return
        filepath = result

        caption = (
            f"🖼 **{info.get('title') or 'YouTube Thumbnail'}**\n"
            f"__{info.get('uploader') or ''}__"
        )
        try:
            await client.send_photo(chat_id=user_id, photo=filepath, caption=caption)
        except Exception as e:
            logger.warning(f"send_photo failed, falling back to send_document: {e}")
            await client.send_document(chat_id=user_id, document=filepath, caption=caption)

        # Keep the thumbnail image in chat; replace the status message with
        # a small result menu (Back to Menu / New Link).
        try:
            await status_msg.edit_text(
                "✅ **Thumbnail delivered above.**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Choose next action:",
                reply_markup=_result_menu_markup(),
            )
        except MessageNotModified:
            pass
    except Exception as e:
        logger.exception("Thumbnail pipeline crashed")
        try:
            await status_msg.edit_text(
                f"❌ Unexpected error: `{e}`",
                reply_markup=_result_menu_markup(),
            )
        except Exception:
            pass
    finally:
        _safe_remove(filepath)
        # Session is kept alive so Back-to-Menu works. State is set to
        # awaiting_yt_result so stray text messages don't trigger other flows.
        set_state(user_id, "awaiting_yt_result")


async def _run_info_display(client, status_msg, user_id: int, url: str):
    try:
        await status_msg.edit_text(
            "ℹ️ **Fetching full metadata...**\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
    except MessageNotModified:
        pass

    info = await extract_video_info(url)
    if not info:
        try:
            await status_msg.edit_text(
                "❌ Could not fetch video info. The link may be invalid, "
                "private or region-blocked.",
                reply_markup=_result_menu_markup(),
            )
        except Exception:
            pass
        set_state(user_id, "awaiting_yt_result")
        return

    text = format_video_info(info)
    delivered = False
    try:
        await status_msg.edit_text(
            text,
            disable_web_page_preview=True,
            reply_markup=_result_menu_markup(),
        )
        delivered = True
    except MessageNotModified:
        delivered = True
    except Exception as e:
        # Telegram may reject ultra-long messages — fall back to a document upload
        logger.warning(f"Info edit failed, sending as document: {e}")
        try:
            tmp_path = os.path.join(Config.DOWNLOAD_DIR, f"yt_info_{info.get('id') or user_id}.txt")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
            await client.send_document(chat_id=user_id, document=tmp_path,
                                       caption="ℹ️ YouTube Video Info")
            _safe_remove(tmp_path)
            try:
                await status_msg.edit_text(
                    "✅ **Info delivered above.**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "Choose next action:",
                    reply_markup=_result_menu_markup(),
                )
            except MessageNotModified:
                pass
            delivered = True
        except Exception as e2:
            logger.exception("Info fallback failed")
            try:
                await status_msg.edit_text(
                    f"❌ Could not render info: `{e2}`",
                    reply_markup=_result_menu_markup(),
                )
            except Exception:
                pass
    set_state(user_id, "awaiting_yt_result")
    _ = delivered  # placeholder for future telemetry


# === Post-result navigation: Back to Menu / New YouTube Link ===
@Client.on_callback_query(filters.regex(r"^yt_back_mode$"))
async def handle_yt_back_mode(client, callback_query):
    """Return the user to the per-URL mode menu, keeping the session alive."""
    user_id = callback_query.from_user.id
    session = get_data(user_id) or {}
    url = session.get("youtube_url")
    if not url:
        return await callback_query.answer(
            "⚠️ Session expired. Please send a new YouTube link.", show_alert=True
        )
    await callback_query.answer()
    set_state(user_id, "awaiting_yt_mode")

    title = session.get("video_title") or "Untitled"
    uploader = session.get("video_uploader") or "Unknown"
    duration = _format_duration(session.get("video_duration"))
    try:
        await callback_query.message.edit_text(
            _mode_menu_text(title, uploader, duration),
            reply_markup=_mode_menu_markup(),
            disable_web_page_preview=True,
        )
    except MessageNotModified:
        pass


@Client.on_callback_query(filters.regex(r"^yt_new_link$"))
async def handle_yt_new_link(client, callback_query):
    """Clear the current video context and ask for a new URL."""
    user_id = callback_query.from_user.id
    await callback_query.answer()
    # Keep the user in the YouTube flow but drop video-specific data.
    for key in ("youtube_url", "video_title", "video_id",
                "video_duration", "video_uploader", "youtube_mode"):
        update_data(user_id, key, None)
    set_state(user_id, "awaiting_youtube_url")
    try:
        await callback_query.message.edit_text(
            "▶️ **YouTube Tool**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "> Paste the next **YouTube URL** to continue.",
            reply_markup=InlineKeyboardMarkup(_cancel_row()),
            disable_web_page_preview=True,
        )
    except MessageNotModified:
        pass


# === Cancel ===
@Client.on_callback_query(filters.regex(r"^yt_cancel$"))
async def handle_yt_cancel(client, callback_query):
    user_id = callback_query.from_user.id
    clear_session(user_id)
    await callback_query.answer("Cancelled.")
    try:
        await callback_query.message.edit_text(
            "❌ **YouTube Tool — cancelled.**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Use /start or /yt to open it again."
        )
    except MessageNotModified:
        pass


# === Auto URL Detection ===
# Runs after the dedicated awaiting_youtube_url handler (group=1). If the user
# pastes a YouTube URL without any active state, we offer to open the tool.
@Client.on_message(
    filters.private & filters.text
    & filters.regex(r"(youtube\.com|youtu\.be|youtube-nocookie\.com)"),
    group=2,
)
async def handle_yt_auto_detect(client, message):
    user_id = message.from_user.id
    if get_state(user_id):
        return  # leave existing flows alone

    if not _YTDLP_AVAILABLE:
        return  # don't advertise a broken feature

    # Gate on feature toggles / premium access, same as the /yt shortcut.
    try:
        from database import db
        toggles = await db.get_feature_toggles()
        allowed = toggles.get("youtube_tool", True)
        if Config.PUBLIC_MODE and not allowed:
            user_doc = await db.get_user(user_id)
            if user_doc and user_doc.get("is_premium"):
                plan_name = user_doc.get("premium_plan", "standard")
                config = await db.get_public_config()
                if config.get("premium_system_enabled", False):
                    plan_settings = config.get(f"premium_{plan_name}", {})
                    if plan_settings.get("features", {}).get("youtube_tool", False):
                        allowed = True
        if not allowed:
            return
    except Exception as e:
        logger.debug(f"Auto-detect feature check failed: {e}")
        return

    url = extract_first_url(message.text or "")
    if not url:
        return

    update_data(user_id, "youtube_url", url)
    status_msg = await message.reply_text(
        "🔎 **YouTube URL detected — fetching info...**\n"
        "━━━━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(_cancel_row()),
    )

    info = await extract_video_info(url)
    if not info:
        try:
            await status_msg.edit_text(
                "❌ Could not fetch video info. The link may be invalid, "
                "private or region-blocked.",
                reply_markup=InlineKeyboardMarkup(_cancel_row()),
            )
        except MessageNotModified:
            pass
        return

    update_data(user_id, "video_title", info.get("title") or "Untitled")
    update_data(user_id, "video_id", info.get("id"))
    update_data(user_id, "video_duration", info.get("duration") or 0)
    update_data(user_id, "video_uploader", info.get("uploader") or info.get("channel") or "Unknown")
    set_state(user_id, "awaiting_yt_mode")

    title = info.get("title") or "Untitled"
    uploader = info.get("uploader") or info.get("channel") or "Unknown"
    duration = _format_duration(info.get("duration"))
    try:
        await status_msg.edit_text(
            f"▶️ **YouTube Tool**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**🎬 {title}**\n"
            f"__by {uploader} · ⏱ {duration}__\n\n"
            f"Choose what you want to do:",
            reply_markup=_mode_menu_markup(),
            disable_web_page_preview=True,
        )
    except MessageNotModified:
        pass


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
