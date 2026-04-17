# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Cloud-host scraper downloader.

Extracts direct download URLs from cloud-host landing pages (Mediafire,
Pixeldrain, GoFile, KrakenFiles, AnonFiles-style hosts) and streams
them to disk. Delegates the actual streaming to the same chunk loop
used by HTTPDownloader so retry / cancel semantics stay identical.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.Tasks import MLContext
from utils.log import get_logger

logger = get_logger("mirror_leech.mediaplat")

_CHUNK = 1024 * 64

_SUPPORTED_HOSTS = {
    "mediafire.com",
    "www.mediafire.com",
    "pixeldrain.com",
    "gofile.io",
    "krakenfiles.com",
    "www.krakenfiles.com",
    "bayfiles.com",
    "letsupload.cc",
    "anonfiles.com",
}


def _host(source: str) -> str:
    return urlparse(source).hostname or ""


# -- Per-host resolvers ------------------------------------------------------

async def _resolve_mediafire(source: str) -> tuple[str, str]:
    import aiohttp

    async with aiohttp.ClientSession() as s, s.get(source, allow_redirects=True) as r:
        html = await r.text()
    m = re.search(r'href="(https?://download[^"]+)"', html)
    if not m:
        raise RuntimeError("mediafire: direct link not found in landing page")
    direct = m.group(1)
    name_m = re.search(r'<div class="filename">([^<]+)</div>', html)
    name = name_m.group(1).strip() if name_m else os.path.basename(
        urlparse(direct).path
    ) or "download.bin"
    return direct, name


async def _resolve_pixeldrain(source: str) -> tuple[str, str]:
    m = re.search(r"/u/([A-Za-z0-9]+)", source)
    if not m:
        raise RuntimeError("pixeldrain: not a /u/<id> URL")
    file_id = m.group(1)
    return (
        f"https://pixeldrain.com/api/file/{file_id}",
        f"pixeldrain-{file_id}.bin",
    )


async def _resolve_gofile(source: str) -> tuple[str, str]:
    import aiohttp

    # GoFile exposes a JSON API; we use it to fetch the first file of
    # the "content" record the landing page references.
    m = re.search(r"/d/([A-Za-z0-9]+)", source)
    if not m:
        raise RuntimeError("gofile: not a /d/<code> URL")
    code = m.group(1)
    async with aiohttp.ClientSession() as s, s.get(
        f"https://api.gofile.io/getContent?contentId={code}"
    ) as r:
        data = await r.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"gofile: api refused ({data.get('status')})")
    contents = (data.get("data") or {}).get("contents") or {}
    first = next(iter(contents.values()), None)
    if not first or "link" not in first:
        raise RuntimeError("gofile: folder is empty or private")
    return first["link"], first.get("name", "gofile.bin")


async def _resolve_krakenfiles(source: str) -> tuple[str, str]:
    import aiohttp

    async with aiohttp.ClientSession() as s, s.get(source) as r:
        html = await r.text()
    m = re.search(r'data-action="([^"]+)"', html)
    token_m = re.search(r'data-token="([^"]+)"', html)
    if not (m and token_m):
        raise RuntimeError("krakenfiles: tokens missing")
    async with aiohttp.ClientSession() as s, s.post(
        m.group(1), data={"token": token_m.group(1)}
    ) as r:
        j = await r.json()
    url = j.get("url")
    if not url:
        raise RuntimeError("krakenfiles: no url in response")
    return url, os.path.basename(urlparse(source).path) or "krakenfiles.bin"


_RESOLVERS = {
    "mediafire.com": _resolve_mediafire,
    "www.mediafire.com": _resolve_mediafire,
    "pixeldrain.com": _resolve_pixeldrain,
    "gofile.io": _resolve_gofile,
    "krakenfiles.com": _resolve_krakenfiles,
    "www.krakenfiles.com": _resolve_krakenfiles,
}


async def _stream_to_file(
    url: str, dest: Path, ctx: MLContext, total_hint: float = 0.0
) -> Path:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=120)
    async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url, allow_redirects=True) as resp:
        resp.raise_for_status()
        total = float(resp.headers.get("Content-Length") or total_hint or 0)
        downloaded = 0.0
        started = time.time()
        with dest.open("wb") as f:
            async for chunk in resp.content.iter_chunked(_CHUNK):
                if ctx.cancelled():
                    raise asyncio.CancelledError()
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                elapsed = max(time.time() - started, 1e-3)
                ctx.progress(downloaded, total, downloaded / elapsed)
    return dest


@register_downloader
class MediaPlatformDownloader(Downloader):
    id = "mediaplat"
    display_name = "Cloud-Hoster (Mediafire / Pixeldrain / GoFile / Kraken)"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        h = _host(source).lower()
        return h in _SUPPORTED_HOSTS

    async def download(self, ctx: MLContext) -> Path:
        ctx.status("downloading")
        dest_dir = ctx.temp_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        host = _host(ctx.source).lower()
        resolver = _RESOLVERS.get(host)
        if resolver is None:
            raise RuntimeError(f"MediaPlatform: no resolver for host `{host}`")

        direct, filename = await resolver(ctx.source)
        filename = unquote(filename)[:200] or "download.bin"
        dest = dest_dir / filename
        logger.info(
            "MediaPlat resolved %s -> %s (name=%s)",
            ctx.source[:80], direct[:80], filename,
        )
        return await _stream_to_file(direct, dest, ctx)
