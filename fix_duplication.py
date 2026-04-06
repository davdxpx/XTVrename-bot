import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Instead of splitting `admin_pub_callback` and duplicating its body 3 times with different decorators,
# we should just revert that and use a single decorator that catches all of them for that specific block of logic.
# The original logic under `if Config.PUBLIC_MODE and (data.startswith("adm_pub_") or ...)`
# perfectly handles all of them. We just need to make sure the decorator catches them all!

# Let's find the 3 duplicated functions
fs_match = re.search(r'# === FORCE SUB MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^adm_fs_"\)\)\nasync def admin_fs_callback\(client, callback_query\):\n(.*?)\n# === FREE PLAN MODULE ===', content, re.DOTALL)
pln_free_match = re.search(r'# === FREE PLAN MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^\(adm_pln_free_\|adm_pln_p_\)"\)\)\nasync def admin_pln_free_callback\(client, callback_query\):\n(.*?)\n# === TEMPLATES MODULE ===', content, re.DOTALL)

if fs_match and pln_free_match:
    # Remove them
    content = content.replace(fs_match.group(0), "")
    content = content.replace(pln_free_match.group(0), "\n# === TEMPLATES MODULE ===")

    # Update the admin_pub_callback decorator to catch them all
    content = re.sub(
        r'@Client\.on_callback_query\(filters\.regex\(r"\^adm_pub_"\)\)\nasync def admin_pub_callback',
        r'@Client.on_callback_query(filters.regex(r"^(adm_pub_|adm_fs_|adm_pln_free_|adm_pln_p_)"))\nasync def admin_pub_callback',
        content
    )

with open('plugins/admin.py', 'w') as f:
    f.write(content)
