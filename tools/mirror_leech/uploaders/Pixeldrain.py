"""Pixeldrain uploader.

Anonymous uploads work. An API key elevates the upload into the user's
account (enabling longer retention, file listing, etc.).
"""

from __future__ import annotations

from pathlib import Path

from utils.log import get_logger

from tools.mirror_leech.uploaders import Uploader, register_uploader
from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult

logger = get_logger("mirror_leech.pixeldrain")

PIXELDRAIN_API = "https://pixeldrain.com/api"


@register_uploader
class PixeldrainUploader(Uploader):
    id = "pixeldrain"
    display_name = "Pixeldrain"
    needs_credentials = False

    async def is_configured(self, user_id: int) -> bool:
        return True  # anonymous fallback

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{PIXELDRAIN_API}/misc/viewer") as resp:
                    resp.raise_for_status()
            return True, "Pixeldrain API reachable"
        except Exception as exc:
            return False, f"Pixeldrain unreachable: {exc}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        import aiohttp
        from base64 import b64encode

        ctx.status("uploading")
        api_key = await Accounts.get_secret(ctx.user_id, self.id, "api_key")
        headers = {}
        if api_key:
            headers["Authorization"] = "Basic " + b64encode(f":{api_key}".encode()).decode()

        async with aiohttp.ClientSession() as session:
            with local_path.open("rb") as fp:
                async with session.post(
                    f"{PIXELDRAIN_API}/file", data=fp, headers=headers
                ) as resp:
                    body = await resp.json()

        file_id = body.get("id")
        if not file_id:
            return UploadResult(self.id, ok=False, message=f"Pixeldrain: {body}")
        return UploadResult(
            self.id,
            ok=True,
            url=f"https://pixeldrain.com/u/{file_id}",
        )
