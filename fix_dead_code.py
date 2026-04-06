import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Delete the duplicated and dead admin_pln_free_callback
pln_free_match = re.search(r'# === FREE PLAN MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^\(adm_pln_free_\|adm_pln_p_\)"\)\)\nasync def admin_pln_free_callback\(client, callback_query\):\n    await callback_query\.answer\(\)\n(.*?)\n# === TEMPLATES MODULE ===', content, re.DOTALL)
if pln_free_match:
    content = content.replace(pln_free_match.group(0), "\n# === TEMPLATES MODULE ===")

with open('plugins/admin.py', 'w') as f:
    f.write(content)
