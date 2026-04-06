import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# I see the duplicate key `awaiting_premium_`.
# One handles egress/files/stars (`_handle_awaiting_premium__11`), the other handles price (`_handle_state_12`).
# Let's combine them or change the prefix logic.
# Wait, they were separated by `if isinstance(state, str)` and `if isinstance(state, dict)`.
# Since `ADMIN_TEXT_ROUTERS` maps prefix to function, we can't have both.
# I'll create a master `_handle_awaiting_premium_` that delegates based on `isinstance(state_obj, dict)`.
# Or I can just rename the second one to `awaiting_premium_price` but that requires updating the state when saving it.
# Let's combine them into one wrapper function.

wrapper = """
async def _handle_awaiting_premium__master(client, message, user_id, state, msg_id, state_obj):
    if isinstance(state_obj, dict) and state_obj.get("currency"):
        await _handle_state_12(client, message, user_id, state, msg_id, state_obj)
    else:
        await _handle_awaiting_premium__11(client, message, user_id, state, msg_id, state_obj)
"""

content = content.replace(
    '    "awaiting_premium_": _handle_awaiting_premium__11,\n    "awaiting_premium_": _handle_state_12,',
    '    "awaiting_premium_": _handle_awaiting_premium__master,'
)

content += "\n" + wrapper

# Fix 3: Undefined set_state in `admin_prompt_lookup_cb`
content = content.replace(
    'from utils.state import set_state\n\n    set_state(callback_query.from_user.id, "awaiting_user_lookup")',
    'await set_admin_state(callback_query.from_user.id, {"state": "awaiting_user_lookup", "msg_id": callback_query.message.id})'
)
# And get_state in admin_handle_user_lookup_text
content = content.replace(
    'from utils.state import get_state, clear_session\n\n    state = get_state(message.from_user.id)',
    'state_obj = await get_admin_state(message.from_user.id)\n    state = state_obj.get("state") if isinstance(state_obj, dict) else state_obj'
)
content = content.replace('clear_session(message.from_user.id)', 'await clear_admin_state(message.from_user.id)')

# Fix 4: `admin_view` is under `admin_main_callback`, but its decorator is `^(adm_main|adm_cancel)`.
content = re.sub(
    r'@Client\.on_callback_query\(filters\.regex\(r"\^\(adm_main\|adm_cancel\)"\)\)',
    r'@Client.on_callback_query(filters.regex(r"^(adm_main|adm_cancel|adm_view)"))',
    content
)

with open('plugins/admin.py', 'w') as f:
    f.write(content)
