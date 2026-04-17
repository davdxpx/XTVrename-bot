"""Fernet-backed encryption for Mirror-Leech provider credentials.

Every OAuth refresh token, rclone config blob, MEGA password, ... is
stored on the user document as `*_enc` and runs through this module.
The encryption key lives in the `SECRETS_KEY` env var; callers that
need to know if encryption is ready call `is_available()` first.

When `SECRETS_KEY` is missing AND the feature toggle is on, the admin
panel shows a red banner and the config UI refuses to store tokens —
never silently falls back to plaintext.
"""

from __future__ import annotations

from typing import Optional

from config import Config
from utils.log import get_logger

logger = get_logger("mirror_leech.secrets")


def _fernet():
    """Return a ready Fernet instance, or None if the key isn't configured
    or the cryptography package isn't importable."""
    key = Config.SECRETS_KEY
    if not key or not key.strip():
        return None
    try:
        from cryptography.fernet import Fernet  # lazy: keeps import cost off hot paths
    except ImportError:
        logger.error("cryptography is not installed — Mirror-Leech credentials cannot be encrypted")
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        logger.error("Invalid SECRETS_KEY: %s", exc)
        return None


def is_available() -> bool:
    """True when encrypt/decrypt will succeed on the current process."""
    return _fernet() is not None


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string into a Fernet token.

    Raises RuntimeError if encryption isn't available — callers that want
    to avoid that should gate on `is_available()` first.
    """
    f = _fernet()
    if f is None:
        raise RuntimeError(
            "SECRETS_KEY is not configured — cannot encrypt Mirror-Leech credentials"
        )
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> Optional[str]:
    """Decrypt a Fernet token back to a UTF-8 string.

    Returns None when the key is unavailable or the token is corrupt —
    callers then surface a "re-link your provider" prompt instead of
    crashing.
    """
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to decrypt Mirror-Leech token: %s", exc)
        return None


def generate_key() -> str:
    """Generate a brand-new Fernet key as a printable string."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode("ascii")
