# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""utils.tmdb — TMDb client + admin gate.

Importers expecting the legacy ``from utils.tmdb import tmdb`` singleton
style continue to work via the re-export below.
"""

from utils.tmdb.gate import (
    TMDB_DOCS_URL,
    ensure_tmdb,
    is_tmdb_available,
    tmdb_docs_keyboard,
    tmdb_required_message,
)

__all__ = [
    "TMDB_DOCS_URL",
    "TMDb",
    "ensure_tmdb",
    "is_tmdb_available",
    "tmdb",
    "tmdb_docs_keyboard",
    "tmdb_required_message",
]


def __getattr__(name):
    if name in ("TMDb", "tmdb"):
        from utils.tmdb import client as _client
        return getattr(_client, name)
    raise AttributeError(f"module 'utils.tmdb' has no attribute {name!r}")
