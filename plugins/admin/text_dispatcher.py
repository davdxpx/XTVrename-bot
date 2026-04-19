# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
"""
Centralised text-input dispatcher for admin state-machine flows.

Replaces the monolithic ``handle_admin_text`` from ``_legacy.py``.  Each
domain module registers its state-prefix(es) via :func:`register`; the
single ``@Client.on_message`` handler here looks up the current
``admin_sessions`` state and delegates to the matching domain handler.

**Import order in __init__.py:** ``text_dispatcher`` must be imported
*before* the domain modules that call :func:`register`.
"""

from pyrogram import Client, ContinuePropagation, filters

from plugins.admin.core import admin_sessions, is_admin

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Each entry is (check_fn, handler_fn).
#   check_fn(state, state_obj) -> bool
#   handler_fn(client, message, state, state_obj, msg_id) -> None
_registry: list[tuple] = []


def register(prefix_or_check, handler):
    """Register a text handler for a state prefix or custom predicate.

    *prefix_or_check* — either a ``str`` (matched via ``state.startswith``)
    or a ``callable(state, state_obj) -> bool``.

    *handler* — ``async def handler(client, message, state, state_obj, msg_id)``
    """
    if isinstance(prefix_or_check, str):
        _p = prefix_or_check

        def _check(state, state_obj):
            return isinstance(state, str) and state.startswith(_p)

        _registry.append((_check, handler))
    elif callable(prefix_or_check):
        _registry.append((prefix_or_check, handler))


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
# group=-3 is intentionally ahead of every other text handler in the codebase:
#   -2 myfiles, -1 debug, 0 xtv_pro_setup, 1 admin-setup, …
# so an active admin_sessions state is always the first thing considered.
# The handler raises ContinuePropagation whenever it has nothing to do,
# which lets downstream handlers run normally.
@Client.on_message(
    (filters.text | filters.forwarded) & filters.private & ~filters.regex(r"^/"),
    group=-3,
)
async def admin_text_dispatcher(client, message):
    if not message.from_user:
        raise ContinuePropagation

    user_id = message.from_user.id
    if not is_admin(user_id):
        raise ContinuePropagation

    state_obj = admin_sessions.get(user_id)
    if not state_obj:
        raise ContinuePropagation

    state = state_obj if isinstance(state_obj, str) else state_obj.get("state")
    msg_id = None if isinstance(state_obj, str) else state_obj.get("msg_id")

    for check_fn, handler_fn in _registry:
        if check_fn(state, state_obj):
            await handler_fn(client, message, state, state_obj, msg_id)
            return

    # No registered handler matched — let other handlers try.
    raise ContinuePropagation


# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
