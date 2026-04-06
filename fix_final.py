import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix 1: Move ADMIN_TEXT_ROUTERS dictionary to the bottom of the file
router_start = content.find("ADMIN_TEXT_ROUTERS = {")
router_end = content.find("}", router_start) + 1
router_dict_code = content[router_start:router_end]
content = content[:router_start] + content[router_end:]

# Insert it right before `handle_admin_text`
handle_admin_text_idx = content.find("async def handle_admin_text(client, message):")
content = content[:handle_admin_text_idx] + router_dict_code + "\n\n" + content[handle_admin_text_idx:]

# Fix 2: Unentangle adm_fs_ callbacks into their proper dedicated handler
# I will create `admin_fs_callback` and copy the fs logic from `admin_pub_callback`.
# Actually, looking at the code, in `admin_pub_callback`, there is an `if Config.PUBLIC_MODE` wrapper.
# Let's extract the `adm_fs_` logic and `adm_pln_free_` logic into `admin_fs_callback` and `admin_pln_free_callback`.
