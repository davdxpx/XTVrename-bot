import aiohttp
from config import Config

class TMDb:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

    def __init__(self):
        self.api_key = Config.TMDB_API_KEY

    async def _request(self, endpoint, params=None):
        if params is None:
            params = {}
        else:
            params = params.copy()

        params["api_key"] = self.api_key

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.BASE_URL}{endpoint}", params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
            except Exception as e:
                return None

    async def search_movie(self, query):
        data = await self._request("/search/movie", {"query": query})
        if not data or "results" not in data:
            return []

        results = []
        for item in data["results"][:5]:
            year = item.get("release_date", "")[:4] if item.get("release_date") else "N/A"
            poster = f"{self.IMAGE_BASE_URL}{item['poster_path']}" if item.get("poster_path") else None
            results.append({
                "id": item["id"],
                "title": item["title"],
                "year": year,
                "poster_path": poster,
                "overview": item.get("overview", ""),
                "type": "movie"
            })
        return results

    async def search_tv(self, query):
        data = await self._request("/search/tv", {"query": query})
        if not data or "results" not in data:
            return []

        results = []
        for item in data["results"][:5]:
            year = item.get("first_air_date", "")[:4] if item.get("first_air_date") else "N/A"
            poster = f"{self.IMAGE_BASE_URL}{item['poster_path']}" if item.get("poster_path") else None
            results.append({
                "id": item["id"],
                "title": item["name"],
                "year": year,
                "poster_path": poster,
                "overview": item.get("overview", ""),
                "type": "tv"
            })
        return results

    async def get_details(self, media_type, tmdb_id):
        endpoint = f"/movie/{tmdb_id}" if media_type == "movie" else f"/tv/{tmdb_id}"
        return await self._request(endpoint)

tmdb = TMDb()
