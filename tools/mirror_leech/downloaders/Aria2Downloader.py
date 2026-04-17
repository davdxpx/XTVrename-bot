# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Aria2 RPC downloader.

Uses a local or remote aria2 daemon (`aria2c --enable-rpc`) via aria2p
to get multi-connection HTTP(S) / FTP pulls. Only HTTP-family schemes
are routed here — the daemon is NOT exposed to any other protocol by
this bot.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.Tasks import MLContext
from utils.log import get_logger

logger = get_logger("mirror_leech.aria2")

_HTTP_SCHEME = re.compile(r"^(https?|ftp)://", re.IGNORECASE)


def _rpc_endpoint() -> tuple[str, int, str]:
    """Return (host, port, secret) from env with safe defaults."""
    url = os.getenv("ARIA2_RPC_URL", "http://127.0.0.1:6800/jsonrpc")
    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else "http://127.0.0.1"
    port = parsed.port or 6800
    secret = os.getenv("ARIA2_RPC_SECRET", "")
    return host, port, secret


@register_downloader
class Aria2Downloader(Downloader):
    id = "aria2"
    display_name = "Aria2 Multi-Connection"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        if not _HTTP_SCHEME.match(source):
            return False
        try:
            import aria2p  # type: ignore
        except ImportError:
            return False
        host, port, secret = _rpc_endpoint()
        try:
            api = aria2p.API(
                aria2p.Client(host=host, port=port, secret=secret, timeout=2)
            )
            await asyncio.to_thread(api.get_stats)
            return True
        except Exception:
            return False

    async def download(self, ctx: MLContext) -> Path:
        import aria2p  # type: ignore

        ctx.status("downloading")
        host, port, secret = _rpc_endpoint()
        dest_dir = ctx.temp_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        api = aria2p.API(
            aria2p.Client(host=host, port=port, secret=secret, timeout=10)
        )
        dl = await asyncio.to_thread(
            api.add_uris,
            [ctx.source],
            options={"dir": str(dest_dir), "max-connection-per-server": "8"},
        )
        gid = dl.gid
        started = time.time()

        try:
            while True:
                if ctx.cancelled():
                    await asyncio.to_thread(api.remove, [dl])
                    await asyncio.to_thread(api.purge)
                    raise asyncio.CancelledError()
                dl = await asyncio.to_thread(api.get_download, gid)
                total = float(dl.total_length or 0)
                done = float(dl.completed_length or 0)
                elapsed = max(time.time() - started, 1e-3)
                ctx.progress(done, total, done / elapsed)
                if dl.is_complete:
                    break
                if dl.has_failed:
                    raise RuntimeError(
                        f"Aria2 reported failure: {dl.error_message or 'unknown'}"
                    )
                await asyncio.sleep(1.5)
        finally:
            # Leave the daemon clean even if the caller cancels.
            with contextlib.suppress(Exception):
                await asyncio.to_thread(api.purge)

        # aria2 may land the file under a sub-path if the URL carries one.
        files = [Path(f.path) for f in dl.files if f.path]
        if files:
            return files[0]
        # Fallback: first regular file under dest_dir.
        for child in dest_dir.iterdir():
            if child.is_file():
                return child
        raise RuntimeError("Aria2Downloader: download completed but no file found")
