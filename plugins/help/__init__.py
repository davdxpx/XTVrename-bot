# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""plugins.help — Help/Docs feature package.

Re-exports the most frequently imported builder symbols so other plugins
(e.g. plugins.premium) can keep the short ``from plugins.help import X``
form.

Importing this package registers the Pyrogram ``/help`` command and the
``help_*`` callback router in ``handlers``.

Mode: BOTH (public + non-public). Content changes per mode is handled by
``HelpContext`` inside builder.py — there is no per-mode gate at the
handler level.
"""

from plugins.help.builder import (
    HelpContext,
    build_help_context,
    build_main_menu,
    format_egress,
)

from . import handlers  # noqa: F401  (registers @Client handlers)

__all__ = [
    "HelpContext",
    "build_help_context",
    "build_main_menu",
    "format_egress",
]
