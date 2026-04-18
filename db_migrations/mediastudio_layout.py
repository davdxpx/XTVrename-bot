"""mediastudio_layout migration.

Splits the legacy `user_settings` collection into per-concern docs under
`MediaStudio-Settings` and inlines per-user settings into `MediaStudio-users`.
Idempotent. Advisory-locked. Safe to re-run.
"""

from __future__ import annotations

import time

import database_schema as schema
from db_migrations.helpers import backup_collection, collection_exists, copy_collection
from db_migrations.split import split_user_settings_doc
from utils.log import get_logger

logger = get_logger("db_migrations.mediastudio_layout")

MIGRATION_ID = "mediastudio_layout"
_LOCK_TTL_SECONDS = 30 * 60  # 30 minutes
_LEGACY_SETTINGS_NAME = "user_settings"


async def _read_migration_doc(settings_coll):
    return await settings_coll.find_one({"_id": schema.DOC_SCHEMA_MIGRATIONS}) or {}


async def _is_already_completed(settings_coll) -> bool:
    doc = await _read_migration_doc(settings_coll)
    entry = doc.get(MIGRATION_ID) or {}
    return bool(entry.get("completed_at"))


async def _acquire_lock(settings_coll, *, now: float) -> bool:
    """Set `schema_migrations.<id>.started_at` if not already held within TTL.
    Returns True if we acquired it, False if another instance is mid-run."""
    doc = await _read_migration_doc(settings_coll)
    entry = doc.get(MIGRATION_ID) or {}
    started_at = entry.get("started_at")
    completed_at = entry.get("completed_at")

    if completed_at:
        return False  # Someone already finished — handled by _is_already_completed.

    if started_at and now - float(started_at) < _LOCK_TTL_SECONDS:
        logger.warning(
            "mediastudio_layout migration held by another instance since %s; skipping",
            started_at,
        )
        return False

    await settings_coll.update_one(
        {"_id": schema.DOC_SCHEMA_MIGRATIONS},
        {"$set": {f"{MIGRATION_ID}.started_at": now, f"{MIGRATION_ID}.host": "bot"}},
        upsert=True,
    )
    return True


async def _mark_completed(settings_coll, *, stats: dict) -> None:
    await settings_coll.update_one(
        {"_id": schema.DOC_SCHEMA_MIGRATIONS},
        {
            "$set": {
                f"{MIGRATION_ID}.completed_at": time.time(),
                f"{MIGRATION_ID}.stats": stats,
            }
        },
        upsert=True,
    )


async def _backup_all(db) -> list[dict]:
    results = []
    for legacy_name in [
        _LEGACY_SETTINGS_NAME,
        "users",
        "files",
        "folders",
        "daily_stats",
        "pending_payments",
        "file_groups",
        schema.SETTINGS_COLLECTION,  # defensive: if someone pre-created it
    ]:
        if not await collection_exists(db, legacy_name):
            continue
        results.append(
            await backup_collection(db, legacy_name, backup_suffix=schema.BACKUP_SUFFIX)
        )
    return results


async def _copy_same_shape(db) -> list[dict]:
    """Copy collections whose document shape is unchanged into their
    MediaStudio-* destinations."""
    pairs = [
        ("users", schema.USERS_COLLECTION),
        ("files", schema.FILES_COLLECTION),
        ("folders", schema.FOLDERS_COLLECTION),
        ("daily_stats", schema.DAILY_STATS_COLLECTION),
        ("pending_payments", schema.PENDING_PAYMENTS_COLLECTION),
        ("file_groups", schema.FILE_GROUPS_COLLECTION),
    ]
    return [await copy_collection(db, src, dst) for src, dst in pairs]


async def _apply_split(db, *, public_mode: bool, ceo_id: int) -> dict:
    """Walk user_settings and rewrite each doc into the new layout.

    Returns stats: {settings_docs_seen, users_touched, unknown_keys,
                    verbatim_legacy_count}.
    """
    stats = {
        "settings_docs_seen": 0,
        "users_touched": set(),
        "unknown_keys": [],
        "verbatim_legacy_count": 0,
    }

    if not await collection_exists(db, _LEGACY_SETTINGS_NAME):
        logger.info("No legacy user_settings collection; nothing to split.")
        stats["users_touched"] = 0
        return stats

    legacy = db[_LEGACY_SETTINGS_NAME]
    new_settings = db[schema.SETTINGS_COLLECTION]
    new_users = db[schema.USERS_COLLECTION]

    async for legacy_doc in legacy.find({}):
        stats["settings_docs_seen"] += 1
        plan = split_user_settings_doc(
            legacy_doc, public_mode=public_mode, ceo_id=ceo_id
        )

        for target_id, fields in plan.global_docs.items():
            if not fields:
                continue
            await new_settings.update_one(
                {"_id": target_id}, {"$set": fields}, upsert=True
            )

        for uid, payload in plan.user_updates.items():
            stats["users_touched"].add(uid)
            update: dict = {"$setOnInsert": {"user_id": uid}}
            if payload.get("personal_settings"):
                update["$set"] = {
                    f"personal_settings.{k}": v
                    for k, v in payload["personal_settings"].items()
                }
            if payload.get("usage"):
                update.setdefault("$set", {}).update(
                    {f"usage.{k}": v for k, v in payload["usage"].items()}
                )
            await new_users.update_one({"user_id": uid}, update, upsert=True)

        for legacy_id, body in plan.verbatim_legacy.items():
            stats["verbatim_legacy_count"] += 1
            await new_settings.update_one(
                {"_id": legacy_id}, {"$set": body}, upsert=True
            )

        stats["unknown_keys"].extend(plan.unknown_keys)

    stats["users_touched"] = len(stats["users_touched"])
    # Keep unknown_keys serialisable & bounded.
    stats["unknown_keys"] = [list(pair) for pair in stats["unknown_keys"][:200]]
    return stats


async def ensure_indexes_v2(db) -> None:
    """Create indexes on the MediaStudio-* collections.

    Mirrors the previous ensure_indexes() but targets the renamed collections.
    Index failures are warn-logged, not raised — the bot can run without them.
    """
    try:
        await db[schema.USERS_COLLECTION].create_index("user_id", unique=True)
        await db[schema.FILES_COLLECTION].create_index(
            [("status", 1), ("expires_at", 1)]
        )
        await db[schema.FILES_COLLECTION].create_index("user_id")
        await db[schema.FOLDERS_COLLECTION].create_index("user_id")
        await db[schema.DAILY_STATS_COLLECTION].create_index(
            [("user_id", 1), ("date", 1)]
        )
        await db[schema.DAILY_STATS_COLLECTION].create_index("date")
        await db[schema.PENDING_PAYMENTS_COLLECTION].create_index("user_id")
        await db[schema.PENDING_PAYMENTS_COLLECTION].create_index("status")
        logger.info("MediaStudio-* indexes ensured.")
    except Exception as exc:
        logger.warning("ensure_indexes_v2: could not create indexes: %s", exc)


async def run_mediastudio_layout_migration(
    db,
    *,
    public_mode: bool,
    ceo_id: int,
    dry_run: bool = False,
) -> dict:
    """Run the mediastudio_layout migration. Idempotent.

    Returns a stats dict. When `dry_run=True`, splits are computed in memory
    and logged but no writes (beyond the advisory lock) happen.
    """
    settings_coll = db[schema.SETTINGS_COLLECTION]

    if await _is_already_completed(settings_coll):
        logger.info("mediastudio_layout migration already completed; skipping.")
        return {"status": "already_done"}

    now = time.time()
    if not dry_run and not await _acquire_lock(settings_coll, now=now):
        return {"status": "locked"}

    try:
        if dry_run:
            logger.info("[dry-run] mediastudio_layout migration starting")
        else:
            logger.info("mediastudio_layout migration starting")

        backups = [] if dry_run else await _backup_all(db)
        copies = [] if dry_run else await _copy_same_shape(db)
        split_stats = await _apply_split(
            db, public_mode=public_mode, ceo_id=ceo_id
        ) if not dry_run else {"status": "dry_run_skipped_apply"}

        if not dry_run:
            await ensure_indexes_v2(db)

        stats = {
            "backups": backups,
            "copies": copies,
            "split": split_stats,
        }

        if not dry_run:
            await _mark_completed(settings_coll, stats=stats)
            logger.info("mediastudio_layout migration completed: %s", stats)
        else:
            logger.info("[dry-run] mediastudio_layout migration plan: %s", stats)

        return {"status": "completed" if not dry_run else "dry_run", **stats}
    except Exception:
        logger.exception("mediastudio_layout migration FAILED — leaving lock in place")
        raise
