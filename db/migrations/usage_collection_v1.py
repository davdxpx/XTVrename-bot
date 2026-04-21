# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""usage_collection_v1 migration.

Moves usage counters out of ``MediaStudio-users.<uid>.usage`` into three
dedicated collections designed for history, leaderboards, and global
roll-ups (see ``db/usage.py`` for the data model):

  * MediaStudio-usage              — one doc per (uid, date)
  * MediaStudio-usage-alltime      — one doc per uid (lifetime)
  * MediaStudio-usage-daily-global — one doc per date (global)

What the migration does on a fresh run:

 1. Create TTL + query indexes on all three collections.
 2. Backfill today's per-day doc + the user's alltime doc from each
    existing ``MediaStudio-users.<uid>.usage`` subdoc. The migration
    is conservative — it preserves the user's lifetime totals as-is
    and seeds a single per-day doc for whatever ``usage.date`` the
    legacy counters carried. It doesn't fabricate per-type /
    per-tool breakdowns — those accumulate naturally from the next
    upload onwards.
 3. Aggregate per-day global rollups from the freshly-populated
    ``MediaStudio-usage`` collection so the global stats panel has
    something to show before any new uploads land.
 4. Unset the legacy ``usage`` subdoc on each user so old code that
    does ``user_doc.get("usage", {})`` falls back to the new tracker
    (callers have been migrated in the same PR).

Idempotent, advisory-locked, takes a backup of ``MediaStudio-users``
before the ``$unset`` step so the lifetime totals can be restored if
something goes wrong.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from pymongo import ASCENDING, DESCENDING

from db import schema
from db.migrations.helpers import backup_collection, collection_exists
from utils.telegram.log import get_logger

logger = get_logger("migrations.usage_collection_v1")

MIGRATION_ID = "usage_collection_v1"
_LOCK_TTL_SECONDS = 30 * 60


async def _read_migration_doc(settings_coll):
    return await settings_coll.find_one({"_id": schema.DOC_SCHEMA_MIGRATIONS}) or {}


async def _is_already_completed(settings_coll) -> bool:
    doc = await _read_migration_doc(settings_coll)
    entry = doc.get(MIGRATION_ID) or {}
    return bool(entry.get("completed_at"))


async def _acquire_lock(settings_coll, *, now: float) -> bool:
    doc = await _read_migration_doc(settings_coll)
    entry = doc.get(MIGRATION_ID) or {}
    started_at = entry.get("started_at")
    completed_at = entry.get("completed_at")

    if completed_at:
        return False
    if started_at and now - float(started_at) < _LOCK_TTL_SECONDS:
        logger.warning(
            "usage_collection_v1 held by another instance since %s; skipping",
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


async def _ensure_indexes(db: Any) -> None:
    """Create the indexes the UsageTracker relies on."""
    usage = db.db[schema.USAGE_COLLECTION]
    alltime = db.db[schema.USAGE_ALLTIME_COLLECTION]
    daily_global = db.db[schema.USAGE_DAILY_GLOBAL_COLLECTION]

    # Per-user per-day
    await usage.create_index([("uid", ASCENDING), ("date", DESCENDING)])
    await usage.create_index([("date", ASCENDING), ("egress_mb", DESCENDING)])
    await usage.create_index([("date", ASCENDING), ("file_count", DESCENDING)])
    # TTL on the ``date_ts`` int field (set by the tracker). Mongo's TTL
    # requires a date/number field; we use the upload timestamp set as
    # ``updated_at`` (epoch seconds). That's good enough for "drop old
    # per-day rows" — if a day has no writes for TTL_DAYS it gets culled.
    await usage.create_index(
        [("updated_at", ASCENDING)],
        expireAfterSeconds=int(schema.USAGE_TTL_DAYS * 86400),
        name="ttl_usage_by_updated_at",
    )

    # Alltime — no TTL
    await alltime.create_index([("last_seen_at", DESCENDING)])
    await alltime.create_index([("egress_mb_alltime", DESCENDING)])

    # Daily global — one doc per date, TTL on updated_at
    await daily_global.create_index(
        [("updated_at", ASCENDING)],
        expireAfterSeconds=int(schema.USAGE_DAILY_GLOBAL_TTL_DAYS * 86400),
        name="ttl_usage_daily_global_by_updated_at",
    )

    logger.info("usage_collection_v1: indexes ensured.")


async def _backfill_from_users(db: Any) -> dict:
    """Walk every users doc that still carries a ``usage`` subdoc and
    create the equivalent per-day + alltime entries in the new
    collections. Doesn't touch users with no usage record."""
    users_coll = db.db[schema.USERS_COLLECTION]
    usage_coll = db.db[schema.USAGE_COLLECTION]
    alltime_coll = db.db[schema.USAGE_ALLTIME_COLLECTION]

    now = time.time()
    users_seen = 0
    day_docs_created = 0
    alltime_docs_created = 0

    cursor = users_coll.find({"usage": {"$exists": True}})
    async for user_doc in cursor:
        uid = user_doc.get("user_id")
        usage = user_doc.get("usage") or {}
        if not isinstance(usage, dict) or not uid:
            continue
        users_seen += 1

        # Seed the per-day doc for the legacy ``usage.date`` if any.
        legacy_date = usage.get("date")
        if legacy_date:
            day_doc = {
                "_id": {"uid": uid, "date": legacy_date},
                "date": legacy_date,
                "uid": uid,
                "egress_mb": float(usage.get("egress_mb") or 0.0),
                "file_count": int(usage.get("file_count") or 0),
                "quota_hits": int(usage.get("quota_hits") or 0),
                "reserved_egress_mb": float(usage.get("reserved_egress_mb") or 0.0),
                "first_activity_at": now,
                "last_activity_at": now,
                "updated_at": now,
                "migrated_from_user_doc": True,
            }
            try:
                # Use replace-with-upsert so re-runs don't accumulate.
                await usage_coll.replace_one(
                    {"_id": day_doc["_id"]}, day_doc, upsert=True
                )
                day_docs_created += 1
            except Exception as e:
                logger.warning("day-doc backfill failed uid=%s: %s", uid, e)

        # Seed the alltime doc from lifetime counters.
        alltime_doc = {
            "_id": uid,
            "uid": uid,
            "egress_mb_alltime": float(usage.get("egress_mb_alltime") or 0.0),
            "file_count_alltime": int(usage.get("file_count_alltime") or 0),
            "quota_hits_alltime": 0,
            "batch_runs_alltime": 0,
            "first_seen_at": now,
            "last_seen_at": now,
            "migrated_from_user_doc": True,
        }
        try:
            await alltime_coll.replace_one(
                {"_id": uid}, alltime_doc, upsert=True
            )
            alltime_docs_created += 1
        except Exception as e:
            logger.warning("alltime-doc backfill failed uid=%s: %s", uid, e)

    return {
        "users_seen": users_seen,
        "day_docs_created": day_docs_created,
        "alltime_docs_created": alltime_docs_created,
    }


async def _rollup_global_from_users(db: Any) -> dict:
    """Aggregate ``MediaStudio-usage`` into per-day global rollups. Runs
    once after the backfill so the daily-global collection has data
    even before the first new upload.
    """
    usage_coll = db.db[schema.USAGE_COLLECTION]
    global_coll = db.db[schema.USAGE_DAILY_GLOBAL_COLLECTION]

    now = time.time()
    days_rolled = 0

    pipeline = [
        {
            "$group": {
                "_id": "$date",
                "total_egress_mb": {"$sum": "$egress_mb"},
                "total_file_count": {"$sum": "$file_count"},
                "unique_user_ids": {"$addToSet": "$uid"},
            }
        }
    ]
    try:
        async for doc in usage_coll.aggregate(pipeline):
            date = doc["_id"]
            if not date:
                continue
            try:
                await global_coll.update_one(
                    {"_id": date},
                    {
                        "$set": {
                            "date": date,
                            "total_egress_mb": doc.get("total_egress_mb", 0),
                            "total_file_count": doc.get("total_file_count", 0),
                            "unique_user_ids": doc.get("unique_user_ids", []),
                            "updated_at": now,
                            "backfilled_at": now,
                        }
                    },
                    upsert=True,
                )
                days_rolled += 1
            except Exception as e:
                logger.warning(
                    "daily-global rollup failed date=%s: %s", date, e
                )
    except Exception as e:
        logger.warning("daily-global aggregation failed: %s", e)

    return {"days_rolled": days_rolled}


async def _unset_legacy_usage(db: Any) -> dict:
    """Remove the ``usage`` subdoc from every user doc. Old reads that
    used ``user_doc.get("usage", {})`` now return an empty dict; the
    callers have been migrated to use ``db.usage_tracker.get_user_*``
    in the same PR.
    """
    users_coll = db.db[schema.USERS_COLLECTION]
    try:
        r = await users_coll.update_many(
            {"usage": {"$exists": True}},
            {"$unset": {"usage": ""}},
        )
        return {"users_updated": getattr(r, "modified_count", 0)}
    except Exception as e:
        logger.warning("unset legacy usage failed: %s", e)
        return {"users_updated": 0, "error": str(e)}


async def run_usage_collection_v1(db: Any) -> dict:
    """Entry point. Idempotent.

    ``db`` is the Database singleton.
    """
    if db.settings is None or db.users is None:
        logger.warning("DB collections unavailable; skipping usage migration.")
        return {"status": "skipped", "reason": "db-unavailable"}

    settings_coll = db.settings.real

    if await _is_already_completed(settings_coll):
        logger.info("usage_collection_v1 migration already completed; skipping.")
        # Still ensure indexes — they're cheap and idempotent, and a prior
        # incomplete run may have left them missing.
        with contextlib.suppress(Exception):
            await _ensure_indexes(db)
        return {"status": "already_done"}

    now = time.time()
    if not await _acquire_lock(settings_coll, now=now):
        return {"status": "locked"}

    try:
        logger.info("usage_collection_v1 migration starting")

        # Backup MediaStudio-users before the $unset step so lifetime
        # counters can be recovered if something goes wrong downstream.
        backup = None
        if await collection_exists(db.db, schema.USERS_COLLECTION):
            backup = await backup_collection(
                db.db,
                schema.USERS_COLLECTION,
                backup_suffix=f"_backup_usage_v1_{int(now)}",
            )
            logger.info("usage_collection_v1: users backup -> %s", backup)

        await _ensure_indexes(db)
        backfill_stats = await _backfill_from_users(db)
        rollup_stats = await _rollup_global_from_users(db)
        unset_stats = await _unset_legacy_usage(db)

        stats = {
            "backup": backup,
            "backfill": backfill_stats,
            "global_rollup": rollup_stats,
            "unset_legacy": unset_stats,
        }
        await _mark_completed(settings_coll, stats=stats)
        logger.info("usage_collection_v1 migration completed: %s", stats)
        return {"status": "completed", **stats}
    except Exception:
        logger.exception(
            "usage_collection_v1 migration FAILED — leaving lock in place"
        )
        raise
