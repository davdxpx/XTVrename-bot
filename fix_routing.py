import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix 1: Move ADMIN_TEXT_ROUTERS exactly above handle_admin_text
router_start = content.find("ADMIN_TEXT_ROUTERS = {")
router_end = content.find("}", router_start) + 1
router_dict_code = content[router_start:router_end]
content = content[:router_start] + content[router_end:]

handle_admin_text_idx = content.find("@Client.on_message(\n    (filters.text | filters.forwarded) & filters.private")
content = content[:handle_admin_text_idx] + "\n" + router_dict_code + "\n\n" + content[handle_admin_text_idx:]

# Fix 2: Catch-all admin_misc_callback swallows callbacks
content = content.replace(
"""# === MISC/UNKNOWN MODULE ===
@Client.on_callback_query(filters.regex(r"^adm_"))
async def admin_misc_callback(client, callback_query):""",
"""# === MISC/UNKNOWN MODULE ===
@Client.on_callback_query(filters.regex(r"^(adm_del_msg|adm_cancel)"))
async def admin_misc_callback(client, callback_query):"""
)

# Fix 3: Missing admin_fs_callback and admin_pln_free_callback definitions.
# The reviewer said the logic for Force-Sub (`adm_fs_`) and Free Plan Limits (`adm_pln_free_`)
# was stuffed inside `admin_pub_callback`.
# We need to extract that logic into its own handlers.

pub_cb_match = re.search(r'# === PUBLIC CONFIG MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^\(adm_pub_\|adm_fs_\|adm_pln_free_\)"\)\)\nasync def admin_pub_callback\(client, callback_query\):\n(.*?)\n# === TEMPLATES MODULE ===', content, re.DOTALL)

if pub_cb_match:
    pub_body = pub_cb_match.group(1)

    fs_cb = f"""
# === FORCE SUB MODULE ===
@Client.on_callback_query(filters.regex(r"^adm_fs_"))
async def admin_fs_callback(client, callback_query):
{pub_body}
"""
    pln_free_cb = f"""
# === FREE PLAN MODULE ===
@Client.on_callback_query(filters.regex(r"^(adm_pln_free_|adm_pln_p_)"))
async def admin_pln_free_callback(client, callback_query):
{pub_body}
"""

    content = content.replace(pub_cb_match.group(0), "# === PUBLIC CONFIG MODULE ===\n@Client.on_callback_query(filters.regex(r\"^adm_pub_\"))\nasync def admin_pub_callback(client, callback_query):\n" + pub_body + "\n" + fs_cb + pln_free_cb + "\n# === TEMPLATES MODULE ===")
else:
    # try the old regex
    pub_cb_match = re.search(r'# === PUBLIC CONFIG MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^adm_pub_"\)\)\nasync def admin_pub_callback\(client, callback_query\):\n(.*?)\n# === TEMPLATES MODULE ===', content, re.DOTALL)
    if pub_cb_match:
        pub_body = pub_cb_match.group(1)
        fs_cb = f"""
# === FORCE SUB MODULE ===
@Client.on_callback_query(filters.regex(r"^adm_fs_"))
async def admin_fs_callback(client, callback_query):
{pub_body}
"""
        pln_free_cb = f"""
# === FREE PLAN MODULE ===
@Client.on_callback_query(filters.regex(r"^(adm_pln_free_|adm_pln_p_)"))
async def admin_pln_free_callback(client, callback_query):
{pub_body}
"""
        content = content.replace(pub_cb_match.group(0), "# === PUBLIC CONFIG MODULE ===\n@Client.on_callback_query(filters.regex(r\"^adm_pub_\"))\nasync def admin_pub_callback(client, callback_query):\n" + pub_body + "\n" + fs_cb + pln_free_cb + "\n# === TEMPLATES MODULE ===")

with open('plugins/admin.py', 'w') as f:
    f.write(content)
