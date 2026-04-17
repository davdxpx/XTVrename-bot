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
    is_admin,
    edit_or_reply,
    get_admin_main_menu,
    get_admin_access_limits_menu,
)

# Guarantee all submodule handlers register on import, independent of
# pyrofork's plugin discovery behaviour.
# text_dispatcher must be imported first — it provides register() used
# by domain modules to register their text-input state handlers.
from . import text_dispatcher  # noqa: F401
from . import noop  # noqa: F401
from . import dumb_channels  # noqa: F401
from . import dashboard  # noqa: F401
from . import users_mod  # noqa: F401
from . import setup  # noqa: F401
from . import users  # noqa: F401
from . import broadcast  # noqa: F401
from . import general  # noqa: F401
from . import panel  # noqa: F401
from . import feature_toggles  # noqa: F401
from . import thumbnails  # noqa: F401
from . import templates  # noqa: F401
from . import public_settings  # noqa: F401
from . import force_sub  # noqa: F401
from . import myfiles  # noqa: F401
from . import payments  # noqa: F401
from . import premium  # noqa: F401

__all__ = [
    "admin_sessions",
    "is_admin",
    "edit_or_reply",
    "get_admin_main_menu",
    "get_admin_access_limits_menu",
]
