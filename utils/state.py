import asyncio
import time

_STATE_TTL = 3600  # 1 hour — sessions expire after inactivity

user_data = {}
_timestamps = {}
_on_expire_callbacks = []

# Per-user asyncio.Lock registry. Prevents two concurrent handlers
# (e.g. user rapid-fires text input while a callback still writes state)
# from clobbering each other's writes.
_session_locks = {}


def session_lock(user_id):
    """Return (creating if necessary) an asyncio.Lock scoped to a user's
    session. Callers `async with session_lock(uid):` around compound
    read-modify-write operations on user_data."""
    lock = _session_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[user_id] = lock
    return lock


def register_expire_callback(fn):
    """Register a callback to be called with user_id when a session expires."""
    _on_expire_callbacks.append(fn)

# === Helper Functions ===
def _touch(user_id):
    # Sliding TTL: every read *or* write bumps last-activity. Prevents the
    # 30-minute cleanup task from killing an actively used session.
    _timestamps[user_id] = time.time()

def _maybe_expire(user_id):
    ts = _timestamps.get(user_id)
    if ts and (time.time() - ts > _STATE_TTL):
        user_data.pop(user_id, None)
        _timestamps.pop(user_id, None)
        _session_locks.pop(user_id, None)

def get_state(user_id):
    _maybe_expire(user_id)
    state = user_data.get(user_id, {}).get("state")
    # Touch on read so the TTL slides forward while the user is active.
    if state is not None:
        _touch(user_id)
    return state

def set_state(user_id, state):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["state"] = state
    _touch(user_id)

def update_data(user_id, key_or_dict, value=None):
    if user_id not in user_data:
        user_data[user_id] = {}
    if isinstance(key_or_dict, dict):
        user_data[user_id].update(key_or_dict)
    else:
        user_data[user_id][key_or_dict] = value
    _touch(user_id)

def get_data(user_id):
    _maybe_expire(user_id)
    data = user_data.get(user_id, {})
    if data:
        _touch(user_id)
    return data

def clear_session(user_id):
    user_data.pop(user_id, None)
    _timestamps.pop(user_id, None)
    _session_locks.pop(user_id, None)
    _db_persist_pending.discard(user_id)

_db_persist_pending = set()

def mark_for_db_persist(user_id):
    """Mark a session as needing DB persistence (for crash recovery)."""
    _db_persist_pending.add(user_id)

def needs_db_persist(user_id):
    return user_id in _db_persist_pending

def cleanup_expired():
    """Remove all expired sessions. Called periodically from main.py.

    Uses last-activity timestamps (sliding TTL) so active users are never
    swept mid-flow. Locks are also released so stale references don't
    linger."""
    now = time.time()
    expired = [uid for uid, ts in _timestamps.items() if now - ts > _STATE_TTL]
    for uid in expired:
        user_data.pop(uid, None)
        _timestamps.pop(uid, None)
        _session_locks.pop(uid, None)
        _db_persist_pending.discard(uid)
        for cb in _on_expire_callbacks:
            try:
                cb(uid)
            except Exception:
                pass
    return len(expired)


def requires_state(*expected_states):
    """Decorator for message handlers that should only process when the
    user's session is in one of the given states. If the state doesn't
    match, raises `ContinuePropagation` so the message can reach the next
    handler group (prevents handler-group collisions for rapid-fire input).

    Usage:
        @Client.on_message(filters.text & filters.private, group=5)
        @requires_state("awaiting_search_movie", "awaiting_search_series")
        async def search_handler(client, message):
            ...
    """
    from pyrogram import ContinuePropagation

    def decorator(fn):
        async def wrapper(client, message, *args, **kwargs):
            user_id = None
            try:
                user_id = message.from_user.id if message.from_user else message.chat.id
            except Exception:
                raise ContinuePropagation
            state = get_state(user_id)
            if state not in expected_states:
                raise ContinuePropagation
            return await fn(client, message, *args, **kwargs)

        wrapper.__name__ = getattr(fn, "__name__", "wrapped")
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
