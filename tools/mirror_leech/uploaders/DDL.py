"""Direct-Download-Link uploader.

Spins a tiny per-task one-time URL that streams the local file from the
bot's own disk. Requires DDL_BASE_URL + DDL_PORT configured via env /
admin panel; otherwise the uploader is hidden.

The actual aiohttp server lives in plugins/mirror_leech_ui.py so it
shares the bot's event loop — this module just books the URL.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.log import get_logger

logger = get_logger("mirror_leech.ddl")

# Simple in-memory registry of active one-time URLs. Keys are tokens,
# values are {"path": Path, "expires_at": float, "served": bool}.
_ddl_tokens: dict[str, dict] = {}


def claim_file(local_path: Path, ttl_seconds: int = 6 * 3600) -> str:
    """Register `local_path` for one-time download and return its token."""
    import time

    token = secrets.token_urlsafe(24)
    _ddl_tokens[token] = {
        "path": local_path,
        "expires_at": time.time() + ttl_seconds,
        "served": False,
    }
    return token


def lookup_token(token: str) -> dict | None:
    import time

    entry = _ddl_tokens.get(token)
    if not entry:
        return None
    if entry["served"]:
        return None
    if time.time() > entry["expires_at"]:
        _ddl_tokens.pop(token, None)
        return None
    return entry


def mark_served(token: str) -> None:
    entry = _ddl_tokens.get(token)
    if entry:
        entry["served"] = True


@register_uploader
class DDLUploader(Uploader):
    id = "ddl"
    display_name = "Direct Download Link"
    needs_credentials = False

    @classmethod
    def available(cls) -> bool:
        return bool(os.getenv("DDL_BASE_URL"))

    async def is_configured(self, user_id: int) -> bool:
        return self.available()

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        if not self.available():
            return False, "DDL_BASE_URL not set — configure it on the bot host."
        return True, f"DDL base URL: {os.getenv('DDL_BASE_URL')}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        if not self.available():
            return UploadResult(self.id, ok=False, message="DDL_BASE_URL not configured")

        ctx.status("uploading")
        token = claim_file(local_path)
        base = os.getenv("DDL_BASE_URL").rstrip("/")
        return UploadResult(
            self.id,
            ok=True,
            url=f"{base}/ddl/{token}/{local_path.name}",
        )
