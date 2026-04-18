"""RSS feed downloader: fans a feed URL out into individual item downloads.

Strictly speaking RSS isn't a download protocol — this module treats a
feed URL as a meta-source: accept if the URL ends in `.rss` / `.xml` /
contains `/feed/`, then delegate the first unseen enclosure to the HTTP
downloader. Full polling scheduling lives in plugins/mirror_leech_ui.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.mirror_leech.downloaders import Downloader, register_downloader
from tools.mirror_leech.downloaders.HTTPDownloader import HTTPDownloader
from tools.mirror_leech.Tasks import MLContext
from utils.log import get_logger

logger = get_logger("mirror_leech.rss")

_RSS_HINT_RE = re.compile(r"(\.rss($|\?)|\.xml($|\?)|/feed/?)", re.IGNORECASE)


@register_downloader
class RSSDownloader(Downloader):
    id = "rss"
    display_name = "RSS feed (first new enclosure)"

    @classmethod
    async def accepts(cls, source: str, context: dict) -> bool:
        if context and context.get("rss_force"):
            return True
        return bool(_RSS_HINT_RE.search(source))

    async def download(self, ctx: MLContext) -> Path:
        import aiohttp

        try:
            import feedparser  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "feedparser is not installed; `pip install feedparser`"
            ) from exc

        ctx.status("downloading")
        async with aiohttp.ClientSession() as session, session.get(ctx.source) as resp:
            resp.raise_for_status()
            body = await resp.read()

        feed = feedparser.parse(body)
        if not feed.entries:
            raise RuntimeError("RSS feed has no entries")

        first = feed.entries[0]
        enclosure_url = None
        if getattr(first, "enclosures", None):
            enclosure_url = first.enclosures[0].get("href")
        elif getattr(first, "link", None):
            enclosure_url = first.link
        if not enclosure_url:
            raise RuntimeError("RSS first entry has no enclosure / link to download")

        # Delegate the actual byte transfer to HTTPDownloader.
        ctx.source = enclosure_url  # let any further progress messages show the real URL
        return await HTTPDownloader().download(ctx)
