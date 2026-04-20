"""Seafile native uploader (REST API).

Seafile has a WebDAV add-on but the official REST API is leaner and
avoids the add-on's Basic-auth quirks. Users paste an API token from
their Seafile profile along with the server URL and library (repo) ID.

Uses plain `aiohttp`, no extra PyPI dep needed.
"""

from __future__ import annotations

from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import QuotaInfo, Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.seafile")


def _headers(api_token: str) -> dict:
    return {
        "Authorization": f"Token {api_token}",
        "Accept": "application/json",
    }


@register_uploader
class SeafileUploader(Uploader):
    id = "seafile"
    display_name = "Seafile"
    needs_credentials = True

    async def _creds(self, user_id: int) -> dict:
        account = await Accounts.get_account(user_id, self.id)
        return {
            "server_url": (account.get("server_url") or "").rstrip("/"),
            "library_id": account.get("library_id") or "",
            "parent_dir": (account.get("parent_dir") or "/").strip() or "/",
            "folder_template": (account.get("folder_template") or "").strip(),
            "api_token": await Accounts.get_secret(user_id, self.id, "api_token"),
        }

    async def is_configured(self, user_id: int) -> bool:
        c = await self._creds(user_id)
        return bool(c["server_url"] and c["library_id"] and c["api_token"])

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        import aiohttp

        c = await self._creds(user_id)
        if not (c["server_url"] and c["library_id"] and c["api_token"]):
            return False, "Need server_url + library_id + api_token"

        url = f"{c['server_url']}/api2/auth/ping/"
        try:
            async with aiohttp.ClientSession() as http, http.get(
                url, headers=_headers(c["api_token"])
            ) as resp:
                if resp.status == 200:
                    # Seafile's /auth/ping returns the string "pong".
                    return True, "linked"
                return False, f"ping {resp.status}"
        except Exception as exc:
            return False, f"Seafile probe failed: {exc}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        import aiohttp

        c = await self._creds(ctx.user_id)
        if not (c["server_url"] and c["library_id"] and c["api_token"]):
            return UploadResult(self.id, ok=False, message="Seafile not configured")

        ctx.status("uploading")

        parent_dir = c["parent_dir"]
        if c["folder_template"]:
            rendered = ctx.resolve_path(c["folder_template"], local_path).strip()
            if rendered:
                if not rendered.startswith("/"):
                    rendered = "/" + rendered
                parent_dir = rendered.rstrip("/") or "/"

        # Seafile's two-step upload: first fetch a per-library upload link,
        # then POST the file as multipart/form-data. Upload links are
        # single-use and short-lived, so we can't cache them.
        link_url = (
            f"{c['server_url']}/api2/repos/{c['library_id']}/upload-link/"
        )
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    link_url, headers=_headers(c["api_token"])
                ) as link_resp:
                    if link_resp.status != 200:
                        body = await link_resp.text()
                        return UploadResult(
                            self.id,
                            ok=False,
                            message=f"upload-link {link_resp.status}: {body[:200]}",
                        )
                    upload_url = (await link_resp.json()).strip('"')

                form = aiohttp.FormData()
                form.add_field("parent_dir", parent_dir)
                form.add_field("replace", "1")
                with open(local_path, "rb") as f:
                    form.add_field(
                        "file", f, filename=local_path.name,
                        content_type="application/octet-stream",
                    )
                    async with http.post(
                        upload_url, data=form, headers=_headers(c["api_token"])
                    ) as up_resp:
                        if up_resp.status not in (200, 201):
                            body = await up_resp.text()
                            return UploadResult(
                                self.id,
                                ok=False,
                                message=f"upload {up_resp.status}: {body[:200]}",
                            )
                        uploaded = await up_resp.json()
        except Exception as exc:
            logger.warning(f"Seafile upload failed: {exc}")
            return UploadResult(self.id, ok=False, message=f"Seafile upload failed: {exc}")

        # Seafile's upload endpoint returns a list of uploaded items —
        # use the file ID to build a stable web URL.
        file_id = (
            uploaded[0].get("id")
            if isinstance(uploaded, list) and uploaded
            else None
        )
        if file_id:
            web_url = (
                f"{c['server_url']}/lib/{c['library_id']}/file"
                f"{parent_dir.rstrip('/')}/{local_path.name}"
            )
            return UploadResult(self.id, ok=True, url=web_url)
        return UploadResult(self.id, ok=True, url=c["server_url"])

    async def get_quota(self, user_id: int) -> QuotaInfo | None:
        import aiohttp

        c = await self._creds(user_id)
        if not (c["server_url"] and c["api_token"]):
            return None
        url = f"{c['server_url']}/api2/account/info/"
        try:
            async with aiohttp.ClientSession() as http, http.get(
                url,
                headers=_headers(c["api_token"]),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception:
            return None
        used = int(data.get("usage") or 0)
        total_raw = data.get("total")
        # Seafile returns -2 for "unlimited" in some configurations; treat
        # anything non-positive as unlimited so the UI hides the bar.
        total = int(total_raw) if total_raw and int(total_raw) > 0 else None
        free = (total - used) if total is not None else None
        return QuotaInfo(used_bytes=used, total_bytes=total, free_bytes=free)
