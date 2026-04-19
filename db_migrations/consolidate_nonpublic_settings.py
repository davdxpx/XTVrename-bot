# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Consolidate non-public per-user settings docs into global_settings.

Background
----------
Before the MediaStudio layout migration, ``Database._get_doc_id()`` in
non-public mode effectively ignored ``user_id`` and always addressed the
global settings document. The layout migration accidentally dropped that
special-case: if a caller passed ``user_id`` in non-public mode, writes
suddenly went to a ``user_<id>`` doc and reads split depending on who
asked.

Observed symptom
----------------
A single-tenant private bot had its dumb-channel list saved under
``user_<CEO_ID>`` (because the rename flow calls ``get_dumb_channels``
with ``user_id``), while ``/admin → Dumb Channels`` reads
``global_settings`` and therefore showed an empty list.

Fix
---
``_get_doc_id`` now forces ``global_settings`` in non-public mode. This
migration rescues any pre-existing per-user docs by deep-merging their
content into ``global_settings`` and then removing the per-user doc, so
both flows converge on the same source of truth.

In addition, this migration backfills the CEO's ``personal_settings``
from stray PERSONAL_KEYS stored in ``legacy_misc`` — which is where
template / thumbnail / channel writes land when ``CEO_ID`` is unset at
runtime. Once ``CEO_ID`` is configured, the CEO's personal_settings is
the source of truth for these keys; without this backfill, admin reads
show defaults (empty CEO overlay wins over legacy_misc via merge order)
even though the values are still sitting in ``MediaStudio-Settings``.

Idempotent. Safe to call every boot. No-op when:
- ``PUBLIC_MODE=True`` (per-user docs are intentional there)
- no ``user_*`` docs exist AND no stray personal keys in legacy_misc
"""

from __future__ import annotations

import contextlib
from typing import Any

import database_schema as schema
from config import Config
from utils.log import get_logger

logger = get_logger("migrations.consolidate_nonpublic_settings")


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Merge ``overlay`` into ``base`` in place without overwriting keys
    that already exist in ``base``. Nested dicts are merged recursively.
    Non-dict values in ``base`` win over overlay — we preferentially keep
    whatever's already in the global doc."""
    for key, value in overlay.items():
        if key == "_id":
            continue
        if key not in base:
            base[key] = value
            continue
        if isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
    return base


async def _backfill_legacy_misc_personal_keys(db: Any) -> int:
    """Move PERSONAL_KEYS that sit in ``legacy_misc`` into the CEO's
    ``personal_settings``.

    This happens when a non-public deployment was booted without CEO_ID
    at some point: the shim's CEO-routing short-circuits and writes for
    ``filename_templates`` / ``templates`` / ``channel`` / ``thumbnail_*``
    end up in ``legacy_misc`` instead of ``MediaStudio-users.<ceo>.
    personal_settings``. Admin reads then silently show defaults because
    the virtual-global merge lets the (empty or stale) CEO overlay win
    over ``legacy_misc``.

    Policy:
      - legacy_misc is treated as the AUTHORITATIVE source for PERSONAL_KEYS
        (it's where the most recent admin write that *did* persist ended up).
      - Sub-keys from legacy_misc overwrite matching sub-keys in CEO
        personal_settings (so stale CEO data is corrected by the newest
        admin action).
      - After backfill the key is removed from legacy_misc so the overlay
        model is consistent going forward.

    Returns the number of top-level personal keys backfilled.
    """
    ceo_id = Config.CEO_ID or 0
    if not ceo_id:
        return 0
    if db.settings is None or db.users is None:
        return 0

    real = db.settings.real  # raw MediaStudio-Settings collection
    legacy = await real.find_one({"_id": schema.LEGACY_MISC_DOC_ID})
    if not legacy:
        return 0

    stray = {
        k: v for k, v in legacy.items()
        if k != "_id" and k in schema.PERSONAL_KEYS
    }
    if not stray:
        return 0

    logger.info(
        "Backfilling %d personal key(s) from legacy_misc into CEO %s: %s",
        len(stray),
        ceo_id,
        sorted(stray.keys()),
    )

    ceo_doc = await db.users.find_one({"user_id": ceo_id}) or {}
    personal = dict(ceo_doc.get("personal_settings") or {})

    for key, value in stray.items():
        existing = personal.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged_val = dict(existing)
            merged_val.update(value)  # legacy_misc sub-keys win
            personal[key] = merged_val
        else:
            personal[key] = value

    await db.users.update_one(
        {"user_id": ceo_id},
        {
            "$set": {f"personal_settings.{k}": v for k, v in personal.items()},
            "$setOnInsert": {"user_id": ceo_id},
        },
        upsert=True,
    )

    await real.update_one(
        {"_id": schema.LEGACY_MISC_DOC_ID},
        {"$unset": {k: "" for k in stray}},
    )

    return len(stray)


async def run_consolidate_nonpublic_settings(db: Any) -> int:
    """Merge ``user_*`` settings docs into ``global_settings`` in non-public mode,
    and backfill the CEO's personal_settings from stray legacy_misc keys.

    Returns the number of user docs that were consumed.
    """
    if Config.PUBLIC_MODE:
        logger.info("PUBLIC_MODE=True — skipping non-public consolidation.")
        return 0

    if db.settings is None:
        logger.warning("Settings collection unavailable; skipping consolidation.")
        return 0

    # Surface a configuration problem that otherwise silently breaks
    # PERSONAL_KEYS routing: admin edits would go to legacy_misc, reads
    # would fall back to defaults once a valid CEO_ID is configured later.
    if not Config.CEO_ID:
        logger.warning(
            "CEO_ID is not set (or is 0) in non-public mode — personal-key "
            "routing is disabled. Templates, thumbnails, channel and dumb "
            "channels will be written to MediaStudio-Settings.legacy_misc "
            "instead of MediaStudio-users.<ceo>.personal_settings, and admin "
            "edits may appear to persist but not take effect. Set CEO_ID in "
            "the environment."
        )

    # --- Phase 1: stray user_* docs in MediaStudio-Settings (rare; pre-shim) ---
    try:
        cursor = db.settings.find({"_id": {"$regex": r"^user_\d+$"}})
    except Exception as e:
        logger.warning(f"Could not enumerate user_* docs: {e}")
        cursor = None

    user_docs = []
    if cursor is not None:
        async for doc in cursor:
            user_docs.append(doc)

    merged_any = False
    if user_docs:
        global_doc = await db.settings.find_one({"_id": "global_settings"}) or {}
        for doc in user_docs:
            doc_id = doc.get("_id")
            logger.info(
                f"Consolidating {doc_id} → global_settings "
                f"(keys: {sorted(k for k in doc if k != '_id')})"
            )
            before_keys = set(global_doc.keys())
            _deep_merge(global_doc, doc)
            after_keys = set(global_doc.keys())
            added = after_keys - before_keys
            if added:
                merged_any = True
                logger.info(f"  added to global: {sorted(added)}")

        if merged_any:
            global_doc["_id"] = "global_settings"
            try:
                await db.settings.update_one(
                    {"_id": "global_settings"},
                    {"$set": {k: v for k, v in global_doc.items() if k != "_id"}},
                    upsert=True,
                )
                logger.info("global_settings updated with merged user data.")
            except Exception as e:
                logger.error(f"Failed to write merged global_settings: {e}")
                return 0

    removed = 0
    for doc in user_docs:
        doc_id = doc.get("_id")
        try:
            await db.settings.delete_one({"_id": doc_id})
            removed += 1
        except Exception as e:
            logger.warning(f"Could not remove {doc_id}: {e}")

    # --- Phase 2: stray PERSONAL_KEYS in legacy_misc (the template bug) ---
    backfilled = 0
    try:
        backfilled = await _backfill_legacy_misc_personal_keys(db)
    except Exception as e:
        logger.warning(f"legacy_misc → CEO personal backfill failed: {e}")

    with contextlib.suppress(Exception):
        db._invalidate_settings_cache()

    logger.info(
        "Non-public consolidation done: merged %d user doc(s), removed %d, "
        "backfilled %d personal key(s) from legacy_misc.",
        len(user_docs),
        removed,
        backfilled,
    )
    return removed


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
