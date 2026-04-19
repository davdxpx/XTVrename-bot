# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Instant-share link downloader.

When the source URL points at our own DDL endpoint
(`<DDL_BASE_URL>/ddl/<token>/<name>`) we skip the HTTP round-trip and
copy the registered file directly from the local tokens registry. This
is the hot path for re-mirroring the bot's own outputs.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.Tasks import MLContext
from tools.mirror_leech.uploaders.DDL import lookup_token, mark_served
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.instant")


def _ddl_base() -> str:
    return (os.getenv("DDL_BASE_URL") or "").rstrip("/")


@register_downloader
class InstantShareDownloader(Downloader):
    id = "instant"
    display_name = "Instant-Share Link"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        base = _ddl_base()
        if not base:
            return False
        return source.startswith(f"{base}/ddl/")

    async def download(self, ctx: MLContext) -> Path:
        ctx.status("downloading")

        base = _ddl_base()
        rest = ctx.source[len(f"{base}/ddl/"):]
        token, _, remainder = rest.partition("/")
        filename = remainder or "instant.bin"

        entry = lookup_token(token)
        if entry is None:
            raise RuntimeError("instant-share: token expired or already used")

        src_path: Path = entry["path"]
        if not src_path.exists():
            raise RuntimeError("instant-share: source file missing on disk")

        dest_dir = ctx.temp_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / (filename or src_path.name)
        shutil.copy2(src_path, dest)

        size = float(dest.stat().st_size)
        ctx.progress(size, size, 0.0)
        mark_served(token)
        logger.info(
            "InstantShare copied %s -> %s (%.1f KB)",
            src_path.name, dest.name, size / 1024,
        )
        return dest
