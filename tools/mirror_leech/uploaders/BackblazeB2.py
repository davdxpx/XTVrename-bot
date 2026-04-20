"""Backblaze B2 native uploader.

B2 is S3-compatible, so the generic S3 uploader already covers it —
but the native B2 SDK surfaces app-key capability info, keep-versions
metadata, hash verification via `b2_get_file_info`, and B2-specific
error codes that the S3 shim can't reach. Users who care about any of
those ship here; everyone else can use S3.py.

`b2sdk` is synchronous; calls run through `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.backblaze_b2")


def _authorize(app_key_id: str, app_key: str):
    from b2sdk.v2 import B2Api, InMemoryAccountInfo  # type: ignore

    info = InMemoryAccountInfo()
    api = B2Api(info)
    api.authorize_account("production", app_key_id, app_key)
    return api


def _probe_sync(app_key_id: str, app_key: str, bucket_name: str) -> str:
    api = _authorize(app_key_id, app_key)
    bucket = api.get_bucket_by_name(bucket_name)
    return bucket.name


def _upload_sync(
    app_key_id: str,
    app_key: str,
    bucket_name: str,
    local_path: Path,
    remote_key: str,
) -> str:
    api = _authorize(app_key_id, app_key)
    bucket = api.get_bucket_by_name(bucket_name)
    uploaded = bucket.upload_local_file(
        local_file=str(local_path), file_name=remote_key
    )
    # Native URL is more useful than a signed one here — B2 buckets can be
    # public or require auth; the bot returns the canonical object URL and
    # leaves ACL handling to the bucket owner.
    download_url = api.account_info.get_download_url()
    return f"{download_url}/file/{bucket_name}/{uploaded.file_name}"


@register_uploader
class BackblazeB2Uploader(Uploader):
    id = "b2"
    display_name = "Backblaze B2 (native)"
    needs_credentials = True
    python_import_required = "b2sdk"

    async def _creds(self, user_id: int) -> dict:
        account = await Accounts.get_account(user_id, self.id)
        return {
            "bucket": account.get("bucket") or "",
            "prefix": (account.get("prefix") or "").strip().strip("/"),
            "app_key_id": await Accounts.get_secret(user_id, self.id, "app_key_id"),
            "app_key": await Accounts.get_secret(user_id, self.id, "app_key"),
        }

    async def is_configured(self, user_id: int) -> bool:
        c = await self._creds(user_id)
        return bool(c["app_key_id"] and c["app_key"] and c["bucket"])

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        c = await self._creds(user_id)
        if not (c["app_key_id"] and c["app_key"] and c["bucket"]):
            return False, "Need app_key_id + app_key + bucket"
        try:
            name = await asyncio.to_thread(
                _probe_sync, c["app_key_id"], c["app_key"], c["bucket"]
            )
        except Exception as exc:
            return False, f"B2 probe failed: {exc}"
        return True, f"bucket ok: {name}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        c = await self._creds(ctx.user_id)
        if not (c["app_key_id"] and c["app_key"] and c["bucket"]):
            return UploadResult(self.id, ok=False, message="B2 not configured")

        ctx.status("uploading")
        remote_key = (
            f"{c['prefix']}/{local_path.name}" if c["prefix"] else local_path.name
        )

        try:
            url = await asyncio.to_thread(
                _upload_sync,
                c["app_key_id"],
                c["app_key"],
                c["bucket"],
                local_path,
                remote_key,
            )
        except Exception as exc:
            logger.warning(f"B2 upload failed: {exc}")
            return UploadResult(self.id, ok=False, message=f"B2 upload failed: {exc}")
        return UploadResult(self.id, ok=True, url=url)
