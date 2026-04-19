"""MEGA uploader using the mega.py python wrapper.

mega.py is synchronous and chatty; all calls go through asyncio.to_thread
so they don't stall the bot's event loop. The Mega SDK is marked as a
python_import so the uploader is automatically hidden on hosts that
haven't installed it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.mega")


def _login_sync(email: str, password: str):
    from mega import Mega  # type: ignore

    mega = Mega()
    return mega.login(email, password)


@register_uploader
class MEGAUploader(Uploader):
    id = "mega"
    display_name = "MEGA.nz"
    python_import_required = "mega"

    async def is_configured(self, user_id: int) -> bool:
        email = (await Accounts.get_account(user_id, self.id)).get("email")
        password = await Accounts.get_secret(user_id, self.id, "password")
        return bool(email and password)

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        email = (await Accounts.get_account(user_id, self.id)).get("email")
        password = await Accounts.get_secret(user_id, self.id, "password")
        if not (email and password):
            return False, "MEGA needs email + password"
        try:
            await asyncio.to_thread(_login_sync, email, password)
            return True, "MEGA login OK"
        except Exception as exc:
            return False, f"MEGA login failed: {exc}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        email = (await Accounts.get_account(ctx.user_id, self.id)).get("email")
        password = await Accounts.get_secret(ctx.user_id, self.id, "password")
        if not (email and password):
            return UploadResult(self.id, ok=False, message="MEGA not configured")

        ctx.status("uploading")

        def _upload_sync() -> str:
            m = _login_sync(email, password)
            node = m.upload(str(local_path))
            return m.get_upload_link(node)

        try:
            link = await asyncio.to_thread(_upload_sync)
        except Exception as exc:
            return UploadResult(self.id, ok=False, message=f"MEGA upload failed: {exc}")
        return UploadResult(self.id, ok=True, url=link)
