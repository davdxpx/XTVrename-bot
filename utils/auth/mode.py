# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""utils.auth.mode — Public-mode vs. Non-public-mode helpers.

Central place so every plugin can ask the same question the same way.
Also provides two small decorators that short-circuit a handler whose
body is only meaningful in one of the two modes.

Usage:
    from utils.auth.mode import is_public_mode, public_only

    @Client.on_message(filters.command("info") & filters.private)
    @public_only
    async def info_command(client, message):
        ...
"""

from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable, TypeVar

from config import Config

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def is_public_mode() -> bool:
    """True when the bot is running in Public mode (multi-tenant)."""
    return bool(Config.PUBLIC_MODE)


def public_only(func: F) -> F:
    """Decorator — run the handler only in Public mode, else silently no-op."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not is_public_mode():
            return None
        return await func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def non_public_only(func: F) -> F:
    """Decorator — run the handler only in Non-public mode, else silently no-op."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if is_public_mode():
            return None
        return await func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
