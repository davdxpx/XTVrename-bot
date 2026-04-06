import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# It looks like there are TWO instances of public settings (one in `admin_pln_free_callback` because of duplication)
# Let's fix both
search_str2 = """        field = data.replace(
            "adm_pub_p_",
            "").replace(
            "daily_",
            "daily_")
        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})"""

replace_str = """        field_map = {"nam": "bot_name", "com": "community_name", "con": "support_contact", "gleg": "global_daily_egress"}
        raw_field = data.replace("adm_pub_p_", "").replace("adm_pln_p_", "daily_")
        field = field_map.get(raw_field, raw_field)
        await set_admin_state(user_id, {"state": f"awaiting_public_{field}", "msg_id": callback_query.message.id})"""

content = content.replace(search_str2, replace_str)

# Template field maps
# admin_tpl_callback
content = content.replace(
    'field = data.split("_")[-1]\n        templates = await db.get_all_templates()',
    'field_map = {"tit": "title", "aut": "author", "art": "artist", "vid": "video", "aud": "audio", "sub": "subtitle"}\n        field = field_map.get(data.split("_")[-1], data.split("_")[-1])\n        templates = await db.get_all_templates()'
)
content = content.replace(
    'field = state.replace("adm_tpl_pt_", "")\n    new_template = message.text',
    'field_map = {"tit": "title", "aut": "author", "art": "artist", "vid": "video", "aud": "audio", "sub": "subtitle"}\n    field = field_map.get(state.replace("adm_tpl_pt_", ""), state.replace("adm_tpl_pt_", ""))\n    new_template = message.text'
)
content = content.replace(
    'field = state.split("_")[-1]\n    new_template = message.text',
    'field_map = {"tit": "title", "aut": "author", "art": "artist", "vid": "video", "aud": "audio", "sub": "subtitle"}\n    field = field_map.get(state.split("_")[-1], state.split("_")[-1])\n    new_template = message.text'
)
# Filename templates
content = content.replace(
    'field = data.replace("adm_fn_", "")\n        templates = await db.get_filename_templates()',
    'field_map = {"mov": "movies", "ser": "series", "p_fil": "personal_file", "p_pho": "personal_photo", "p_vid": "personal_video", "s_mov": "subtitles_movies", "s_ser": "subtitles_series"}\n        field = field_map.get(data.replace("adm_fn_", ""), data.replace("adm_fn_", ""))\n        templates = await db.get_filename_templates()'
)
content = content.replace(
    'field = state.replace("awaiting_fn_template_", "")\n    new_template = message.text',
    'field_map = {"mov": "movies", "ser": "series", "p_fil": "personal_file", "p_pho": "personal_photo", "p_vid": "personal_video", "s_mov": "subtitles_movies", "s_ser": "subtitles_series"}\n    field = field_map.get(state.replace("awaiting_fn_template_", ""), state.replace("awaiting_fn_template_", ""))\n    new_template = message.text'
)

with open('plugins/admin.py', 'w') as f:
    f.write(content)
