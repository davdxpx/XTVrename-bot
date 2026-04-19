"""yt-dlp-backed downloader that handles any URL yt-dlp recognises.

Registered after HTTPDownloader so a pure direct-URL still takes the
faster plain-HTTP path; yt-dlp wins for YouTube / Vimeo / SoundCloud
/ Reddit / Twitter / etc. where the raw URL doesn't point at a media
file.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.Tasks import MLContext
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.ytdlp")


def _extractor_accepts(source: str) -> bool:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return False
    # yt-dlp has a cheap URL check; use it so we don't do a full network
    # probe just to classify.
    from yt_dlp.extractor import gen_extractors

    for extractor in gen_extractors():
        try:
            if extractor.suitable(source) and extractor.IE_NAME != "generic":
                return True
        except Exception:
            continue
    return False


@register_downloader
class YTDLPDownloader(Downloader):
    id = "ytdlp"
    display_name = "yt-dlp (YouTube / social video)"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        return _extractor_accepts(source)

    async def download(self, ctx: MLContext) -> Path:
        import yt_dlp

        ctx.status("downloading")
        ctx.temp_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(ctx.temp_dir / "%(title).200s.%(ext)s")

        started = time.time()

        def _hook(d: dict) -> None:
            if ctx.cancelled():
                raise yt_dlp.utils.DownloadError("cancelled")
            if d.get("status") == "downloading":
                total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
                done = float(d.get("downloaded_bytes") or 0)
                elapsed = max(time.time() - started, 1e-3)
                ctx.progress(done, total, done / elapsed)

        opts = {
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_hook],
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "noprogress": True,
        }

        def _run() -> str:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(ctx.source, download=True)
                return ydl.prepare_filename(info)

        local = await asyncio.to_thread(_run)
        return Path(local)
