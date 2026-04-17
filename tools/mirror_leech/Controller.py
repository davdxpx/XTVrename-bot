"""URL / file classifier → downloader picker.

Pure-function core so the routing logic is unit-testable without any I/O.
`pick_downloader(source)` returns the first registered downloader whose
`accepts()` method returns True, or raises `UnsupportedSourceError`.
"""

from __future__ import annotations

from typing import Optional

from tools.mirror_leech.downloaders import all_downloaders


class UnsupportedSourceError(RuntimeError):
    """Raised when Controller cannot find a downloader willing to handle
    the source. User-facing message comes from `.args[0]`."""


async def pick_downloader(source: str, context: Optional[dict] = None) -> type:
    """Return the first registered Downloader class that accepts `source`.

    Raises UnsupportedSourceError with a friendly message when no
    registered downloader is willing to handle the source. Peer-to-peer
    link formats are intentionally NOT supported on this branch; they
    fall through to the generic "can't fetch this" response.
    """
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
        "are direct HTTP(S) URLs, yt-dlp-compatible pages, Telegram file "
        "refs, and RSS feeds."
    )
