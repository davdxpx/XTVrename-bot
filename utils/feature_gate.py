# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# --------------------------------------------------------------------------
"""Feature-toggle gate used by every UI surface.

Reads `feature_toggles` from the settings layer with a minimal cache
(wrapping Database.get_setting is enough) and applies per-plan overrides
for premium users in PUBLIC_MODE. Returns False when a feature is off so
callers can simply skip rendering the corresponding button — the caller
also MUST check before executing the action to defend against direct
callback posting.
"""

from __future__ import annotations

from config import Config

# Keys that NEVER require the user to be premium (always respect global
# toggle only). Keep the set small — most myfiles_* keys are plan-
# gateable.
_GLOBAL_ONLY_KEYS = frozenset({
    "mirror_leech",
    "myfiles_enabled",
    "myfiles_audit",
})


async def feature_enabled(key: str, user_id: int | None = None) -> bool:
    """True iff the named feature is globally on and (optionally) the
    user's plan does not explicitly override it off."""
    from db import db

    if db is None or db.settings is None:
        return False

    toggles = await db.get_setting("feature_toggles", {}) or {}
    if not isinstance(toggles, dict):
        return False
    if not toggles.get(key, False):
        return False

    # Global-only keys skip per-plan overrides.
    if key in _GLOBAL_ONLY_KEYS:
        return True
    if user_id is None or not Config.PUBLIC_MODE:
        return True

    user = await db.get_user(user_id) if hasattr(db, "get_user") else None
    if not user or not user.get("is_premium"):
        return True

    plan = user.get("premium_plan") or "standard"
    plan_doc = await db.get_setting(f"premium_{plan}", {}) or {}
    plan_features = (plan_doc.get("features") or {}) if isinstance(
        plan_doc, dict
    ) else {}
    if key in plan_features:
        return bool(plan_features[key])
    return True


async def feature_many(keys: list[str], user_id: int | None = None) -> dict:
    """Bulk check — returns {key: bool} so a menu render can fetch the
    relevant toggles with one settings round-trip."""
    from db import db

    if db is None or db.settings is None:
        return {k: False for k in keys}

    toggles = await db.get_setting("feature_toggles", {}) or {}
    if not isinstance(toggles, dict):
        toggles = {}

    result: dict[str, bool] = {}
    plan_features: dict | None = None
    needs_plan = (
        Config.PUBLIC_MODE and user_id is not None
        and any(k not in _GLOBAL_ONLY_KEYS for k in keys)
    )
    if needs_plan:
        user = await db.get_user(user_id) if hasattr(db, "get_user") else None
        if user and user.get("is_premium"):
            plan = user.get("premium_plan") or "standard"
            plan_doc = await db.get_setting(f"premium_{plan}", {}) or {}
            pf = plan_doc.get("features") if isinstance(plan_doc, dict) else None
            if isinstance(pf, dict):
                plan_features = pf

    for k in keys:
        if not toggles.get(k, False):
            result[k] = False
            continue
        if k in _GLOBAL_ONLY_KEYS:
            result[k] = True
            continue
        if plan_features is not None and k in plan_features:
            result[k] = bool(plan_features[k])
        else:
            result[k] = True
    return result
