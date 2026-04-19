# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""utils.auth — authentication, access gates, and feature toggles.

Re-exports the public API of the three sibling modules so call-sites can
keep the compact ``from utils.auth import is_authorized`` form. Importers
that want the canonical submodule path (``utils.auth.auth.is_authorized``)
can still use it.
"""

from utils.auth.auth import auth_filter, check_force_sub, is_admin, is_authorized
from utils.auth.feature_gate import feature_enabled, feature_many
from utils.auth.gate import check_and_send_welcome, send_force_sub_gate
from utils.auth.mode import is_public_mode, non_public_only, public_only

__all__ = [
    "auth_filter",
    "check_and_send_welcome",
    "check_force_sub",
    "feature_enabled",
    "feature_many",
    "is_admin",
    "is_authorized",
    "is_public_mode",
    "non_public_only",
    "public_only",
    "send_force_sub_gate",
]
