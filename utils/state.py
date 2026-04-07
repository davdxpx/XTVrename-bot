import time

_STATE_TTL = 3600  # 1 hour — sessions expire after inactivity

user_data = {}
_timestamps = {}

# === Helper Functions ===
def _touch(user_id):
    _timestamps[user_id] = time.time()

def _maybe_expire(user_id):
    ts = _timestamps.get(user_id)
    if ts and (time.time() - ts > _STATE_TTL):
        user_data.pop(user_id, None)
        _timestamps.pop(user_id, None)

def get_state(user_id):
    _maybe_expire(user_id)
    return user_data.get(user_id, {}).get("state")

def set_state(user_id, state):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["state"] = state
    _touch(user_id)

def update_data(user_id, key, value):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id][key] = value
    _touch(user_id)

def get_data(user_id):
    _maybe_expire(user_id)
    return user_data.get(user_id, {})

def clear_session(user_id):
    user_data.pop(user_id, None)
    _timestamps.pop(user_id, None)

def cleanup_expired():
    """Remove all expired sessions. Called periodically from main.py."""
    now = time.time()
    expired = [uid for uid, ts in _timestamps.items() if now - ts > _STATE_TTL]
    for uid in expired:
        user_data.pop(uid, None)
        _timestamps.pop(uid, None)
    return len(expired)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
