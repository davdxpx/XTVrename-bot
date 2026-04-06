import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix 1: Missing `await callback_query.answer()` at the top of EVERY domain handler.
# The original monolith had it. We need to add it to the top of all our `async def admin_*_callback` functions.

def add_answer(match):
    func_sig = match.group(0)
    return func_sig + "\n    await callback_query.answer()\n"

content = re.sub(r'async def admin_[a-z]+_callback\(client, callback_query\):', add_answer, content)
# But wait, `admin_misc_callback` shouldn't necessarily answer if it's falling through? No, all valid callbacks must be answered.
# `admin_callback` (the manual dispatcher) does NOT need it because it just routes.
content = content.replace("async def admin_callback(client, callback_query):\n    await callback_query.answer()\n", "async def admin_callback(client, callback_query):\n")

# Fix 2: State Machine String Corruption (e.g. `adm_tpl_ed_tit` saving "tit" instead of "title").
# I should just revert the shortened callbacks that represent database keys!
# The user wants "only the ones explicitly dealing with deep nesting / variable lengths" shortened?
# Wait, they said: "Please systematically update ALL callback data strings in admin.py to use a smaller, consistent footprint."
# If I shorten them, I MUST map them back to the correct DB keys in the handlers.
# Example: `field = data.split("_")[-1]` -> "tit", "aut", "art", "vid", "aud", "sub" -> "title", "author", "artist", "video", "audio", "subtitle".
# Same for `prompt_public_` -> `adm_pub_p_nam`, `adm_pub_p_com`, `adm_pub_p_con` -> "bot_name", "community_name", "support_contact".

# Let's map them back in the handlers by replacing the `field` assignment logic.
# For templates:
content = content.replace(
    'field = data.split("_")[-1]\n        templates = await db.get_all_templates()',
    'field_map = {"tit": "title", "aut": "author", "art": "artist", "vid": "video", "aud": "audio", "sub": "subtitle"}\n        field = field_map.get(data.split("_")[-1], data.split("_")[-1])\n        templates = await db.get_all_templates()'
)
content = content.replace(
    'field = state.replace("adm_tpl_pt_", "")\n    new_template = message.text',
    'field_map = {"tit": "title", "aut": "author", "art": "artist", "vid": "video", "aud": "audio", "sub": "subtitle"}\n    field = field_map.get(state.replace("adm_tpl_pt_", ""), state.replace("adm_tpl_pt_", ""))\n    new_template = message.text'
)

# For filename templates (mov, ser, per, sub, p_fil, p_pho, p_vid, s_mov, s_ser):
content = content.replace(
    'field = data.replace("adm_fn_", "")\n        templates = await db.get_filename_templates()',
    'field_map = {"mov": "movies", "ser": "series", "p_fil": "personal_file", "p_pho": "personal_photo", "p_vid": "personal_video", "s_mov": "subtitles_movies", "s_ser": "subtitles_series"}\n        field = field_map.get(data.replace("adm_fn_", ""), data.replace("adm_fn_", ""))\n        templates = await db.get_filename_templates()'
)
content = content.replace(
    'field = state.replace("awaiting_fn_template_", "")\n    new_template = message.text',
    'field_map = {"mov": "movies", "ser": "series", "p_fil": "personal_file", "p_pho": "personal_photo", "p_vid": "personal_video", "s_mov": "subtitles_movies", "s_ser": "subtitles_series"}\n    field = field_map.get(state.replace("awaiting_fn_template_", ""), state.replace("awaiting_fn_template_", ""))\n    new_template = message.text'
)
# Note: we need to make sure the state generation sends `awaiting_fn_template_mov` instead of `awaiting_fn_template_movies`
# Wait, `admin_fn_pt_mov` creates `awaiting_fn_template_mov`. Yes.

# For public settings (nam, com, con):
content = content.replace(
    'field = data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_")\n        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})',
    'field_map = {"nam": "bot_name", "com": "community_name", "con": "support_contact", "gleg": "global_daily_egress"}\n        field = field_map.get(data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_"), data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_"))\n        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})'
)

# Fix 3: String Splitting Errors (`adm_pln_tf_file_converter` -> `rsplit("_", 1)`)
# I used `adm_pln_tf_file_converter_free` or `adm_pln_tf_file_converter_standard`.
# In my `dry_features.py`, I generated `callback_data=f"adm_pln_tf_{key}_{plan_name}"`. So it's `adm_pln_tf_file_converter_free`.
# The parse code is `parts = data.replace("adm_pln_tf_", "").rsplit("_", 1)`.
# This perfectly splits `file_converter_free` into `["file_converter", "free"]`!
# Wait, the reviewer said "incorrectly parses the feature as 'file' and the plan name as 'converter'".
# Oh! `rsplit("_", 1)` splits from the right ONCE.
# "file_converter_free" -> `["file_converter", "free"]`. This IS correct.
# Wait, did I generate `adm_pln_tf_free_file_converter`? Let's check `dry_features.py` output.
# I generated `adm_pln_tf_{key}_{plan_name}`. For free: `adm_pln_tf_file_converter_free`. `rsplit("_", 1)` -> `["file_converter", "free"]`.
# BUT for premium: `adm_pln_pf_{plan_name}_{key}` -> `adm_pln_pf_standard_file_converter`.
# The premium parser is `data.replace("adm_pln_pf_", "").split("_", 1)`.
# `standard_file_converter` -> `split("_", 1)` -> `["standard", "file_converter"]`. This is ALSO correct.
# Why did the reviewer complain?
# Maybe the original code had `admin_toggle_file_converter` without a plan name!
# If it's just `adm_pln_tf_file_converter`, then `rsplit("_", 1)` splits it into `["file", "converter"]`!
# Ah! For `admin_toggle_file_converter` (from `admin_feature_toggles`), I generated `adm_pln_tf_file_converter`.
# Let's fix that specific handler to check if there is a plan name or not.
content = content.replace(
    'parts = data.replace("adm_pln_tf_", "").rsplit("_", 1)\n        feature = parts[0]\n        plan_name = parts[1] if len(parts) > 1 else "free"',
    'parts = data.replace("adm_pln_tf_", "").rsplit("_", 1)\n        if parts[-1] in ["free", "standard", "deluxe"]:\n            feature = parts[0]\n            plan_name = parts[1]\n        else:\n            feature = data.replace("adm_pln_tf_", "")\n            plan_name = "free"'
)

# Fix 4: External Plugins Broken (`adm_usr_menu` and `adm_broadcast`).
# I need to revert them back to `admin_users_menu` and `admin_broadcast`.
content = content.replace('"adm_usr_menu"', '"admin_users_menu"')
content = content.replace('"adm_broadcast"', '"admin_broadcast"')
content = content.replace('"adm_usr_look"', '"prompt_user_lookup"')
content = content.replace('"adm_dash_main"', '"admin_usage_dashboard"')
content = content.replace('"adm_dash_dly"', '"admin_dashboard_daily"')
content = content.replace('r\'^adm_usr_blk_(\d+)$\'', 'r\'^admin_block_(\\d+)\'$\'')
content = content.replace('r\'^adm_usr_ublk_(\d+)$\'', 'r\'^admin_unblock_(\\d+)\'$\'')
content = content.replace('r\'^adm_usr_rsq_(\d+)$\'', 'r\'^admin_reset_quota_(\\d+)\'$\'')

# Also need to make sure the main dispatcher forwards them?
# No, external plugins use their own `@Client.on_callback_query(filters.regex("..."))`.
# They won't go through our `admin_callback` unless they have `adm_`.
# Wait, `admin_users_menu` doesn't start with `adm_` so it will fall through our `admin_callback` completely, which is exactly what we want!

# Fix 5: Duplicated massive blocks of code (`admin_pln_free_callback` and `admin_pub_callback`).
# In an earlier fix I tried to delete `admin_pln_free_callback` but messed it up?
# Let's check if `admin_pln_free_callback` still exists and delete it.
pln_free_match = re.search(r'# === FREE PLAN MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^\(adm_pln_free_\|adm_pln_p_\)"\)\)\nasync def admin_pln_free_callback\(client, callback_query\):\n    await callback_query\.answer\(\)\n(.*?)\n# === TEMPLATES MODULE ===', content, re.DOTALL)
if pln_free_match:
    content = content.replace(pln_free_match.group(0), "\n# === TEMPLATES MODULE ===")

fs_match = re.search(r'# === FORCE SUB MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^adm_fs_"\)\)\nasync def admin_fs_callback\(client, callback_query\):\n    await callback_query\.answer\(\)\n(.*?)\n# === FREE PLAN MODULE ===', content, re.DOTALL)
if fs_match:
    content = content.replace(fs_match.group(0), "")

# Fix 6: Placement of ADMIN_TEXT_ROUTERS dictionary
# The reviewer complained it was placed at the very bottom.
# To place it "directly above handle_admin_text" without getting a `NameError` for the async functions inside it,
# I need to move the async functions ABOVE the dictionary, and the dictionary ABOVE `handle_admin_text`.
# Let's move ALL `_handle_*` functions and the `ADMIN_TEXT_ROUTERS` dictionary directly above `handle_admin_text`.

handlers_start = content.find("async def _handle_awaiting_myfiles_db__0")
# The handlers go all the way to `ADMIN_TEXT_ROUTERS = {`
router_end = content.find("}", content.find("ADMIN_TEXT_ROUTERS = {")) + 1
handlers_code = content[handlers_start:router_end]
content = content[:handlers_start] + content[router_end:]

handle_admin_text_idx = content.find("@Client.on_message(\n    (filters.text | filters.forwarded)")
content = content[:handle_admin_text_idx] + handlers_code + "\n\n" + content[handle_admin_text_idx:]

with open('plugins/admin.py', 'w') as f:
    f.write(content)
