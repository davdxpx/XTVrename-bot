# --- Imports ---
import os
import asyncio
import logging

logger = logging.getLogger("utils.archive")

# === Helper Functions ===
def is_archive(filename: str) -> bool:
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz")

async def check_password_protected(archive_path: str) -> bool:

    try:

        process = await asyncio.create_subprocess_exec(
            "7z", "t", f"-pDUMMYPASSWORD123!@#", archive_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
            output = (stdout.decode() + stderr.decode()).lower()

            if "wrong password" in output or "cannot open encrypted archive" in output or "data error in encrypted file" in output or "enter password" in output:
                return True

            return False
        except asyncio.TimeoutError:
            logger.warning("7z password check timed out, killing...")
            try:
                process.kill()
            except Exception:
                pass
            return False
        except asyncio.CancelledError:
            logger.warning("7z password check cancelled, killing...")
            try:
                process.kill()
            except Exception:
                pass
            raise
    except Exception as e:
        logger.error(f"Error checking archive password status: {e}")
        return False

async def extract_archive(archive_path: str, dest_dir: str, password: str = None) -> bool:

    try:
        os.makedirs(dest_dir, exist_ok=True)

        args = ["7z", "x", archive_path, f"-o{dest_dir}", "-y"]
        if password:
            pw = password.replace("\x00", "")[:256]
            args.append(f"-p{pw}")

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            # Archives can be large, allow 10 minutes timeout
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600.0)

            if process.returncode == 0:
                return True
            else:
                logger.error(f"Extraction failed: {stderr.decode()}")
                return False
        except asyncio.TimeoutError:
            logger.warning("7z extraction timed out, killing...")
            try:
                process.kill()
            except Exception:
                pass
            return False
        except asyncio.CancelledError:
            logger.warning("7z extraction cancelled, killing...")
            try:
                process.kill()
            except Exception:
                pass
            raise

    except Exception as e:
        logger.error(f"Error extracting archive: {e}")
        return False

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
