"""Dropbox uploader (OAuth refresh-token flow).

Users paste `refresh_token + app_key + app_secret` obtained from their
Dropbox app console (app.dropbox.com/developers/apps). The SDK handles
short-lived access-token refresh automatically. Large files go through a
resumable upload session; small files use the one-shot endpoint.

The `dropbox` package is synchronous — calls are wrapped in
`asyncio.to_thread` so the bot's event loop keeps running.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import QuotaInfo, Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.dropbox")

# Dropbox's one-shot upload endpoint hard-caps at 150 MB; anything above
# must use the session-based resumable flow.
_SINGLE_SHOT_LIMIT = 150 * 1024 * 1024
_CHUNK = 8 * 1024 * 1024


def _client(refresh_token: str, app_key: str, app_secret: str):
    import dropbox  # type: ignore

    return dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
    )


def _upload_sync(
    refresh_token: str,
    app_key: str,
    app_secret: str,
    local_path: Path,
    dest_path: str,
) -> str:
    import dropbox  # type: ignore
    from dropbox.files import CommitInfo, UploadSessionCursor, WriteMode  # type: ignore

    dbx = _client(refresh_token, app_key, app_secret)
    size = local_path.stat().st_size
    mode = WriteMode("overwrite")

    with open(local_path, "rb") as f:
        if size <= _SINGLE_SHOT_LIMIT:
            meta = dbx.files_upload(f.read(), dest_path, mode=mode)
        else:
            start = dbx.files_upload_session_start(f.read(_CHUNK))
            cursor = UploadSessionCursor(
                session_id=start.session_id, offset=f.tell()
            )
            commit = CommitInfo(path=dest_path, mode=mode)
            while size - f.tell() > _CHUNK:
                dbx.files_upload_session_append_v2(f.read(_CHUNK), cursor)
                cursor.offset = f.tell()
            meta = dbx.files_upload_session_finish(
                f.read(_CHUNK), cursor, commit
            )

    # Prefer a shared link; fall back to a path-style reference if the
    # share endpoint rejects (e.g. scoped apps without sharing.write).
    try:
        link = dbx.sharing_create_shared_link_with_settings(meta.path_display)
        return link.url
    except dropbox.exceptions.ApiError:
        return f"dropbox://{meta.path_display}"


@register_uploader
class DropboxUploader(Uploader):
    id = "dropbox"
    display_name = "Dropbox"
    needs_credentials = True
    python_import_required = "dropbox"

    async def is_configured(self, user_id: int) -> bool:
        rt = await Accounts.get_secret(user_id, self.id, "refresh_token")
        ak = await Accounts.get_secret(user_id, self.id, "app_key")
        sec = await Accounts.get_secret(user_id, self.id, "app_secret")
        return bool(rt and ak and sec)

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        rt = await Accounts.get_secret(user_id, self.id, "refresh_token")
        ak = await Accounts.get_secret(user_id, self.id, "app_key")
        sec = await Accounts.get_secret(user_id, self.id, "app_secret")
        if not (rt and ak and sec):
            return False, "Need refresh_token + app_key + app_secret"

        def _probe() -> str:
            acct = _client(rt, ak, sec).users_get_current_account()
            return acct.name.display_name

        try:
            name = await asyncio.to_thread(_probe)
            return True, f"linked as {name}"
        except Exception as exc:
            return False, f"Dropbox probe failed: {exc}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        rt = await Accounts.get_secret(ctx.user_id, self.id, "refresh_token")
        ak = await Accounts.get_secret(ctx.user_id, self.id, "app_key")
        sec = await Accounts.get_secret(ctx.user_id, self.id, "app_secret")
        if not (rt and ak and sec):
            return UploadResult(self.id, ok=False, message="Dropbox not configured")

        ctx.status("uploading")

        account = await Accounts.get_account(ctx.user_id, self.id)
        folder = (account.get("folder_path") or "").strip().rstrip("/")
        dest_path = f"{folder}/{local_path.name}" if folder else f"/{local_path.name}"
        if not dest_path.startswith("/"):
            dest_path = "/" + dest_path

        try:
            url = await asyncio.to_thread(
                _upload_sync, rt, ak, sec, local_path, dest_path
            )
        except Exception as exc:
            logger.warning(f"Dropbox upload failed: {exc}")
            return UploadResult(self.id, ok=False, message=f"Dropbox upload failed: {exc}")

        return UploadResult(self.id, ok=True, url=url)

    async def get_quota(self, user_id: int) -> QuotaInfo | None:
        rt = await Accounts.get_secret(user_id, self.id, "refresh_token")
        ak = await Accounts.get_secret(user_id, self.id, "app_key")
        sec = await Accounts.get_secret(user_id, self.id, "app_secret")
        if not (rt and ak and sec):
            return None

        def _probe():
            usage = _client(rt, ak, sec).users_get_space_usage()
            used = int(getattr(usage, "used", 0) or 0)
            allocation = getattr(usage, "allocation", None)
            total = None
            if allocation is not None:
                # individual vs team allocation — both expose .allocated
                total = int(
                    getattr(allocation.get_individual(), "allocated", 0)
                    if allocation.is_individual()
                    else getattr(allocation.get_team(), "allocated", 0)
                ) or None
            return used, total

        try:
            used, total = await asyncio.to_thread(_probe)
        except Exception:
            return None
        free = (total - used) if (total is not None) else None
        return QuotaInfo(used_bytes=used, total_bytes=total, free_bytes=free)
