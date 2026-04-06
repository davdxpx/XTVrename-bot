import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix 1: Mismatched prefixes (adm_tpl_pt_, adm_fn_pt_, adm_dmb_ren_, adm_dmb_ds_).
# Let's forcefully replace them in the conditional checks.
content = content.replace('data.startswith("prompt_template_")', 'data.startswith("adm_tpl_pt_")')
content = content.replace('data.replace("prompt_template_", "")', 'data.replace("adm_tpl_pt_", "")')
content = content.replace('data.startswith("prompt_fn_template_")', 'data.startswith("adm_fn_pt_")')
content = content.replace('data.replace("prompt_fn_template_", "")', 'data.replace("adm_fn_pt_", "")')
content = content.replace('data.startswith("dumb_ren_")', 'data.startswith("adm_dmb_ren_")')
content = content.replace('data.replace("dumb_ren_", "")', 'data.replace("adm_dmb_ren_", "")')
content = content.replace('data.startswith("dumb_def_std_")', 'data.startswith("adm_dmb_ds_")')
content = content.replace('data.replace("dumb_def_std_", "")', 'data.replace("adm_dmb_ds_", "")')

# Fix 2: Text input handler for public mode settings (_handle_awaiting_public__10).
# The state is passed down as `adm_pub_p_nam`, but the handler expects `bot_name`.
# In my previous script, I modified `data.replace("adm_pub_p_", "")` to map it to the correct field name using `field_map = {"nam": "bot_name", ...}`.
# BUT I did that when *setting* the state! So the state saved in the database is `awaiting_public_bot_name`.
# If the state saved is `awaiting_public_bot_name`, the handler checks `if field == "bot_name"`, so it should work!
# Let's check `fix_final7.py`:
# `field = field_map.get(...)`
# `await set_admin_state(user_id, {"state": f"awaiting_public_{field}"})`
# Wait, if `state` is `awaiting_public_bot_name`, the prefix in `ADMIN_TEXT_ROUTERS` is `awaiting_public_`.
# The handler extracts `field = state.replace("awaiting_public_", "")` -> `bot_name`.
# Why did the reviewer say "The state passed down is `adm_pub_p_nam`, but the handler expects `bot_name`"?
# Oh! The reviewer said `adm_pub_p_nam` IS the state passed down.
# Let's check the code for `admin_pub_callback`.
# Ah! In my `fix_final.py` (or earlier), I replaced `prompt_public_` with `adm_pub_p_` EVERYWHERE, including the text handler prefix!
# Wait, let's look at `ADMIN_TEXT_ROUTERS`. Is the prefix `adm_pub_p_` or `awaiting_public_`?
# In `ADMIN_TEXT_ROUTERS` it's `awaiting_public_`.
# What does the code in `admin_pub_callback` actually do?
content = content.replace(
    'field_map = {"nam": "bot_name", "com": "community_name", "con": "support_contact", "gleg": "global_daily_egress"}\n        field = field_map.get(data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_"), data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_"))\n        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})',
    'field_map = {"nam": "bot_name", "com": "community_name", "con": "support_contact", "gleg": "global_daily_egress"}\n        field = field_map.get(data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_"), data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_"))\n        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})'
)
# The above replacement doesn't change anything, it just shows what I did.
# Wait, the reviewer says "The state passed down is `adm_pub_p_nam`".
# Let's check `plugins/admin.py` for how the state is set.
