# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""MyFiles Enterprise — schema migration v1.

Idempotent. Creates the new collections
(MediaStudio-myfiles-{audit,activity,quotas,shares}) with appropriate
indexes, back-fills quota docs for existing users, and tags each file /
folder document with the enterprise-default fields (is_deleted=False,
tags=[], parent_folder_id=None, ...) so the rest of the codebase can
assume they exist.

Runs from main.py at boot, after the mediastudio_layout migration. Safe
to call many times — every step checks for existing state first.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING

import database_schema as _schema
from utils.log import get_logger

logger = get_logger("migrations.myfiles_enterprise_v1")

# Retention defaults (days). Admin can override via admin panel.
_DEFAULT_RETENTION = {
    "myfiles_trash_retention_days": 30,
    "myfiles_audit_retention_days": 180,
    "myfiles_activity_retention_days": 90,
    "myfiles_max_versions": 10,
}


async def _ensure_indexes(db: Any) -> None:
    """Create the indexes the new collections rely on."""
    audit = db.db[_schema.MYFILES_AUDIT_COLLECTION]
    activity = db.db[_schema.MYFILES_ACTIVITY_COLLECTION]
    quotas = db.db[_schema.MYFILES_QUOTAS_COLLECTION]
    shares = db.db[_schema.MYFILES_SHARES_COLLECTION]

    # Audit — long retention, admin-only view.
    await audit.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    await audit.create_index(
        [("created_at", ASCENDING)],
        expireAfterSeconds=int(
            _DEFAULT_RETENTION["myfiles_audit_retention_days"] * 86400
        ),
        name="ttl_audit",
    )

    # Activity — shorter retention, user-facing feed.
    await activity.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    await activity.create_index(
        [("created_at", ASCENDING)],
        expireAfterSeconds=int(
            _DEFAULT_RETENTION["myfiles_activity_retention_days"] * 86400
        ),
        name="ttl_activity",
    )

    # Quotas — one doc per user.
    await quotas.create_index("user_id", unique=True)

    # Shares — unique token + TTL on expires_at.
    await shares.create_index("token", unique=True, sparse=True)
    await shares.create_index("owner_id")
    await shares.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
        name="ttl_share_expiry",
        partialFilterExpression={"expires_at": {"$type": "date"}},
    )


async def _seed_retention_defaults(db: Any) -> None:
    if db.settings is None:
        return
    existing = await db.get_setting("myfiles_max_versions")
    if existing is not None:
        return
    for k, v in _DEFAULT_RETENTION.items():
        try:
            await db.update_setting(k, v)
        except Exception as exc:
            logger.debug("seed retention %s: %s", k, exc)
    # Default per-plan quotas (0 = unlimited, admin can tighten).
    try:
        await db.update_setting(
            "myfiles_default_quotas",
            {
                "free": {"storage_bytes": 2 * 1024**3, "file_count": 100},
                "standard": {"storage_bytes": 25 * 1024**3, "file_count": 2000},
                "deluxe": {"storage_bytes": 0, "file_count": 0},  # unlimited
            },
        )
    except Exception as exc:
        logger.debug("seed default quotas: %s", exc)


async def _tag_existing_files_and_folders(db: Any) -> None:
    """Make sure the new boolean / list fields exist on legacy docs.

    We use $setOnInsert-style updates per document: `update_many` with
    `$exists: false` filter for each field so we never overwrite a
    value the app already wrote. Idempotent by construction.
    """
    if db.files is None or db.folders is None:
        return

    file_defaults = {
        "is_deleted": False,
        "tags": [],
        "parent_folder_id": None,
        "pinned": False,
        "view_count": 0,
        "version_number": 1,
    }
    folder_defaults = {
        "is_deleted": False,
        "parent_folder_id": None,
    }

    for field, value in file_defaults.items():
        try:
            await db.files.update_many(
                {field: {"$exists": False}},
                {"$set": {field: value}},
            )
        except Exception as exc:
            logger.debug("backfill files.%s: %s", field, exc)

    for field, value in folder_defaults.items():
        try:
            await db.folders.update_many(
                {field: {"$exists": False}},
                {"$set": {field: value}},
            )
        except Exception as exc:
            logger.debug("backfill folders.%s: %s", field, exc)


async def _recompute_user_quotas(db: Any) -> None:
    """Populate `myfiles_quotas` with current usage per user. Idempotent:
    uses upsert + absolute `$set`, so re-running converges."""
    if db.files is None or db.myfiles_quotas is None:
        return

    pipeline = [
        {"$match": {"is_deleted": {"$ne": True}}},
        {
            "$group": {
                "_id": "$user_id",
                "used": {"$sum": {"$ifNull": ["$size_bytes", 0]}},
                "count": {"$sum": 1},
            }
        },
    ]
    try:
        cursor = db.files.aggregate(pipeline)
    except Exception as exc:
        logger.warning("quota aggregate failed: %s", exc)
        return

    now = datetime.datetime.utcnow()
    processed = 0
    async for row in cursor:
        uid = row.get("_id")
        if uid is None:
            continue
        try:
            await db.myfiles_quotas.update_one(
                {"user_id": uid},
                {
                    "$set": {
                        "storage_used_bytes": int(row.get("used", 0)),
                        "file_count": int(row.get("count", 0)),
                        "last_recalculated_at": now,
                    },
                    "$setOnInsert": {
                        "storage_quota_bytes": 0,
                        "file_count_quota": 0,
                    },
                },
                upsert=True,
            )
            processed += 1
        except Exception as exc:
            logger.debug("quota upsert for %s failed: %s", uid, exc)
    logger.info("MyFiles quotas recomputed for %d users", processed)


async def run_myfiles_enterprise_v1(db: Any, *, dry_run: bool = False) -> None:
    """Entry point invoked by main.py during startup."""
    if db is None or getattr(db, "db", None) is None:
        logger.info("skip myfiles_enterprise_v1: no DB connection")
        return
    if dry_run:
        logger.info("myfiles_enterprise_v1 dry-run: would create indexes / backfill")
        return

    try:
        await _ensure_indexes(db)
        await _seed_retention_defaults(db)
        await _tag_existing_files_and_folders(db)
        await _recompute_user_quotas(db)
        # Mark applied so we can inspect from admin panel later.
        import contextlib
        with contextlib.suppress(Exception):
            await db.update_setting("myfiles_enterprise_v1_applied_at",
                                    datetime.datetime.utcnow().isoformat())
        logger.info("myfiles_enterprise_v1 migration complete")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("myfiles_enterprise_v1 failed: %s", exc)
