user_data = {}

# === Helper Functions ===
def get_state(user_id):
    return user_data.get(user_id, {}).get("state")

def set_state(user_id, state):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["state"] = state

def update_data(user_id, key, value):
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id][key] = value

def get_data(user_id):
    return user_data.get(user_id, {})

def clear_session(user_id):
    user_data.pop(user_id, None)

# --------------------------------------------------------------------------
# Developed by 𝕏0L0™ (@davdxpx) | © 2026 XTV Network Global
# Don't Remove Credit
# Telegram Channel @XTVbots
# Developed for the 𝕏TV Network @XTVglobal
# Backup Channel @XTVhome
# Contact on Telegram @davdxpx
# --------------------------------------------------------------------------
