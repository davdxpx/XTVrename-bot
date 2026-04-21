# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""UsageTracker — the single entry point for every usage / quota write.

This module owns the three new usage collections introduced in PR E:

  * ``MediaStudio-usage``              — one doc per (uid, date)
  * ``MediaStudio-usage-alltime``      — one doc per uid (lifetime)
  * ``MediaStudio-usage-daily-global`` — one doc per date (global roll-up)

Every write goes through ``record_upload`` (or one of the small siblings
``record_quota_hit`` / ``record_batch_run`` / ``record_task_duration``)
so the three collections stay consistent — a single upload event
increments the user's day doc, the user's alltime doc, and the day's
global doc atomically via ``$inc``. The reads on the other side are
read-only accessors that callers compose into dashboards and quota
checks.

Design notes
------------
- ``$inc`` updates are atomic per-document in MongoDB so there's no
  read-modify-write race between concurrent uploads.
- `by_type` and `by_tool` nested counters use dotted-key ``$inc`` so
  new media types / tools auto-materialise as sub-fields the first
  time they're seen — no schema migration needed.
- Leaderboards query ``MediaStudio-usage`` directly with the
  ``{date: 1, egress_mb: -1}`` index; the "last 7 days" query range-
  scans using ``{uid: 1, date: -1}``.
- The ``record_upload`` parameters accept optional breakdown keys so
  callers that don't know their media_type / tool_name just get the
  top-level counters bumped without polluting the breakdown dicts.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import schema
from utils.telegram.log import get_logger

logger = get_logger("db.usage")


def _utc_date_str(ts: Optional[float] = None) -> str:
    """Return the ``YYYY-MM-DD`` UTC date for ``ts`` or now."""
    dt = (
        datetime.datetime.utcnow()
        if ts is None
        else datetime.datetime.utcfromtimestamp(ts)
    )
    return dt.strftime("%Y-%m-%d")


def _utc_now() -> float:
    return datetime.datetime.utcnow().timestamp()


class UsageTracker:
    """Thin facade over the three usage collections.

    ``db`` is the Database instance (``db.core.Database``) — we read the
    three usage collections off it and use its ``settings`` Motor
    collection to mutate the ``global_daily_egress_mb`` legacy key when
    the caller asks for a global-cap refresh.
    """

    # Bundle of fields that appear in `by_type` / `by_tool` sub-dicts.
    _BREAKDOWN_DEFAULT = {"count": 0, "egress_mb": 0.0}

    def __init__(self, db_instance):
        self._db = db_instance

    # ------------------------------------------------------------------ writes

    async def record_upload(
        self,
        uid: int,
        egress_mb: float,
        *,
        media_type: Optional[str] = None,
        tool_name: Optional[str] = None,
        pro_mode: bool = False,
        ts: Optional[float] = None,
    ) -> None:
        """Record one completed upload.

        Atomically increments:
          * user's day doc (``MediaStudio-usage``)
          * user's alltime doc (``MediaStudio-usage-alltime``)
          * global day doc (``MediaStudio-usage-daily-global``)

        Safe to call for zero-MB uploads — only the counters that make
        sense are incremented.
        """
        if self._db.usage is None:
            return
        date = _utc_date_str(ts)
        now = ts if ts is not None else _utc_now()
        mb = max(0.0, float(egress_mb or 0.0))

        # --- Per-user per-day ----------------------------------------------
        inc: Dict[str, float] = {
            "egress_mb": mb,
            "file_count": 1,
        }
        if media_type:
            inc[f"by_type.{media_type}.egress_mb"] = mb
            inc[f"by_type.{media_type}.count"] = 1
        if tool_name:
            inc[f"by_tool.{tool_name}.egress_mb"] = mb
            inc[f"by_tool.{tool_name}.count"] = 1
        if pro_mode:
            inc["pro_mode.egress_mb"] = mb
            inc["pro_mode.count"] = 1

        try:
            await self._db.usage.update_one(
                {"_id": {"uid": uid, "date": date}},
                {
                    "$set": {"date": date, "uid": uid, "updated_at": now},
                    "$setOnInsert": {"first_activity_at": now},
                    "$max": {"last_activity_at": now},
                    "$inc": inc,
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("usage.record_upload (day) failed for uid=%s: %s", uid, e)

        # --- Per-user alltime ----------------------------------------------
        inc_alltime: Dict[str, float] = {
            "egress_mb_alltime": mb,
            "file_count_alltime": 1,
        }
        if media_type:
            inc_alltime[f"by_type_alltime.{media_type}.egress_mb"] = mb
            inc_alltime[f"by_type_alltime.{media_type}.count"] = 1
        if tool_name:
            inc_alltime[f"by_tool_alltime.{tool_name}.egress_mb"] = mb
            inc_alltime[f"by_tool_alltime.{tool_name}.count"] = 1
        if pro_mode:
            inc_alltime["pro_mode_alltime.egress_mb"] = mb
            inc_alltime["pro_mode_alltime.count"] = 1

        try:
            await self._db.usage_alltime.update_one(
                {"_id": uid},
                {
                    "$set": {"uid": uid, "last_seen_at": now},
                    "$setOnInsert": {"first_seen_at": now},
                    "$inc": inc_alltime,
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning(
                "usage.record_upload (alltime) failed for uid=%s: %s", uid, e
            )

        # --- Per-day global -------------------------------------------------
        global_inc: Dict[str, float] = {
            "total_egress_mb": mb,
            "total_file_count": 1,
        }
        if media_type:
            global_inc[f"by_type_totals.{media_type}.egress_mb"] = mb
            global_inc[f"by_type_totals.{media_type}.count"] = 1
        if tool_name:
            global_inc[f"by_tool_totals.{tool_name}.egress_mb"] = mb
            global_inc[f"by_tool_totals.{tool_name}.count"] = 1
        if pro_mode:
            global_inc["pro_mode_totals.egress_mb"] = mb
            global_inc["pro_mode_totals.count"] = 1

        try:
            await self._db.usage_daily_global.update_one(
                {"_id": date},
                {
                    "$set": {"date": date, "updated_at": now},
                    "$setOnInsert": {"first_activity_at": now},
                    "$inc": global_inc,
                    "$addToSet": {"unique_user_ids": uid},
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning(
                "usage.record_upload (global) failed date=%s: %s", date, e
            )

    async def record_quota_hit(self, uid: int, ts: Optional[float] = None) -> None:
        """Bump the user's quota-hit counter when a quota check denies an
        upload. Doesn't touch egress counters."""
        if self._db.usage is None:
            return
        date = _utc_date_str(ts)
        now = ts if ts is not None else _utc_now()
        try:
            await self._db.usage.update_one(
                {"_id": {"uid": uid, "date": date}},
                {
                    "$set": {"date": date, "uid": uid, "updated_at": now},
                    "$inc": {"quota_hits": 1},
                },
                upsert=True,
            )
            await self._db.usage_alltime.update_one(
                {"_id": uid},
                {"$inc": {"quota_hits_alltime": 1}},
                upsert=True,
            )
        except Exception as e:
            logger.warning("usage.record_quota_hit failed uid=%s: %s", uid, e)

    async def record_batch_run(self, uid: int, ts: Optional[float] = None) -> None:
        """Bump the user's batch-run counter when a batch completes."""
        if self._db.usage is None:
            return
        date = _utc_date_str(ts)
        now = ts if ts is not None else _utc_now()
        try:
            await self._db.usage.update_one(
                {"_id": {"uid": uid, "date": date}},
                {
                    "$set": {"date": date, "uid": uid, "updated_at": now},
                    "$inc": {"batch_runs": 1},
                },
                upsert=True,
            )
            await self._db.usage_alltime.update_one(
                {"_id": uid},
                {"$inc": {"batch_runs_alltime": 1}},
                upsert=True,
            )
        except Exception as e:
            logger.warning("usage.record_batch_run failed uid=%s: %s", uid, e)

    async def record_task_duration(
        self,
        uid: int,
        seconds: float,
        ts: Optional[float] = None,
    ) -> None:
        """Accumulate processing-time on the user's day doc."""
        if self._db.usage is None or seconds <= 0:
            return
        date = _utc_date_str(ts)
        now = ts if ts is not None else _utc_now()
        try:
            await self._db.usage.update_one(
                {"_id": {"uid": uid, "date": date}},
                {
                    "$set": {"date": date, "uid": uid, "updated_at": now},
                    "$inc": {"processing_time_seconds": float(seconds)},
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("usage.record_task_duration failed uid=%s: %s", uid, e)

    async def reserve_egress(
        self,
        uid: int,
        mb: float,
        ts: Optional[float] = None,
    ) -> None:
        """Add ``mb`` to the user's reserved-egress counter (before the
        upload actually starts, for quota gating)."""
        if self._db.usage is None:
            return
        date = _utc_date_str(ts)
        now = ts if ts is not None else _utc_now()
        try:
            await self._db.usage.update_one(
                {"_id": {"uid": uid, "date": date}},
                {
                    "$set": {"date": date, "uid": uid, "updated_at": now},
                    "$inc": {"reserved_egress_mb": float(mb)},
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("usage.reserve_egress failed uid=%s: %s", uid, e)

    async def release_egress(
        self,
        uid: int,
        mb: float,
        ts: Optional[float] = None,
    ) -> None:
        """Decrement the reserved counter — pair with ``reserve_egress``
        when an upload is cancelled before it completes."""
        if self._db.usage is None:
            return
        date = _utc_date_str(ts)
        now = ts if ts is not None else _utc_now()
        try:
            await self._db.usage.update_one(
                {"_id": {"uid": uid, "date": date}},
                {
                    "$set": {"date": date, "uid": uid, "updated_at": now},
                    "$inc": {"reserved_egress_mb": -float(mb)},
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("usage.release_egress failed uid=%s: %s", uid, e)

    # ------------------------------------------------------------------ reads

    async def get_user_today(self, uid: int) -> dict:
        """Return the user's counters for the current UTC date. Empty
        dict when no activity yet."""
        if self._db.usage is None:
            return {}
        date = _utc_date_str()
        doc = await self._db.usage.find_one({"_id": {"uid": uid, "date": date}})
        return doc or {}

    async def get_user_day(self, uid: int, date: str) -> dict:
        if self._db.usage is None:
            return {}
        doc = await self._db.usage.find_one({"_id": {"uid": uid, "date": date}})
        return doc or {}

    async def get_user_history(self, uid: int, days: int = 7) -> List[dict]:
        """Return the user's per-day docs for the last ``days`` UTC
        days, reverse-chronological (today first). Missing days are
        represented as ``{"date": str, "egress_mb": 0, "file_count": 0}``
        placeholders so chart renderers can assume a full window.
        """
        if self._db.usage is None:
            return []
        today = datetime.datetime.utcnow().date()
        window_start = today - datetime.timedelta(days=days - 1)
        query = {
            "uid": uid,
            "date": {"$gte": window_start.strftime("%Y-%m-%d")},
        }
        found = {}
        async for doc in self._db.usage.find(query):
            found[doc["date"]] = doc
        out: List[dict] = []
        for i in range(days):
            d = today - datetime.timedelta(days=i)
            ds = d.strftime("%Y-%m-%d")
            if ds in found:
                out.append(found[ds])
            else:
                out.append(
                    {
                        "date": ds,
                        "uid": uid,
                        "egress_mb": 0,
                        "file_count": 0,
                        "quota_hits": 0,
                    }
                )
        return out

    async def get_user_alltime(self, uid: int) -> dict:
        if self._db.usage_alltime is None:
            return {}
        doc = await self._db.usage_alltime.find_one({"_id": uid})
        return doc or {}

    # ------------------------------------------------------------------ leaderboards

    async def get_leaderboard_today(
        self, limit: int = 10, *, skip: int = 0
    ) -> Tuple[List[dict], int]:
        """Top users by egress today. Returns (rows, total)."""
        return await self.get_leaderboard_day(
            _utc_date_str(), limit=limit, skip=skip
        )

    async def get_leaderboard_day(
        self, date: str, *, limit: int = 10, skip: int = 0
    ) -> Tuple[List[dict], int]:
        if self._db.usage is None:
            return [], 0
        query = {"date": date, "egress_mb": {"$gt": 0}}
        try:
            cursor = (
                self._db.usage.find(query)
                .sort("egress_mb", -1)
                .skip(skip)
                .limit(limit)
            )
            rows = await cursor.to_list(length=limit)
            total = await self._db.usage.count_documents(query)
            return rows, total
        except Exception as e:
            logger.warning("usage.get_leaderboard_day failed: %s", e)
            return [], 0

    async def get_leaderboard_period(
        self,
        start_date: str,
        end_date: str,
        *,
        limit: int = 10,
        skip: int = 0,
    ) -> List[dict]:
        """Sum each user's egress over [start_date, end_date] and rank.
        Uses an aggregation pipeline; range is inclusive.
        """
        if self._db.usage is None:
            return []
        pipeline = [
            {"$match": {"date": {"$gte": start_date, "$lte": end_date}}},
            {
                "$group": {
                    "_id": "$uid",
                    "egress_mb": {"$sum": "$egress_mb"},
                    "file_count": {"$sum": "$file_count"},
                    "active_days": {"$sum": 1},
                }
            },
            {"$match": {"egress_mb": {"$gt": 0}}},
            {"$sort": {"egress_mb": -1}},
            {"$skip": skip},
            {"$limit": limit},
        ]
        try:
            return [doc async for doc in self._db.usage.aggregate(pipeline)]
        except Exception as e:
            logger.warning("usage.get_leaderboard_period failed: %s", e)
            return []

    async def get_leaderboard_alltime(
        self, *, limit: int = 10, skip: int = 0
    ) -> List[dict]:
        if self._db.usage_alltime is None:
            return []
        try:
            cursor = (
                self._db.usage_alltime.find(
                    {"egress_mb_alltime": {"$gt": 0}}
                )
                .sort("egress_mb_alltime", -1)
                .skip(skip)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.warning("usage.get_leaderboard_alltime failed: %s", e)
            return []

    # ------------------------------------------------------------------ global

    async def get_global_today(self) -> dict:
        if self._db.usage_daily_global is None:
            return {}
        doc = await self._db.usage_daily_global.find_one({"_id": _utc_date_str()})
        return doc or {}

    async def get_global_day(self, date: str) -> dict:
        if self._db.usage_daily_global is None:
            return {}
        doc = await self._db.usage_daily_global.find_one({"_id": date})
        return doc or {}

    async def get_global_history(self, days: int = 30) -> List[dict]:
        """Last ``days`` global daily rollups, reverse-chronological."""
        if self._db.usage_daily_global is None:
            return []
        today = datetime.datetime.utcnow().date()
        window_start = today - datetime.timedelta(days=days - 1)
        cursor = (
            self._db.usage_daily_global.find(
                {"date": {"$gte": window_start.strftime("%Y-%m-%d")}}
            )
            .sort("date", -1)
            .limit(days)
        )
        return await cursor.to_list(length=days)

    # ------------------------------------------------------------------ streaks + peak day

    async def refresh_user_streak(self, uid: int) -> dict:
        """Compute current streak + total active days + peak day and
        persist them onto the alltime doc. Called lazily when rendering
        the user's stats panel so background recomputation isn't needed.
        """
        if self._db.usage is None or self._db.usage_alltime is None:
            return {}
        # Pull the last 400 days (well above the 180-day TTL so we get
        # everything the collection retains).
        today = datetime.datetime.utcnow().date()
        window_start = today - datetime.timedelta(days=400)
        active_dates: set = set()
        peak = {"date": "", "egress_mb": 0.0}
        cursor = self._db.usage.find(
            {"uid": uid, "date": {"$gte": window_start.strftime("%Y-%m-%d")}},
            {"date": 1, "egress_mb": 1},
        )
        async for doc in cursor:
            if doc.get("egress_mb", 0) > 0 or doc.get("file_count", 0) > 0:
                active_dates.add(doc["date"])
            if doc.get("egress_mb", 0) > peak["egress_mb"]:
                peak = {
                    "date": doc["date"],
                    "egress_mb": doc["egress_mb"],
                }

        # Current streak: count backwards from today while days are in set.
        streak = 0
        d = today
        while d.strftime("%Y-%m-%d") in active_dates:
            streak += 1
            d -= datetime.timedelta(days=1)
            if streak > 400:
                break

        update = {
            "current_streak_days": streak,
            "total_active_days": len(active_dates),
            "peak_day": peak,
        }
        try:
            await self._db.usage_alltime.update_one(
                {"_id": uid}, {"$set": update}, upsert=True
            )
        except Exception as e:
            logger.warning("usage.refresh_user_streak failed uid=%s: %s", uid, e)
        return update

    # ------------------------------------------------------------------ bulk maintenance

    async def purge_old_days(self, *, keep_days: int = schema.USAGE_TTL_DAYS) -> dict:
        """Ad-hoc cleanup for the admin panel. TTL indexes usually do
        this automatically, but this helper lets an admin free space now."""
        if self._db.usage is None:
            return {"deleted": 0}
        cutoff = datetime.datetime.utcnow().date() - datetime.timedelta(days=keep_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        try:
            r = await self._db.usage.delete_many({"date": {"$lt": cutoff_str}})
            return {"deleted": getattr(r, "deleted_count", 0), "cutoff": cutoff_str}
        except Exception as e:
            logger.warning("usage.purge_old_days failed: %s", e)
            return {"deleted": 0, "error": str(e)}

    async def purge_old_global_days(
        self, *, keep_days: int = schema.USAGE_DAILY_GLOBAL_TTL_DAYS
    ) -> dict:
        if self._db.usage_daily_global is None:
            return {"deleted": 0}
        cutoff = datetime.datetime.utcnow().date() - datetime.timedelta(days=keep_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        try:
            r = await self._db.usage_daily_global.delete_many(
                {"date": {"$lt": cutoff_str}}
            )
            return {"deleted": getattr(r, "deleted_count", 0), "cutoff": cutoff_str}
        except Exception as e:
            logger.warning("usage.purge_old_global_days failed: %s", e)
            return {"deleted": 0, "error": str(e)}


def init_usage_tracker(db_instance) -> UsageTracker:
    """Factory called from ``db/__init__.py`` once the Database instance
    is up. The resulting tracker is bound onto ``db.usage_tracker`` so
    ``from db import db; await db.usage_tracker.record_upload(...)``
    works across the codebase.
    """
    tracker = UsageTracker(db_instance)
    return tracker
