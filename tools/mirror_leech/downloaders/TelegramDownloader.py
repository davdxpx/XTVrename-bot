"""Download a Telegram file (document / video / audio / photo) referenced
by a Message.from a previous chat interaction to the task's temp dir.

`source` for this downloader is expected to be a JSON-y string the
controller builds: `tg:{chat_id}:{message_id}`. The concrete Pyrogram
client is stashed on `ctx` by the controller, not imported here.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from utils.log import get_logger

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.Tasks import MLContext

logger = get_logger("mirror_leech.telegram")

_TG_REF_RE = re.compile(r"^tg:(-?\d+):(\d+)$")


@register_downloader
class TelegramDownloader(Downloader):
    id = "telegram"
    display_name = "Telegram file"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        return bool(_TG_REF_RE.match(source))

    async def download(self, ctx: MLContext) -> Path:
        ctx.status("downloading")
        match = _TG_REF_RE.match(ctx.source)
        if not match:
            raise ValueError(f"TelegramDownloader: unexpected source format {ctx.source!r}")
        chat_id = int(match.group(1))
        message_id = int(match.group(2))

        # `client` is provided through an MLContext extension the controller
        # attaches when it creates the context from a bot handler. Tests
        # supply a stub. Attribute access falls through to AttributeError
        # so misuse is caught fast.
        client = getattr(ctx, "client", None)
        if client is None:
            raise RuntimeError("TelegramDownloader requires ctx.client (bot instance)")

        msg = await client.get_messages(chat_id, message_id)
        if not msg:
            raise RuntimeError(f"Telegram message {chat_id}:{message_id} not found")

        ctx.temp_dir.mkdir(parents=True, exist_ok=True)

        started = time.time()

        def _progress(done: int, total: int):
            elapsed = max(time.time() - started, 1e-3)
            ctx.progress(float(done), float(total or 0), done / elapsed)

        local_path = await client.download_media(
            msg,
            file_name=str(ctx.temp_dir) + "/",
            progress=_progress,
        )
        return Path(local_path)
