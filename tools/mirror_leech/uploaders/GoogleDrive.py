"""Google Drive uploader (OAuth refresh-token flow).

Users obtain a refresh token via Google's OAuth playground or the rclone
helper and paste it into the config UI. The uploader exchanges the
refresh token for a short-lived access token on every upload.
"""

from __future__ import annotations

from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.gdrive")

_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"


async def _refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> str:
    import aiohttp

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with aiohttp.ClientSession() as session, session.post(_OAUTH_TOKEN_URL, data=data) as resp:
        body = await resp.json()
    token = body.get("access_token")
    if not token:
        raise RuntimeError(f"Google OAuth refresh failed: {body}")
    return token


@register_uploader
class GoogleDriveUploader(Uploader):
    id = "gdrive"
    display_name = "Google Drive"
    needs_credentials = True

    async def is_configured(self, user_id: int) -> bool:
        rt = await Accounts.get_secret(user_id, self.id, "refresh_token")
        cid = await Accounts.get_secret(user_id, self.id, "client_id")
        cs = await Accounts.get_secret(user_id, self.id, "client_secret")
        return bool(rt and cid and cs)

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        rt = await Accounts.get_secret(user_id, self.id, "refresh_token")
        cid = await Accounts.get_secret(user_id, self.id, "client_id")
        cs = await Accounts.get_secret(user_id, self.id, "client_secret")
        if not (rt and cid and cs):
            return False, "Need refresh_token + client_id + client_secret"
        try:
            await _refresh_access_token(rt, cid, cs)
            return True, "Google OAuth refresh OK"
        except Exception as exc:
            return False, f"OAuth refresh failed: {exc}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        import aiohttp

        ctx.status("uploading")
        rt = await Accounts.get_secret(ctx.user_id, self.id, "refresh_token")
        cid = await Accounts.get_secret(ctx.user_id, self.id, "client_id")
        cs = await Accounts.get_secret(ctx.user_id, self.id, "client_secret")
        if not (rt and cid and cs):
            return UploadResult(self.id, ok=False, message="Google Drive not configured")

        token = await _refresh_access_token(rt, cid, cs)

        # Default to My Drive root; users can override by setting folder_id
        # from the config UI.
        account = await Accounts.get_account(ctx.user_id, self.id)
        parent = account.get("folder_id")

        metadata = {"name": local_path.name}
        if parent:
            metadata["parents"] = [parent]

        form = aiohttp.FormData()
        form.add_field(
            "metadata",
            __import__("json").dumps(metadata),
            content_type="application/json; charset=UTF-8",
        )
        form.add_field("file", open(local_path, "rb"), filename=local_path.name)  # noqa: SIM115

        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session, session.post(
            _UPLOAD_URL, data=form, headers=headers
        ) as resp:
            body = await resp.json()

        file_id = body.get("id")
        if not file_id:
            return UploadResult(self.id, ok=False, message=f"Google Drive: {body}")
        return UploadResult(
            self.id,
            ok=True,
            url=f"https://drive.google.com/file/d/{file_id}/view",
        )
