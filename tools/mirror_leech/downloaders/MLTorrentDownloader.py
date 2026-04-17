"""Mirror-Leech downloader for magnet / .torrent sources.

Wraps the aria2c RPC daemon that torrent-edition's Dockerfile / compose
runs on `localhost:6800`. The full /torrent UI lives in
`tools.TorrentDownloader` and is untouched by this module — we just
share the same aria2 instance so both flows don't fight over the same
backend.

Registered only on the torrent-edition branch (main ships without this
file). On deploy hosts without aria2 the downloader's `available()`
check fails softly.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
import xmlrpc.client
from pathlib import Path

from utils.log import get_logger

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.Tasks import MLContext

logger = get_logger("mirror_leech.torrent")

_MAGNET_RE = re.compile(r"^magnet:\?", re.IGNORECASE)
_TORRENT_EXT_RE = re.compile(r"\.torrent($|\?)", re.IGNORECASE)

_ARIA2_RPC_URL = "http://localhost:6800/rpc"
_POLL_INTERVAL_SEC = 3


@register_downloader
class MLTorrentDownloader(Downloader):
    id = "torrent"
    display_name = "Torrent / Magnet (aria2)"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        if not (_MAGNET_RE.match(source) or _TORRENT_EXT_RE.search(source)):
            return False
        # Only offer ourselves when aria2c is actually reachable. No point
        # letting /ml queue a torrent on a host that can't fulfil it.
        return await _aria2_available()

    async def download(self, ctx: MLContext) -> Path:
        ctx.status("downloading")
        ctx.temp_dir.mkdir(parents=True, exist_ok=True)

        server = xmlrpc.client.ServerProxy(_ARIA2_RPC_URL)
        loop = asyncio.get_event_loop()
        options = {
            "dir": str(ctx.temp_dir),
            "max-connection-per-server": "16",
            "split": "16",
            "seed-time": "0",
            "bt-stop-timeout": "300",
        }
        try:
            gid = await loop.run_in_executor(
                None, lambda: server.aria2.addUri([ctx.source], options)
            )
        except Exception as exc:
            raise RuntimeError(f"aria2 addUri failed: {exc}") from exc

        started = time.time()
        followed_gid: str | None = None
        while True:
            if ctx.cancelled():
                try:
                    await loop.run_in_executor(
                        None, lambda: server.aria2.remove(followed_gid or gid)
                    )
                except Exception:
                    pass
                raise asyncio.CancelledError()

            try:
                status = await loop.run_in_executor(
                    None, lambda: server.aria2.tellStatus(followed_gid or gid)
                )
            except Exception as exc:
                raise RuntimeError(f"aria2 tellStatus failed: {exc}") from exc

            # Magnet metadata downloads produce a followedBy gid once the
            # actual file transfer starts — follow it so the progress numbers
            # reflect real bytes instead of the tiny metadata blob.
            followed_by = status.get("followedBy") or []
            if followed_by and followed_gid is None:
                followed_gid = followed_by[0]
                continue

            state = status.get("status")
            if state == "complete":
                break
            if state == "error":
                msg = status.get("errorMessage") or "unknown aria2 error"
                raise RuntimeError(f"aria2 reported error: {msg}")
            if state == "removed":
                raise asyncio.CancelledError()

            total = float(status.get("totalLength") or 0)
            done = float(status.get("completedLength") or 0)
            speed = float(status.get("downloadSpeed") or 0)
            ctx.progress(done, total, speed)
            await asyncio.sleep(_POLL_INTERVAL_SEC)

        # Locate the finished payload. aria2 may have produced a single file
        # or a directory full of them; hand back the biggest single file to
        # keep uploader implementations simple. Callers who want folder-wide
        # uploads can tweak this later.
        final_path = _pick_largest(ctx.temp_dir)
        if final_path is None:
            raise RuntimeError(
                "Torrent completed but nothing landed on disk — aria2 wrote "
                f"to {ctx.temp_dir}"
            )
        _ = started  # silence lint
        return final_path


async def _aria2_available() -> bool:
    """Quick liveness probe so `accepts()` doesn't queue torrents on
    hosts without aria2."""
    if shutil.which("aria2c") is None:
        return False
    try:
        server = xmlrpc.client.ServerProxy(_ARIA2_RPC_URL)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: server.aria2.getVersion())
        return True
    except Exception:
        return False


def _pick_largest(root: Path) -> Path | None:
    best: Path | None = None
    best_size = -1
    for p in root.rglob("*"):
        if p.is_file():
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > best_size:
                best = p
                best_size = size
    return best
