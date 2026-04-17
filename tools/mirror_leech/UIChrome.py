# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Shared UI chrome for Mirror-Leech screens.

Every user-facing message (picker, progress, queue, config, results)
wraps its body with the same divider lines and XTVEngine signature used
by the Rename / Convert / Audio flows. Keeping the helpers here means
one place to tweak the visual style across all Mirror-Leech surfaces.
"""

from __future__ import annotations

from utils.XTVengine import XTVEngine

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"
BAR_LENGTH = 10
BLOCK_FILLED = "■"
BLOCK_EMPTY = "□"


def frame(header: str, body: str, *, mode: str = "core") -> str:
    """Wrap `body` with header, two dividers and the engine signature."""
    return (
        f"{header}\n"
        f"{DIVIDER}\n\n"
        f"{body}\n\n"
        f"{DIVIDER}\n"
        f"{XTVEngine.get_signature(mode=mode)}"
    )


def progress_block(fraction: float) -> str:
    """Render the Rename-style progress block — percentage + bar."""
    pct = max(0.0, min(1.0, fraction)) * 100
    filled = int(pct // (100 / BAR_LENGTH))
    bar = BLOCK_FILLED * filled + BLOCK_EMPTY * (BAR_LENGTH - filled)
    return f"**Progress:**  `{pct:.1f}%`\n[{bar}]"


def format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_eta(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
