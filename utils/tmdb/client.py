# --- Imports ---
import asyncio
import time

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

tmdb = TMDb()

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
