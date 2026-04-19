# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""utils.telegram — Telegram-specific helpers (logging, safe edits, progress).

Re-exports the public API of the sibling modules.
"""

from utils.telegram.log import get_logger
from utils.telegram.logger import debug

__all__ = [
    "debug",
    "get_logger",
    "progress_for_pyrogram",
    "safe_answer",
    "safe_edit",
    "safe_edit_message_text",
    "safe_send",
]


_LAZY = {
    "progress_for_pyrogram": ("utils.telegram.progress", "progress_for_pyrogram"),
    "safe_answer": ("utils.telegram.safe", "safe_answer"),
    "safe_edit": ("utils.telegram.safe", "safe_edit"),
    "safe_edit_message_text": ("utils.telegram.safe", "safe_edit_message_text"),
    "safe_send": ("utils.telegram.safe", "safe_send"),
}


def __getattr__(name):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'utils.telegram' has no attribute {name!r}")
    import importlib
    return getattr(importlib.import_module(target[0]), target[1])
