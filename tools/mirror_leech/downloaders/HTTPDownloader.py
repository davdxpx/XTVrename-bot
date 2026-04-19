"""Streaming HTTP(S) downloader for Mirror-Leech."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.Tasks import MLContext
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.http")

_HTTP_SCHEME = re.compile(r"^https?://", re.IGNORECASE)
_CHUNK = 1024 * 64
_MAX_FILENAME_LEN = 200


def _derive_filename(source: str, resp) -> str:
    """Pick a sensible local filename from the URL / Content-Disposition."""
    disp = resp.headers.get("Content-Disposition", "")
    match = re.search(r'filename\*?="?([^";]+)', disp)
    if match:
        name = unquote(match.group(1)).strip()
        if name:
            return name[:_MAX_FILENAME_LEN]
    path = urlparse(source).path
    name = os.path.basename(path) or "download.bin"
    return unquote(name)[:_MAX_FILENAME_LEN]


@register_downloader
class HTTPDownloader(Downloader):
    id = "http"
    display_name = "Direct URL (HTTP / HTTPS)"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        return bool(_HTTP_SCHEME.match(source))

    async def download(self, ctx: MLContext) -> Path:
        import aiohttp  # lazy: keep import cost off the worker-pool critical path

        ctx.status("downloading")

        dest_dir = ctx.temp_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        last_exc: Exception | None = None
        # One retry with a clean connection — common cloud providers love to
        # drop idle keep-alives mid-stream.
        for attempt in range(2):
            try:
                timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=120)
                async with aiohttp.ClientSession(timeout=timeout) as session, session.get(
                    ctx.source, allow_redirects=True
                ) as resp:
                    resp.raise_for_status()
                    filename = _derive_filename(ctx.source, resp)
                    total = float(resp.headers.get("Content-Length") or 0)
                    dest = dest_dir / filename

                    downloaded = 0.0
                    started = time.time()
                    with dest.open("wb") as f:
                        async for chunk in resp.content.iter_chunked(_CHUNK):
                            if ctx.cancelled():
                                logger.info("HTTPDownloader cancelled: %s", ctx.task_id)
                                raise asyncio.CancelledError()  # noqa
                            if not chunk:
                                continue
                                f.write(chunk)
                                downloaded += len(chunk)
                                elapsed = max(time.time() - started, 1e-3)
                                ctx.progress(downloaded, total, downloaded / elapsed)
                        return dest
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    logger.warning(
                        "HTTPDownloader retrying after error: %s (%s)", exc, ctx.source
                    )
                    continue
        raise last_exc if last_exc else RuntimeError("HTTPDownloader: unreachable")


# asyncio import parked at bottom so we don't pay the import cost for
# non-HTTP users of this module.
import asyncio  # noqa: E402
