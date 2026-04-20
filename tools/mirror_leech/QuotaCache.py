"""In-memory TTL cache for per-destination quota lookups.

Quota endpoints are expensive (one HTTPS round-trip per provider, and
some do a heavy `GET /me/drive` or WebDAV PROPFIND under the hood). The
settings screen would otherwise block on six of these for a few seconds
every time a user opens `/settings → Mirror-Leech`.

Cache key is `(user_id, provider_id)`. Entries expire after
`TTL_SECONDS` (10 min by default). A cache miss — or an expired entry —
triggers an out-of-line refresh via the uploader's `get_quota()` method.

Negative results are cached too: providers that return None (S3-like,
no-quota WebDAV) never get re-polled during the TTL, keeping the UI
snappy without sending per-open HEAD requests.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from tools.mirror_leech.uploaders import QuotaInfo, uploader_by_id
from utils.telegram.log import get_logger

logger = get_logger("mirror_leech.quota_cache")

TTL_SECONDS = 600  # 10 min — enough to stay fresh, not so long it lies after a big upload

# (user_id, provider_id) -> (cached_at_ts, QuotaInfo | None)
_cache: dict[tuple[int, str], tuple[float, Optional[QuotaInfo]]] = {}
# (user_id, provider_id) -> asyncio.Task  — in-flight refresh dedup
_inflight: dict[tuple[int, str], asyncio.Task] = {}


def _is_fresh(cached_at: float) -> bool:
    return (time.time() - cached_at) < TTL_SECONDS


async def _refresh(user_id: int, provider_id: str) -> Optional[QuotaInfo]:
    cls = uploader_by_id(provider_id)
    if cls is None:
        return None
    try:
        info = await cls().get_quota(user_id)
    except Exception as exc:
        # Providers raising on get_quota shouldn't break the whole
        # settings screen — surface None and let the UI render "linked"
        # without a quota bar.
        logger.debug("get_quota(%s, %s) raised: %s", user_id, provider_id, exc)
        info = None
    _cache[(user_id, provider_id)] = (time.time(), info)
    return info


async def get(
    user_id: int,
    provider_id: str,
    *,
    force_refresh: bool = False,
) -> Optional[QuotaInfo]:
    """Return cached quota for (user, provider), refreshing if stale or
    `force_refresh=True`. Concurrent callers de-dup onto a single
    in-flight refresh task."""
    key = (user_id, provider_id)
    cached = _cache.get(key)
    if cached and not force_refresh and _is_fresh(cached[0]):
        return cached[1]

    task = _inflight.get(key)
    if task is None or task.done():
        task = asyncio.create_task(_refresh(user_id, provider_id))
        _inflight[key] = task
    try:
        return await task
    finally:
        # Drop the slot so a later refresh starts a fresh task.
        if _inflight.get(key) is task:
            _inflight.pop(key, None)


def invalidate(user_id: int, provider_id: Optional[str] = None) -> None:
    """Drop cached entries — call after credential changes or a large
    upload so the next read reflects reality. With `provider_id=None`
    invalidates every provider for the user."""
    if provider_id:
        _cache.pop((user_id, provider_id), None)
        return
    for key in list(_cache.keys()):
        if key[0] == user_id:
            _cache.pop(key, None)


def snapshot(user_id: int) -> dict[str, Optional[QuotaInfo]]:
    """Return every still-fresh cached entry for `user_id`. Used by the
    settings renderer to avoid one await per provider — callers that
    only need ready data can skip the refresh logic entirely."""
    out: dict[str, Optional[QuotaInfo]] = {}
    for (uid, pid), (cached_at, info) in _cache.items():
        if uid == user_id and _is_fresh(cached_at):
            out[pid] = info
    return out


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
