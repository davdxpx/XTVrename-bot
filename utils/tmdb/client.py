# --- Imports ---
import asyncio
import time
from typing import Dict, List, Tuple

import aiohttp

from config import Config
from utils.telegram.log import get_logger
from utils.tmdb.gate import is_tmdb_available

logger = get_logger("utils.tmdb")

_MISSING_KEY_LOGGED = False

# === Classes ===
class TMDb:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
    _CACHE_TTL = 600  # 10 minutes for search/detail results
    _MAX_RETRIES = 3

    def __init__(self):
        self.api_key = Config.TMDB_API_KEY
        self._session = None
        self._cache = {}  # key -> (timestamp, data)

    async def _get_session(self):
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _get_cached(self, cache_key):
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if time.time() - cached_time < self._CACHE_TTL:
                return cached_data
            del self._cache[cache_key]
        return None

    def _set_cached(self, cache_key, data):
        self._cache[cache_key] = (time.time(), data)
        # Evict old entries if cache grows too large
        if len(self._cache) > 500:
            now = time.time()
            expired = [k for k, (t, _) in self._cache.items() if now - t > self._CACHE_TTL]
            for k in expired:
                del self._cache[k]

    async def _request(self, endpoint, params=None, language="en-US"):
        # Short-circuit when no TMDB_API_KEY is configured. Logging once at
        # INFO keeps startup clean; repeated hits stay silent.
        global _MISSING_KEY_LOGGED
        if not is_tmdb_available():
            if not _MISSING_KEY_LOGGED:
                logger.info(
                    "TMDb disabled — set TMDB_API_KEY to enable title matching."
                )
                _MISSING_KEY_LOGGED = True
            return None

        params = {} if params is None else params.copy()

        params["api_key"] = self.api_key
        params["language"] = language

        cache_key = f"{endpoint}:{sorted(params.items())}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        session = await self._get_session()

        for attempt in range(self._MAX_RETRIES):
            try:
                async with session.get(
                    f"{self.BASE_URL}{endpoint}", params=params
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._set_cached(cache_key, data)
                        return data
                    if resp.status == 429:  # Rate limited
                        retry_after = int(resp.headers.get("Retry-After", 2))
                        logger.warning(f"TMDb rate limited, retrying in {retry_after}s...")
                        await asyncio.sleep(retry_after)
                        continue
                    logger.warning(f"TMDb API returned {resp.status} for {endpoint}")
                    return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < self._MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    logger.warning(f"TMDb request failed (attempt {attempt + 1}): {e}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"TMDb request failed after {self._MAX_RETRIES} attempts: {e}")
                    return None

        return None

    async def search_movie(self, query, language="en-US"):
        data = await self._request("/search/movie", {"query": query}, language)
        if not data or "results" not in data:
            return []

        results = []
        for item in data["results"][:5]:
            year = (
                item.get("release_date", "")[:4] if item.get("release_date") else "N/A"
            )
            poster = (
                f"{self.IMAGE_BASE_URL}{item['poster_path']}"
                if item.get("poster_path")
                else None
            )
            results.append(
                {
                    "id": item["id"],
                    "title": item["title"],
                    "year": year,
                    "poster_path": poster,
                    "overview": item.get("overview", ""),
                    "type": "movie",
                }
            )
        return results

    async def search_tv(self, query, language="en-US"):
        data = await self._request("/search/tv", {"query": query}, language)
        if not data or "results" not in data:
            return []

        results = []
        for item in data["results"][:5]:
            year = (
                item.get("first_air_date", "")[:4]
                if item.get("first_air_date")
                else "N/A"
            )
            poster = (
                f"{self.IMAGE_BASE_URL}{item['poster_path']}"
                if item.get("poster_path")
                else None
            )
            results.append(
                {
                    "id": item["id"],
                    "title": item["name"],
                    "year": year,
                    "poster_path": poster,
                    "overview": item.get("overview", ""),
                    "type": "tv",
                }
            )
        return results

    async def get_details(self, media_type, tmdb_id, language="en-US"):
        endpoint = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
        return await self._request(endpoint, language=language)

    # ------------------------------------------------------------------
    # Placeholder-details cache
    # ------------------------------------------------------------------
    # ``get_details`` already memoises the raw HTTP response for 10 minutes
    # inside ``_cache``. The placeholder layer on top of TMDb only needs
    # a small subset of fields and benefits from a longer-lived, bounded
    # cache so a batch of 40 files with the same tmdb_id stays cheap
    # across hours. Keyed on ``(tmdb_id, media_type)`` so a numeric id
    # that exists as both (rare but possible) doesn't collide.

    _DETAILS_CACHE_MAX = 1000
    _details_cache: "Dict[Tuple[int, str], Dict[str, object]]" = {}
    _details_cache_order: "List[Tuple[int, str]]" = []

    async def get_details_cached(self, tmdb_id, media_type):
        """Return a trimmed dict of TMDb fields used by template
        placeholders. Cached per process with a simple LRU up to
        ``_DETAILS_CACHE_MAX`` entries. Returns ``None`` when TMDb is
        unavailable or the id doesn't resolve.

        Keys returned when available: ``title``, ``original_title``,
        ``overview``, ``tagline``, ``vote_average``, ``runtime``,
        ``genres`` (list of names), ``release_date``, ``first_air_date``,
        ``number_of_seasons``, ``number_of_episodes``,
        ``original_language``, ``production_countries`` (list of iso),
        ``networks`` (list of names).
        """
        if not tmdb_id:
            return None
        try:
            cache_key = (int(tmdb_id), "tv" if media_type == "series" else "movie")
        except (TypeError, ValueError):
            return None

        cached = type(self)._details_cache.get(cache_key)
        if cached is not None:
            # LRU touch
            import contextlib as _contextlib
            order = type(self)._details_cache_order
            with _contextlib.suppress(ValueError):
                order.remove(cache_key)
            order.append(cache_key)
            return cached

        data = await self.get_details(cache_key[1], cache_key[0])
        if not data:
            return None

        trimmed = {
            "title": data.get("title") or data.get("name") or "",
            "original_title": (
                data.get("original_title") or data.get("original_name") or ""
            ),
            "overview": data.get("overview") or "",
            "tagline": data.get("tagline") or "",
            "vote_average": data.get("vote_average") or 0,
            "runtime": (
                data.get("runtime")
                or (data.get("episode_run_time") or [None])[0]
                or 0
            ),
            "genres": [g.get("name", "") for g in (data.get("genres") or []) if g.get("name")],
            "release_date": data.get("release_date") or "",
            "first_air_date": data.get("first_air_date") or "",
            "number_of_seasons": data.get("number_of_seasons") or 0,
            "number_of_episodes": data.get("number_of_episodes") or 0,
            "original_language": data.get("original_language") or "",
            "production_countries": [
                c.get("iso_3166_1", "")
                for c in (data.get("production_countries") or [])
                if c.get("iso_3166_1")
            ],
            "networks": [
                n.get("name", "") for n in (data.get("networks") or []) if n.get("name")
            ],
        }

        cache = type(self)._details_cache
        order = type(self)._details_cache_order
        cache[cache_key] = trimmed
        order.append(cache_key)
        while len(order) > self._DETAILS_CACHE_MAX:
            evict = order.pop(0)
            cache.pop(evict, None)
        return trimmed


tmdb = TMDb()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
