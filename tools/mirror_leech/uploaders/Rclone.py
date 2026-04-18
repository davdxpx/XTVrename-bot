"""Rclone uploader — covers 70+ backends via the user's rclone.conf blob.

The config UI stores the user's rclone.conf (encrypted) and a default
remote name. Upload writes the conf to a per-task tempfile and shells
out to `rclone copy`; the tempfile is shredded when the task ends.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from pathlib import Path

from tools.mirror_leech import Accounts
from tools.mirror_leech.Tasks import MLContext, UploadResult
from tools.mirror_leech.uploaders import Uploader, register_uploader
from utils.log import get_logger

logger = get_logger("mirror_leech.rclone")


@register_uploader
class RcloneUploader(Uploader):
    id = "rclone"
    display_name = "Rclone (70+ backends)"
    binary_required = "rclone"

    async def is_configured(self, user_id: int) -> bool:
        conf = await Accounts.get_secret(user_id, self.id, "conf")
        account = await Accounts.get_account(user_id, self.id)
        return bool(conf and account.get("remote"))

    async def test_connection(self, user_id: int) -> tuple[bool, str]:
        conf = await Accounts.get_secret(user_id, self.id, "conf")
        account = await Accounts.get_account(user_id, self.id)
        remote = account.get("remote")
        if not conf or not remote:
            return False, "Rclone needs both a config blob and a remote:path"
        proc = await _run_rclone(conf, ["lsd", remote], timeout=15)
        if proc.returncode == 0:
            return True, f"rclone lsd {remote} OK"
        return False, f"rclone returned {proc.returncode}: {proc.stderr.decode(errors='ignore')[:300]}"

    async def upload(self, ctx: MLContext, local_path: Path) -> UploadResult:
        ctx.status("uploading")
        conf = await Accounts.get_secret(ctx.user_id, self.id, "conf")
        account = await Accounts.get_account(ctx.user_id, self.id)
        remote = account.get("remote")
        if not conf or not remote:
            return UploadResult(
                self.id, ok=False, message="Rclone not configured (no conf or remote)"
            )
        proc = await _run_rclone(
            conf,
            ["copy", str(local_path), remote, "--transfers=4", "--progress=false"],
            timeout=None,
        )
        if proc.returncode != 0:
            return UploadResult(
                self.id,
                ok=False,
                message=f"rclone failed: {proc.stderr.decode(errors='ignore')[:300]}",
            )
        return UploadResult(self.id, ok=True, url=f"rclone://{remote}/{local_path.name}")


class _Completed:
    def __init__(self, rc: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


async def _run_rclone(conf: str, args: list[str], *, timeout):
    """Run `rclone <args>` with a per-invocation conf file that's deleted
    afterwards, whether or not the command succeeds."""
    tmp = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)  # noqa: SIM115
    try:
        tmp.write(conf)
        tmp.flush()
        tmp.close()
        proc = await asyncio.create_subprocess_exec(
            "rclone",
            "--config",
            tmp.name,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return _Completed(124, b"", b"rclone timed out")
        return _Completed(proc.returncode or 0, stdout, stderr)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp.name)
