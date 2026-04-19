"""GoFile uploader.

Anonymous uploads work out of the box. Users who want to claim files
under an account can paste a GoFile API token under `ml_cfg_up_gofile`.
"""

from __future__ import annotations

from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.gofile")

GOFILE_API = "https://api.gofile.io"


@register_uploader
class GoFileUploader(Uploader):
    id = "gofile"
    display_name = "GoFile"
    needs_credentials = False  # anonymous upload works; token is optional

    async def is_configured(self, user_id: int) -> bool:
        # Always usable — anonymous upload is the default.
        return True

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session, session.get(f"{GOFILE_API}/servers") as resp:
                resp.raise_for_status()
                data = await resp.json()
            if data.get("status") != "ok":
                return False, f"GoFile returned status={data.get('status')}"
            return True, "GoFile API reachable"
        except Exception as exc:
            return False, f"GoFile unreachable: {exc}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        import aiohttp

        ctx.status("uploading")

        async with aiohttp.ClientSession() as session:
            # Discover the best upload server
            async with session.get(f"{GOFILE_API}/servers") as resp:
                servers = (await resp.json()).get("data", {}).get("servers", [])
            if not servers:
                return UploadResult(self.id, ok=False, message="GoFile: no servers available")
            server = servers[0]["name"]

            token = await Accounts.get_secret(ctx.user_id, self.id, "token")
            url = f"https://{server}.gofile.io/uploadFile"

            data = aiohttp.FormData()
            data.add_field("file", open(local_path, "rb"), filename=local_path.name)  # noqa: SIM115
            if token:
                data.add_field("token", token)

            async with session.post(url, data=data) as resp:
                body = await resp.json()

        if body.get("status") != "ok":
            return UploadResult(self.id, ok=False, message=f"GoFile: {body}")
        return UploadResult(
            self.id,
            ok=True,
            url=body.get("data", {}).get("downloadPage"),
        )
