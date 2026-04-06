import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix the field extraction for public settings
search_str = """        field = data.replace(
            "prompt_public_",
            "").replace(
            "prompt_daily_",
            "daily_")
        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})"""

replace_str = """        field_map = {"nam": "bot_name", "com": "community_name", "con": "support_contact", "gleg": "global_daily_egress"}
        raw_field = data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_")
        field = field_map.get(raw_field, raw_field)
        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})"""

content = content.replace(search_str, replace_str)

with open('plugins/admin.py', 'w') as f:
    f.write(content)
