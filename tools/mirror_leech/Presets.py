"""Destination presets for Mirror-Leech.

A preset is a named group of uploader ids — users can tap one label
and fan-out a file to every provider in the group, instead of ticking
checkboxes in the picker every time.

Stored under `personal_settings.mirror_leech_presets` in the users
collection:

    {
      "media":   {"label": "Media Hosts",  "providers": ["gdrive","dropbox"]},
      "archive": {"label": "Archive",      "providers": ["s3","backblaze_b2"]},
    }

No secrets here; all preset data is plaintext (the providers referenced
carry their own encrypted creds). Limits: 5 presets per user, 8
providers per preset — the picker fan-out is otherwise slow and the
progress UI gets unreadable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from db import db

MAX_PRESETS_PER_USER = 5
MAX_PROVIDERS_PER_PRESET = 8


@dataclass(frozen=True)
class Preset:
    slug: str
    label: str
    providers: tuple[str, ...]


def _as_preset(slug: str, raw: dict[str, Any]) -> Preset:
    label = str(raw.get("label") or slug).strip() or slug
    providers = tuple(
        str(p) for p in (raw.get("providers") or []) if isinstance(p, str)
    )
    return Preset(slug=slug, label=label, providers=providers)


async def get_presets(user_id: int) -> dict[str, Preset]:
    """Return the full preset mapping for `user_id` (empty dict if none)."""
    if db.users is None:
        return {}
    doc = await db.users.find_one({"user_id": user_id})
    if not doc:
        return {}
    personal = doc.get("personal_settings") or {}
    raw = personal.get("mirror_leech_presets") or {}
    return {
        slug: _as_preset(slug, val)
        for slug, val in raw.items()
        if isinstance(val, dict)
    }


async def get_preset(user_id: int, slug: str) -> Preset | None:
    presets = await get_presets(user_id)
    return presets.get(slug)


async def set_preset(
    user_id: int,
    slug: str,
    label: str,
    providers: list[str] | tuple[str, ...],
) -> Preset:
    """Create or replace a preset. Raises ValueError if limits are violated."""
    slug = (slug or "").strip().lower()
    if not slug or not slug.replace("_", "").replace("-", "").isalnum():
        raise ValueError("slug must be alphanumeric (underscore/dash allowed)")
    label = (label or "").strip() or slug
    seen: list[str] = []
    for p in providers:
        if not isinstance(p, str) or not p:
            continue
        if p in seen:
            continue
        seen.append(p)
    if not seen:
        raise ValueError("a preset must reference at least one provider")
    if len(seen) > MAX_PROVIDERS_PER_PRESET:
        raise ValueError(
            f"preset has {len(seen)} providers; max is {MAX_PROVIDERS_PER_PRESET}"
        )

    existing = await get_presets(user_id)
    if slug not in existing and len(existing) >= MAX_PRESETS_PER_USER:
        raise ValueError(
            f"preset limit reached ({MAX_PRESETS_PER_USER}); delete one first"
        )

    await db.users.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {"user_id": user_id},
            "$set": {
                f"personal_settings.mirror_leech_presets.{slug}": {
                    "label": label,
                    "providers": list(seen),
                }
            },
        },
        upsert=True,
    )
    return Preset(slug=slug, label=label, providers=tuple(seen))


async def delete_preset(user_id: int, slug: str) -> None:
    if db.users is None:
        return
    await db.users.update_one(
        {"user_id": user_id},
        {"$unset": {f"personal_settings.mirror_leech_presets.{slug}": ""}},
    )
