# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""plugins.public_cmds — user-facing commands.

Split into:
  - handlers: /info, /settings, and the big user_settings_callback router
    (both public and non-public flows)
  - usage:    /usage command + refresh_usage callback (PUBLIC-ONLY)

Submodules are imported here so Pyrogram's plugin-discovery registers
their handlers.
"""

from plugins.public_cmds.handlers import is_public_mode

from . import handlers  # noqa: F401  (registers @Client handlers)
from . import usage     # noqa: F401  (registers @Client handlers)

__all__ = ["is_public_mode"]
