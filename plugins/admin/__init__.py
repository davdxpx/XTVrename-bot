# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
`plugins.admin` — the admin panel package.

This package replaces the former monolithic plugins/admin.py. Shared state
and helpers live in `core`; callback / message handlers are split across
domain-specific submodules.

For backward compatibility with callers that used to do
`from plugins.admin import admin_sessions` (e.g. force_sub_handler.py),
we re-export the core names at the package level.
"""

from plugins.admin.core import (
    admin_sessions,
    edit_or_reply,
    get_admin_access_limits_menu,
    get_admin_main_menu,
    is_admin,
)

# Guarantee all submodule handlers register on import, independent of
# pyrofork's plugin discovery behaviour.
# text_dispatcher must be imported first — it provides register() used
# by domain modules to register their text-input state handlers.
from . import (
    broadcast,  # noqa: F401
    dashboard,  # noqa: F401
    dumb_channels,  # noqa: F401
    feature_toggles,  # noqa: F401
    force_sub,  # noqa: F401
    general,  # noqa: F401
    myfiles,  # noqa: F401
    noop,  # noqa: F401
    panel,  # noqa: F401
    payments,  # noqa: F401
    premium,  # noqa: F401
    public_settings,  # noqa: F401
    setup,  # noqa: F401
    templates,  # noqa: F401
    text_dispatcher,  # noqa: F401
    thumbnails,  # noqa: F401
    users,  # noqa: F401
    users_mod,  # noqa: F401
)

__all__ = [
    "admin_sessions",
    "is_admin",
    "edit_or_reply",
    "get_admin_main_menu",
    "get_admin_access_limits_menu",
]
