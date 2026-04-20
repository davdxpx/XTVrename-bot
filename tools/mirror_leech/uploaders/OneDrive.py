"""OneDrive uploader (Microsoft Graph, MSAL-refreshed OAuth).

Users paste `refresh_token + client_id + tenant` obtained from an Azure
AD / Entra app registration (Mobile/Desktop Application type). For
personal Microsoft accounts the tenant is `common`; for org accounts
paste the directory (tenant) ID.

MSAL refreshes the short-lived Graph access token; `aiohttp` performs
the actual file upload. Files below 4 MB go through the one-shot
content endpoint, larger files through an upload session with 10 MiB
chunks (multiple of the 320 KiB minimum Graph mandates).
"""

from __future__ import annotations

from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.onedrive")

_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPES = ["Files.ReadWrite", "offline_access"]
_SINGLE_SHOT_LIMIT = 4 * 1024 * 1024
_CHUNK = 10 * 1024 * 1024  # 10 MiB — multiple of 320 KiB Graph requirement


async def _refresh_access_token(refresh_token: str, client_id: str, tenant: str) -> str:
    import msal  # type: ignore

    authority = f"https://login.microsoftonline.com/{tenant or 'common'}"
    app = msal.PublicClientApplication(client_id, authority=authority)
    # Note: `acquire_token_by_refresh_token` is a family-token primitive
    # officially supported for FOCI flows, the standard path for headless
    # bots that cannot run interactive sign-in.
    result = app.acquire_token_by_refresh_token(refresh_token, scopes=_SCOPES)
    token = (result or {}).get("access_token")
    if not token:
        raise RuntimeError(f"OneDrive OAuth refresh failed: {result}")
    return token


async def _upload_small(
    token: str, dest_path: str, local_path: Path
) -> dict:
    import aiohttp

    url = f"{_GRAPH}/me/drive/root:{dest_path}:/content"
    headers = {"Authorization": f"Bearer {token}"}
    with open(local_path, "rb") as f:
        data = f.read()
    async with aiohttp.ClientSession() as session, session.put(
        url, data=data, headers=headers
    ) as resp:
        body = await resp.json()
    return body


async def _upload_large(
    token: str, dest_path: str, local_path: Path
) -> dict:
    import aiohttp

    session_url = f"{_GRAPH}/me/drive/root:{dest_path}:/createUploadSession"
    headers = {"Authorization": f"Bearer {token}"}
    size = local_path.stat().st_size

    async with aiohttp.ClientSession() as http:
        async with http.post(session_url, headers=headers) as resp:
            body = await resp.json()
        upload_url = body.get("uploadUrl")
        if not upload_url:
            raise RuntimeError(f"OneDrive createUploadSession failed: {body}")

        last: dict = {}
        with open(local_path, "rb") as f:
            offset = 0
            while offset < size:
                chunk = f.read(_CHUNK)
                if not chunk:
                    break
                end = offset + len(chunk) - 1
                chunk_headers = {
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                }
                async with http.put(
                    upload_url, data=chunk, headers=chunk_headers
                ) as chunk_resp:
                    last = await chunk_resp.json()
                offset = end + 1
        return last


@register_uploader
class OneDriveUploader(Uploader):
    id = "onedrive"
    display_name = "OneDrive"
    needs_credentials = True
    python_import_required = "msal"

    async def is_configured(self, user_id: int) -> bool:
        rt = await Accounts.get_secret(user_id, self.id, "refresh_token")
        cid = await Accounts.get_secret(user_id, self.id, "client_id")
        tenant = await Accounts.get_secret(user_id, self.id, "tenant")
        return bool(rt and cid and tenant)

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        import aiohttp

        rt = await Accounts.get_secret(user_id, self.id, "refresh_token")
        cid = await Accounts.get_secret(user_id, self.id, "client_id")
        tenant = await Accounts.get_secret(user_id, self.id, "tenant")
        if not (rt and cid and tenant):
            return False, "Need refresh_token + client_id + tenant"
        try:
            token = await _refresh_access_token(rt, cid, tenant)
            async with aiohttp.ClientSession() as session, session.get(
                f"{_GRAPH}/me/drive/quota",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                body = await resp.json()
        except Exception as exc:
            return False, f"OneDrive probe failed: {exc}"

        quota = (body or {}).get("quota") or body
        remaining = quota.get("remaining")
        if remaining is None:
            return True, "OneDrive linked (quota unavailable)"
        free_gb = remaining / (1024**3)
        return True, f"{free_gb:.1f} GB free"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        rt = await Accounts.get_secret(ctx.user_id, self.id, "refresh_token")
        cid = await Accounts.get_secret(ctx.user_id, self.id, "client_id")
        tenant = await Accounts.get_secret(ctx.user_id, self.id, "tenant")
        if not (rt and cid and tenant):
            return UploadResult(self.id, ok=False, message="OneDrive not configured")

        ctx.status("uploading")
        try:
            token = await _refresh_access_token(rt, cid, tenant)
        except Exception as exc:
            return UploadResult(self.id, ok=False, message=f"OneDrive auth failed: {exc}")

        account = await Accounts.get_account(ctx.user_id, self.id)
        folder = (account.get("folder_path") or "").strip().strip("/")
        rel = f"{folder}/{local_path.name}" if folder else local_path.name
        dest_path = "/" + rel.lstrip("/")

        size = local_path.stat().st_size
        try:
            if size <= _SINGLE_SHOT_LIMIT:
                body = await _upload_small(token, dest_path, local_path)
            else:
                body = await _upload_large(token, dest_path, local_path)
        except Exception as exc:
            logger.warning(f"OneDrive upload failed: {exc}")
            return UploadResult(self.id, ok=False, message=f"OneDrive upload failed: {exc}")

        web_url = body.get("webUrl") if isinstance(body, dict) else None
        if not web_url:
            return UploadResult(self.id, ok=False, message=f"OneDrive: {body}")
        return UploadResult(self.id, ok=True, url=web_url)
