"""Per-user Mirror-Leech provider accounts.

Accounts live under `MediaStudio-users.<uid>.personal_settings.mirror_leech_accounts`
as a dict keyed by uploader id. Secrets are encrypted with Fernet via
`Secrets.encrypt`; non-secret fields (e.g. destination folder id) live
alongside in plaintext.

Every uploader round-trips credentials through this module so encryption
is consistent across providers and so the admin-panel "wipe credentials"
action has a single entry point.
"""

from __future__ import annotations

from typing import Any, Optional

from database import db
from tools.mirror_leech import Secrets


async def get_accounts(user_id: int) -> dict[str, dict[str, Any]]:
    """Return the raw mirror_leech_accounts dict for `user_id` (empty if none)."""
    if db.users is None:
        return {}
    doc = await db.users.find_one({"user_id": user_id})
    if not doc:
        return {}
    personal = doc.get("personal_settings") or {}
    return dict(personal.get("mirror_leech_accounts") or {})


async def get_account(user_id: int, provider_id: str) -> dict[str, Any]:
    accounts = await get_accounts(user_id)
    return dict(accounts.get(provider_id) or {})


async def get_secret(user_id: int, provider_id: str, field: str) -> Optional[str]:
    """Read and decrypt a single secret field."""
    account = await get_account(user_id, provider_id)
    ciphertext = account.get(f"{field}_enc")
    if not ciphertext:
        return None
    return Secrets.decrypt(ciphertext)


async def set_secret(user_id: int, provider_id: str, field: str, plaintext: str) -> None:
    """Encrypt and persist a single secret field under the provider key."""
    if not Secrets.is_available():
        raise RuntimeError(
            "SECRETS_KEY is not configured — refusing to store Mirror-Leech credentials"
        )
    enc = Secrets.encrypt(plaintext)
    await db.users.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {"user_id": user_id},
            "$set": {f"personal_settings.mirror_leech_accounts.{provider_id}.{field}_enc": enc},
        },
        upsert=True,
    )


async def set_plain(user_id: int, provider_id: str, field: str, value: Any) -> None:
    """Persist a non-secret config field (destination folder, etc.)."""
    await db.users.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {"user_id": user_id},
            "$set": {f"personal_settings.mirror_leech_accounts.{provider_id}.{field}": value},
        },
        upsert=True,
    )


async def clear_account(user_id: int, provider_id: str) -> None:
    """Drop every field belonging to a provider for a user."""
    await db.users.update_one(
        {"user_id": user_id},
        {"$unset": {f"personal_settings.mirror_leech_accounts.{provider_id}": ""}},
    )


async def list_configured_uploaders(user_id: int) -> list[str]:
    """Return the provider ids for which this user has *any* stored field.
    Callers typically further filter by `Uploader.is_configured()`."""
    return sorted((await get_accounts(user_id)).keys())
