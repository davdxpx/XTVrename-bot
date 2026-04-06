import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix 1: Move ADMIN_TEXT_ROUTERS dictionary to the bottom of the file
router_start = content.find("ADMIN_TEXT_ROUTERS = {")
router_end = content.find("}", router_start) + 1
router_dict_code = content[router_start:router_end]
content = content[:router_start] + content[router_end:]

handle_admin_text_idx = content.find("@Client.on_message(\n    (filters.text | filters.forwarded) & filters.private")
content = content[:handle_admin_text_idx] + router_dict_code + "\n\n" + content[handle_admin_text_idx:]

# Fix 2: Unentangle adm_fs_ callbacks into their proper dedicated handler
# I will copy admin_pub_callback entirely into admin_fs_callback and admin_pln_free_callback,
# and just change the decorators. It's safer and ensures all logic is accessible.
pub_cb_match = re.search(r'# === PUBLIC CONFIG MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^adm_pub_"\)\)\nasync def admin_pub_callback\(client, callback_query\):\n(.*?)# === FORCE SUB MODULE ===', content, re.DOTALL)

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
@Client.on_callback_query(filters.regex(r"^adm_pln_free_"))
async def admin_pln_free_callback(client, callback_query):
{pub_body}
"""
    content = content.replace("# === TEMPLATES MODULE ===", fs_cb + pln_free_cb + "# === TEMPLATES MODULE ===")

    # Wait, the pub_body contains everything. It's safe to just reuse it since it filters internally via `if data == ...`.
    # To fix the "admin_fs_callback is not defined" error in the router.

# Fix 3: Fix `admin_cancel` check inside `admin_main_callback`
content = content.replace('if data == "admin_cancel":', 'if data == "adm_cancel":')

with open('plugins/admin.py', 'w') as f:
    f.write(content)
