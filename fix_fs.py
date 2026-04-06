import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix 1: Create admin_fs_callback and extract its body from admin_pub_callback
# I'll just change the decorators to be catch-alls for their specific domains and fix the missing `admin_fs_callback`
# by mapping it to `admin_pub_callback` inside the dispatcher. Wait, no, it's better to split them, but since they share
# the `if Config.PUBLIC_MODE` wrapper, I'll just change the regex for `admin_pub_callback` to catch both,
# and remove the separate `admin_fs_callback` from the main router.
# Wait, let's look at `admin_pub_callback`'s decorator.
content = re.sub(
    r'@Client\.on_callback_query\(filters\.regex\(r"\^adm_pub_"\)\)\nasync def admin_pub_callback\(client, callback_query\):',
    r'@Client.on_callback_query(filters.regex(r"^(adm_pub_|adm_fs_|adm_pln_free_)"))\nasync def admin_pub_callback(client, callback_query):',
    content
)
# Update the master dispatcher to route correctly
content = content.replace('        await admin_fs_callback(client, callback_query)', '        await admin_pub_callback(client, callback_query)')
content = content.replace('    elif data.startswith("adm_pln_free_eg") or data.startswith("adm_pln_free_fl"):', '')
content = content.replace('    elif data.startswith("adm_fs_"):', '    elif data.startswith("adm_fs_") or data.startswith("adm_pln_free_"):')

# Fix 2: Duplicate key "awaiting_premium_" in ADMIN_TEXT_ROUTERS
# Let's inspect ADMIN_TEXT_ROUTERS in the file.
