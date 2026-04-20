"""Generic S3-compatible uploader.

One uploader covers AWS S3, Wasabi, Cloudflare R2, Backblaze B2 (via S3
API), MinIO, iDrive e2, Storj S3 Gateway, and anything else that speaks
the S3 protocol. Users pick a backend by supplying the right `endpoint`
URL and `region` at paste-time — no code changes needed.

Uses `boto3`, which is synchronous and handles multipart upload
automatically past ~8 MB. Calls run through `asyncio.to_thread` so the
event loop stays free.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.s3")


def _client(
    endpoint_url: str | None,
    region: str | None,
    access_key: str,
    secret_key: str,
):
    import boto3  # type: ignore

    kwargs = {
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if region:
        kwargs["region_name"] = region
    return boto3.client("s3", **kwargs)


def _object_url(endpoint_url: str | None, bucket: str, key: str) -> str:
    """Best-effort public URL.

    Without the bucket's public-read ACL the URL won't actually serve
    the file — but most users uploading via S3 run their own CDN or
    signed-URL flow on top, so we just surface the canonical path so it
    can be plugged into downstream tools.
    """
    if endpoint_url:
        base = endpoint_url.rstrip("/")
        return f"{base}/{bucket}/{key}"
    return f"https://{bucket}.s3.amazonaws.com/{key}"


@register_uploader
class S3Uploader(Uploader):
    id = "s3"
    display_name = "S3-compatible"
    needs_credentials = True
    python_import_required = "boto3"

    async def _creds(self, user_id: int) -> dict:
        """Return the full (plain + secret) config as a flat dict."""
        account = await Accounts.get_account(user_id, self.id)
        return {
            "endpoint_url": account.get("endpoint_url") or None,
            "region": account.get("region") or None,
            "bucket": account.get("bucket") or "",
            "prefix": (account.get("prefix") or "").strip().strip("/"),
            "folder_template": (account.get("folder_template") or "").strip(),
            "access_key": await Accounts.get_secret(user_id, self.id, "access_key"),
            "secret_key": await Accounts.get_secret(user_id, self.id, "secret_key"),
        }

    async def is_configured(self, user_id: int) -> bool:
        c = await self._creds(user_id)
        return bool(c["access_key"] and c["secret_key"] and c["bucket"])

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        c = await self._creds(user_id)
        if not (c["access_key"] and c["secret_key"] and c["bucket"]):
            return False, "Need access_key + secret_key + bucket"

        def _probe() -> None:
            client = _client(
                c["endpoint_url"], c["region"], c["access_key"], c["secret_key"]
            )
            client.head_bucket(Bucket=c["bucket"])

        try:
            await asyncio.to_thread(_probe)
        except Exception as exc:
            return False, f"S3 probe failed: {exc}"
        return True, f"bucket ok: {c['bucket']}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        c = await self._creds(ctx.user_id)
        if not (c["access_key"] and c["secret_key"] and c["bucket"]):
            return UploadResult(self.id, ok=False, message="S3 not configured")

        ctx.status("uploading")
        prefix = c["prefix"]
        if c["folder_template"]:
            prefix = ctx.resolve_path(c["folder_template"], local_path).strip("/")
        key = f"{prefix}/{local_path.name}" if prefix else local_path.name

        def _upload_sync() -> None:
            client = _client(
                c["endpoint_url"], c["region"], c["access_key"], c["secret_key"]
            )
            client.upload_file(str(local_path), c["bucket"], key)

        try:
            await asyncio.to_thread(_upload_sync)
        except Exception as exc:
            logger.warning(f"S3 upload failed: {exc}")
            return UploadResult(self.id, ok=False, message=f"S3 upload failed: {exc}")
        return UploadResult(
            self.id, ok=True, url=_object_url(c["endpoint_url"], c["bucket"], key)
        )
