"""Generic WebDAV uploader.

Covers Nextcloud, ownCloud, Synology, QNAP, Apache mod_dav, and
anything else speaking the WebDAV protocol over HTTPS with Basic auth.
iCloud Drive users can point this at a third-party CalDAV / WebDAV
bridge and get uploads working too.

Uses plain `aiohttp` (already a project dep), so there's no
`python_import_required` gate — the uploader is always available once
the user has credentials stored.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.webdav")


def _join_url(base: str, path: str) -> str:
    """Join `base` (WebDAV root) with a relative `path` while preserving
    already-URL-encoded base components and encoding only the new path
    segments. Nextcloud / ownCloud URLs contain usernames that may have
    non-ASCII chars — if the user already encoded those, we must not
    double-encode."""
    base = base.rstrip("/")
    parts = [quote(seg, safe="") for seg in path.strip("/").split("/") if seg]
    return base + "/" + "/".join(parts) if parts else base + "/"


def _auth(username: str, password: str):
    import aiohttp

    return aiohttp.BasicAuth(username, password)


@register_uploader
class WebDAVUploader(Uploader):
    id = "webdav"
    display_name = "WebDAV (Nextcloud / ownCloud / …)"
    needs_credentials = True

    async def _creds(self, user_id: int) -> dict:
        account = await Accounts.get_account(user_id, self.id)
        return {
            "url": (account.get("url") or "").rstrip("/"),
            "username": account.get("username") or "",
            "folder": (account.get("folder") or "").strip().strip("/"),
            "password": await Accounts.get_secret(user_id, self.id, "password"),
        }

    async def is_configured(self, user_id: int) -> bool:
        c = await self._creds(user_id)
        return bool(c["url"] and c["username"] and c["password"])

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        import aiohttp

        c = await self._creds(user_id)
        if not (c["url"] and c["username"] and c["password"]):
            return False, "Need url + username + password"

        target = _join_url(c["url"], c["folder"]) if c["folder"] else c["url"] + "/"
        try:
            async with aiohttp.ClientSession() as http, http.request(
                "PROPFIND",
                target,
                auth=_auth(c["username"], c["password"]),
                headers={"Depth": "0"},
            ) as resp:
                if resp.status in (200, 207):
                    return True, "directory accessible"
                return False, f"PROPFIND {resp.status}"
        except Exception as exc:
            return False, f"WebDAV probe failed: {exc}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        import aiohttp

        c = await self._creds(ctx.user_id)
        if not (c["url"] and c["username"] and c["password"]):
            return UploadResult(self.id, ok=False, message="WebDAV not configured")

        ctx.status("uploading")
        rel = (
            f"{c['folder']}/{local_path.name}" if c["folder"] else local_path.name
        )
        target = _join_url(c["url"], rel)
        size = local_path.stat().st_size

        try:
            # Streamed PUT — aiohttp reads the file in ~64 KiB chunks so
            # large files don't get loaded into memory.
            with open(local_path, "rb") as f:
                async with aiohttp.ClientSession() as http, http.put(
                    target,
                    data=f,
                    auth=_auth(c["username"], c["password"]),
                    headers={"Content-Length": str(size)},
                ) as resp:
                    if resp.status not in (200, 201, 204):
                        body = await resp.text()
                        return UploadResult(
                            self.id,
                            ok=False,
                            message=f"WebDAV PUT {resp.status}: {body[:200]}",
                        )
        except Exception as exc:
            logger.warning(f"WebDAV upload failed: {exc}")
            return UploadResult(self.id, ok=False, message=f"WebDAV upload failed: {exc}")

        return UploadResult(self.id, ok=True, url=target)
