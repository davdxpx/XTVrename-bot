user_data = {}

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
