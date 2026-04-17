"""Mirror-Leech subsystem.

Imports every downloader / uploader module so their `@register_*`
decorators fire at startup. Call sites only need to import
`tools.mirror_leech` to make the registry fully populated.

Packaging convention mirrors the rest of tools/: each concrete provider
lives in its own PascalCase file (tools/mirror_leech/uploaders/GoogleDrive.py
alongside tools/FileConverter.py, tools/YouTubeTool.py, etc.).
"""

from __future__ import annotations

# Eager-import concrete modules so registration decorators run. Keep these
# inside a try/except so an operator who removes e.g. `mega.py` from
# requirements.txt still gets a bot that boots — the specific uploader
# simply stays unavailable in the admin panel.

def _safe_import(mod: str) -> None:
    try:
        __import__(mod)
    except Exception as exc:  # pragma: no cover - optional deps
        import logging

        logging.getLogger("tools.mirror_leech").info(
            "Skipping mirror-leech module %s: %s", mod, exc
        )


# Downloaders
_safe_import("tools.mirror_leech.downloaders.HTTPDownloader")
_safe_import("tools.mirror_leech.downloaders.YTDLPDownloader")
_safe_import("tools.mirror_leech.downloaders.TelegramDownloader")
_safe_import("tools.mirror_leech.downloaders.RSSDownloader")
# torrent-edition only: wraps the aria2 daemon started by the Dockerfile.
_safe_import("tools.mirror_leech.downloaders.MLTorrentDownloader")

# Uploaders
_safe_import("tools.mirror_leech.uploaders.GoogleDrive")
_safe_import("tools.mirror_leech.uploaders.Rclone")
_safe_import("tools.mirror_leech.uploaders.MEGA")
_safe_import("tools.mirror_leech.uploaders.GoFile")
_safe_import("tools.mirror_leech.uploaders.Pixeldrain")
_safe_import("tools.mirror_leech.uploaders.TelegramUploader")
_safe_import("tools.mirror_leech.uploaders.DDL")
