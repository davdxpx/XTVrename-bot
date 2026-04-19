"""Shared collection-level helpers used by migration modules.

Design goals:
  - Idempotent: every helper checks destination state before acting.
  - Works on free-tier MongoDB Atlas (no admin privileges).
  - Has a cursor-paginated fallback when $out aggregation is denied.
"""

from __future__ import annotations

from typing import Any

from utils.log import get_logger

logger = get_logger("db.migrations.helpers")

_COPY_BATCH_SIZE = 500


async def collection_exists(db, name: str) -> bool:
    """Return True iff a collection with `name` exists in `db`."""
    names = await db.list_collection_names()
    return name in names


async def _count(coll) -> int:
    return await coll.count_documents({})


async def _copy_via_out(src_coll, dst_name: str) -> bool:
    """Copy all docs from `src_coll` to the named destination using an $out
    aggregation stage. Returns True on success, False if $out was rejected
    (so the caller can fall back to a cursor-paginated copy)."""
    try:
        cursor = src_coll.aggregate([{"$out": dst_name}])
        async for _ in cursor:
            pass
        return True
    except Exception as exc:  # pragma: no cover - depends on cluster permissions
        logger.info(
            "aggregation $out not available for %s -> %s (%s); falling back",
            src_coll.name,
            dst_name,
            exc,
        )
        return False


async def _copy_via_cursor(src_coll, dst_coll) -> int:
    """Cursor-paginated fallback copy. Returns the number of docs copied."""
    batch: list[dict[str, Any]] = []
    copied = 0
    async for doc in src_coll.find({}):
        batch.append(doc)
        if len(batch) >= _COPY_BATCH_SIZE:
            await dst_coll.insert_many(batch, ordered=False)
            copied += len(batch)
            batch = []
    if batch:
        await dst_coll.insert_many(batch, ordered=False)
        copied += len(batch)
    return copied


async def backup_collection(db, source_name: str, *, backup_suffix: str) -> dict:
    """Clone `source_name` into `source_name + backup_suffix` if it doesn't
    already exist, preserving every document exactly. No-op when the backup
    is already present and its count matches. Returns a small status dict."""
    if not await collection_exists(db, source_name):
        return {"source": source_name, "status": "source_missing"}

    backup_name = f"{source_name}{backup_suffix}"
    src_coll = db[source_name]
    src_count = await _count(src_coll)

    if await collection_exists(db, backup_name):
        bak_count = await _count(db[backup_name])
        if bak_count == src_count:
            return {
                "source": source_name,
                "backup": backup_name,
                "status": "already_backed_up",
                "count": src_count,
            }
        # Existing backup is stale — drop & recreate rather than merging,
        # the backup is meant to be a point-in-time copy of the source right
        # before migration, not a running mirror.
        logger.warning(
            "Stale backup %s (%d docs) doesn't match source %s (%d docs); recreating",
            backup_name,
            bak_count,
            source_name,
            src_count,
        )
        await db[backup_name].drop()

    # Prefer $out; it's atomic per collection. Fall back to cursor copy.
    if not await _copy_via_out(src_coll, backup_name):
        await _copy_via_cursor(src_coll, db[backup_name])

    final_count = await _count(db[backup_name])
    if final_count != src_count:
        raise RuntimeError(
            f"backup_collection({source_name}) mismatch: src={src_count} dst={final_count}"
        )
    return {
        "source": source_name,
        "backup": backup_name,
        "status": "backed_up",
        "count": final_count,
    }


async def copy_collection(db, src_name: str, dst_name: str) -> dict:
    """Copy every document from `src_name` into `dst_name`. Idempotent:
    if `dst_name` already exists with the same doc count, no-op."""
    if not await collection_exists(db, src_name):
        return {"source": src_name, "status": "source_missing"}

    src_coll = db[src_name]
    src_count = await _count(src_coll)

    if await collection_exists(db, dst_name):
        dst_count = await _count(db[dst_name])
        if dst_count == src_count:
            return {
                "source": src_name,
                "destination": dst_name,
                "status": "already_copied",
                "count": src_count,
            }
        # Destination drifted — drop and redo. Migration is the only writer
        # to the new collections at this point; callers must not invoke
        # copy_collection after the app has started writing to dst.
        logger.warning(
            "Drop-and-recopy: %s has %d docs, %s has %d",
            src_name,
            src_count,
            dst_name,
            dst_count,
        )
        await db[dst_name].drop()

    if not await _copy_via_out(src_coll, dst_name):
        await _copy_via_cursor(src_coll, db[dst_name])

    final_count = await _count(db[dst_name])
    if final_count != src_count:
        raise RuntimeError(
            f"copy_collection({src_name} -> {dst_name}) mismatch: "
            f"src={src_count} dst={final_count}"
        )
    return {
        "source": src_name,
        "destination": dst_name,
        "status": "copied",
        "count": final_count,
    }
