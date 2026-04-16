"""URL / file classifier → downloader picker.

Pure-function core so the routing logic is unit-testable without any I/O.
`pick_downloader(source)` returns the first registered downloader whose
`accepts()` method returns True, or raises `UnsupportedSourceError`.
"""

from __future__ import annotations

import re
from typing import Optional

from tools.mirror_leech.downloaders import all_downloaders

_MAGNET_RE = re.compile(r"^magnet:\?", re.IGNORECASE)
_TORRENT_EXT_RE = re.compile(r"\.torrent($|\?)", re.IGNORECASE)


class UnsupportedSourceError(RuntimeError):
    """Raised when Controller cannot find a downloader willing to handle
    the source. User-facing message comes from `.args[0]`."""


def _is_torrent(source: str) -> bool:
    return bool(_MAGNET_RE.match(source) or _TORRENT_EXT_RE.search(source))


async def pick_downloader(source: str, context: Optional[dict] = None) -> type:
    """Return the first registered Downloader class that accepts `source`.

    Raises UnsupportedSourceError with a friendly message when nothing
    matches — including an explicit rejection for magnet / torrent sources
    (torrent support lives on the `torrent-edition` branch, not here).
    """
    if _is_torrent(source):
        raise UnsupportedSourceError(
            "🚫 **Torrent / magnet is not supported on this branch.**\n\n"
            "Mirror-Leech on the main branch covers direct HTTP(S) URLs, "
            "YouTube-DL sources, Telegram files, and RSS feeds. For "
            "torrent-edition features, use the `torrent-edition` branch."
        )

    ctx = context or {}
    for cls in all_downloaders():
        try:
            accepted = await cls.accepts(source, ctx)
        except Exception:  # pragma: no cover - downloader bug shouldn't crash pick
            accepted = False
        if accepted:
            return cls
    raise UnsupportedSourceError(
        f"🤔 Can't figure out how to fetch `{source}`. Supported sources "
        "are direct HTTP(S) URLs, YouTube-DL-compatible pages, Telegram "
        "file refs, and RSS feeds."
    )
