# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""gallery-dl downloader.

Delegates extraction + fetching to the `gallery-dl` CLI. When the
extractor yields a single file we return that path; when it yields
multiple files we bundle them into a single ZIP so the uploader layer
handles exactly one artefact per task.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Optional

from utils.log import get_logger

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.Tasks import MLContext

logger = get_logger("mirror_leech.gallery_dl")

# Cheap heuristic: gallery-dl handles tons of social-media hosts. We
# pre-filter obvious non-matches (direct binary URLs) so HTTP still runs
# them. accepts() also calls gallery-dl's extractor.find as a final
# guard.
_NON_GALLERY = re.compile(
    r"\.(zip|rar|7z|tar|gz|bz2|xz|iso|bin|exe|mp3|mp4|mkv|avi|flac|wav)"
    r"(?:\?|$)",
    re.IGNORECASE,
)


@register_downloader
class GalleryDLDownloader(Downloader):
    id = "gallery_dl"
    display_name = "Galerie / Social-Media"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        if _NON_GALLERY.search(source):
            return False
        try:
            from gallery_dl import extractor  # type: ignore
        except ImportError:
            return False
        try:
            return extractor.find(source) is not None
        except Exception:
            return False

    async def download(self, ctx: MLContext) -> Path:
        ctx.status("downloading")
        dest_dir = ctx.temp_dir / "gallery"
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Use the CLI so we inherit gallery-dl's config resolution
        # (cookies, --config, etc.) without re-implementing it.
        cmd = [
            "gallery-dl",
            "--dest", str(dest_dir),
            "--quiet",
            ctx.source,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def _pump():
            # Fallback progress: file count so the UI shows movement.
            count = 0
            while True:
                if ctx.cancelled():
                    proc.kill()
                    return
                await asyncio.sleep(2.0)
                new_count = sum(
                    1 for _ in dest_dir.rglob("*") if _.is_file()
                )
                if new_count != count:
                    count = new_count
                    # gallery-dl doesn't expose total up-front; report
                    # a moving fraction so the bar at least animates.
                    ctx.progress(count, max(count, 1) + 1, 0.0)

        pump_task = asyncio.create_task(_pump())
        try:
            _, stderr = await proc.communicate()
        finally:
            pump_task.cancel()

        if proc.returncode != 0:
            msg = (stderr or b"").decode("utf-8", "replace").strip()
            raise RuntimeError(
                f"gallery-dl exited {proc.returncode}: {msg[:200]}"
            )

        files = [p for p in dest_dir.rglob("*") if p.is_file()]
        if not files:
            raise RuntimeError("gallery-dl produced no files")

        if len(files) == 1:
            return files[0]

        # Multiple files → bundle as ZIP and return that.
        archive_base = ctx.temp_dir / f"{ctx.task_id}-gallery"
        archive = Path(shutil.make_archive(
            str(archive_base), "zip", root_dir=str(dest_dir)
        ))
        logger.info(
            "GalleryDL bundled %d files into %s", len(files), archive.name
        )
        return archive
