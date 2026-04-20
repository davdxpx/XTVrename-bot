"""Box uploader (OAuth with rotating refresh tokens).

Users paste `refresh_token + client_id + client_secret` from a Box
Custom App (app.box.com/developers/console, OAuth 2.0 auth method).
Box rotates refresh tokens on every refresh, so the `store_tokens`
callback captures the newest pair and the async wrapper persists it
back via `Accounts.set_secret` after the SDK call returns.

boxsdk is synchronous — calls are wrapped in `asyncio.to_thread`.
Files above 50 MB go through Box's chunked upload session.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import QuotaInfo, Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.box")

_CHUNKED_THRESHOLD = 50 * 1024 * 1024


def _build_client(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    token_sink: dict,
):
    """Return a Box `Client` + `OAuth2` pair. `token_sink` receives the
    latest (access, refresh) pair on every refresh so the caller can
    persist rotated refresh tokens."""
    from boxsdk import Client, OAuth2  # type: ignore

    def _store(access: str, refresh: str) -> None:
        token_sink["access_token"] = access
        token_sink["refresh_token"] = refresh

    oauth = OAuth2(
        client_id=client_id,
        client_secret=client_secret,
        access_token=None,
        refresh_token=refresh_token,
        store_tokens=_store,
    )
    return Client(oauth), oauth


def _upload_sync(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    local_path: Path,
    folder_id: str,
    token_sink: dict,
) -> str:
    client, _oauth = _build_client(
        refresh_token, client_id, client_secret, token_sink
    )
    size = local_path.stat().st_size
    if size >= _CHUNKED_THRESHOLD:
        uploader = client.folder(folder_id).get_chunked_uploader(
            file_path=str(local_path), file_name=local_path.name
        )
        uploaded = uploader.start()
    else:
        uploaded = client.folder(folder_id).upload(
            str(local_path), file_name=local_path.name
        )
    # Shared-link creation requires item.get_shared_link(); fall back to
    # the direct Box file URL if the app lacks share permissions.
    try:
        return uploaded.get_shared_link()
    except Exception:
        return f"https://app.box.com/file/{uploaded.id}"


def _probe_sync(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    token_sink: dict,
) -> str:
    client, _ = _build_client(
        refresh_token, client_id, client_secret, token_sink
    )
    user = client.user().get()
    return getattr(user, "login", None) or getattr(user, "name", "account")


async def _persist_rotated(user_id: int, token_sink: dict) -> None:
    """If the SDK refreshed the refresh token, write the new one back so
    the next upload doesn't fail with `invalid_grant`."""
    new_refresh = token_sink.get("refresh_token")
    if new_refresh:
        await Accounts.set_secret(user_id, "box", "refresh_token", new_refresh)


@register_uploader
class BoxUploader(Uploader):
    id = "box"
    display_name = "Box"
    needs_credentials = True
    python_import_required = "boxsdk"

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

        sink: dict = {}
        try:
            login = await asyncio.to_thread(_probe_sync, rt, cid, cs, sink)
        except Exception as exc:
            return False, f"Box probe failed: {exc}"
        await _persist_rotated(user_id, sink)
        return True, f"linked as {login}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        rt = await Accounts.get_secret(ctx.user_id, self.id, "refresh_token")
        cid = await Accounts.get_secret(ctx.user_id, self.id, "client_id")
        cs = await Accounts.get_secret(ctx.user_id, self.id, "client_secret")
        if not (rt and cid and cs):
            return UploadResult(self.id, ok=False, message="Box not configured")

        ctx.status("uploading")
        account = await Accounts.get_account(ctx.user_id, self.id)
        folder_id = str(account.get("folder_id") or "0")  # "0" == All Files root

        sink: dict = {}
        try:
            url = await asyncio.to_thread(
                _upload_sync, rt, cid, cs, local_path, folder_id, sink
            )
        except Exception as exc:
            logger.warning(f"Box upload failed: {exc}")
            await _persist_rotated(ctx.user_id, sink)
            return UploadResult(self.id, ok=False, message=f"Box upload failed: {exc}")
        await _persist_rotated(ctx.user_id, sink)
        return UploadResult(self.id, ok=True, url=url)

    async def get_quota(self, user_id: int) -> QuotaInfo | None:
        rt = await Accounts.get_secret(user_id, self.id, "refresh_token")
        cid = await Accounts.get_secret(user_id, self.id, "client_id")
        cs = await Accounts.get_secret(user_id, self.id, "client_secret")
        if not (rt and cid and cs):
            return None

        sink: dict = {}

        def _probe():
            client, _ = _build_client(rt, cid, cs, sink)
            user = client.user().get()
            used = int(getattr(user, "space_used", 0) or 0)
            # Box reports -1 to mean "unlimited"; convert that to None
            # so the UI draws a "linked" badge instead of a 0-width bar.
            total_raw = getattr(user, "space_amount", None)
            total = int(total_raw) if total_raw and int(total_raw) > 0 else None
            return used, total

        try:
            used, total = await asyncio.to_thread(_probe)
        except Exception:
            return None
        await _persist_rotated(user_id, sink)
        free = (total - used) if total is not None else None
        return QuotaInfo(used_bytes=used, total_bytes=total, free_bytes=free)
