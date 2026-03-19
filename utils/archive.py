import os
import asyncio
import logging

logger = logging.getLogger("utils.archive")

async def is_archive(filename: str) -> bool:
    """Check if the given filename has an archive extension."""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"]

async def check_password_protected(archive_path: str) -> bool:
    """Use 7z to test if an archive requires a password."""
    try:
        # Run `7z t -p` to test the archive. The `-p` flag forces an error if a password is required,
        # otherwise 7z might wait indefinitely for input.
        # However, passing `-p` with an intentionally wrong password (e.g. `-pWRONGPASSWORD123`)
        # is a standard way to reliably trigger a "Wrong password" or "Data Error" output for encrypted files.
        process = await asyncio.create_subprocess_exec(
            "7z", "t", f"-pDUMMYPASSWORD123!@#", archive_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        output = (stdout.decode() + stderr.decode()).lower()

        # Look for typical 7z encrypted indicators
        if "wrong password" in output or "cannot open encrypted archive" in output or "data error in encrypted file" in output or "enter password" in output:
            return True

        return False
    except Exception as e:
        logger.error(f"Error checking archive password status: {e}")
        return False

async def extract_archive(archive_path: str, dest_dir: str, password: str = None) -> bool:
    """Extract an archive using 7z. Returns True on success, False on failure."""
    try:
        os.makedirs(dest_dir, exist_ok=True)

        args = ["7z", "x", archive_path, f"-o{dest_dir}", "-y"]
        if password:
            args.append(f"-p{password}")

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            return True
        else:
            logger.error(f"Extraction failed: {stderr.decode()}")
            return False

    except Exception as e:
        logger.error(f"Error extracting archive: {e}")
        return False
