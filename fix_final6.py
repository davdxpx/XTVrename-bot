import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix 1: The remaining un-replaced conditional checks!
# Example 1: `set_admin_workflow_` vs `adm_gen_wf_`
content = content.replace('data.startswith("set_admin_workflow_")', 'data.startswith("adm_gen_wf_")')
content = content.replace('data.endswith("smart")', 'data.endswith("smt")')

# Example 2: `dumb_` vs `adm_dmb_`
content = content.replace('data.startswith("dumb_")', 'data.startswith("adm_dmb_")')
# Wait, let's fix `data.startswith("adm_dmb_"): if data.startswith("adm_dmb_menu"):`
# Actually, the original was `if data.startswith("dumb_"): if data.startswith("dumb_menu"):`
# So changing it to `if data.startswith("adm_dmb_"): if data.startswith("adm_dmb_mnu"):` is fine, but I replaced `dumb_menu` with `adm_dmb_mnu`.
content = content.replace('data.startswith("adm_dmb_menu")', 'data.startswith("adm_dmb_mnu")')
content = content.replace('data.replace("adm_dmb_menu"', 'data.replace("adm_dmb_mnu"')

# Example 3: `edit_template_` vs `adm_tpl_ed_`
content = content.replace('data.startswith("edit_template_")', 'data.startswith("adm_tpl_ed_")')
content = content.replace('data.split("_")[-1]', 'data.split("_")[-1]') # This extracts the field
# Wait, if data is `adm_tpl_ed_title`, `split("_")[-1]` gives `title`. That works!

# Example 4: `prompt_admin_thumb_set` vs `adm_thm_p_set`
content = content.replace('data == "prompt_admin_thumb_set"', 'data == "adm_thm_p_set"')

# Example 5: Duplicate code blocks. I attempted to revert them but let's just make sure there is no `admin_pln_free_callback` anymore.
pln_free_match = re.search(r'# === FREE PLAN MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^\(adm_pln_free_\|adm_pln_p_\)"\)\)\nasync def admin_pln_free_callback\(client, callback_query\):\n(.*?)\n# === TEMPLATES MODULE ===', content, re.DOTALL)
if pln_free_match:
    content = content.replace(pln_free_match.group(0), "\n# === TEMPLATES MODULE ===")

fs_match = re.search(r'# === FORCE SUB MODULE ===\n@Client\.on_callback_query\(filters\.regex\(r"\^adm_fs_"\)\)\nasync def admin_fs_callback\(client, callback_query\):\n(.*?)\n# === FREE PLAN MODULE ===', content, re.DOTALL)
if fs_match:
    content = content.replace(fs_match.group(0), "")

# Ensure the decorator for admin_pub_callback catches them all
content = re.sub(
    r'@Client\.on_callback_query\(filters\.regex\(r"\^adm_pub_"\)\)\nasync def admin_pub_callback',
    r'@Client.on_callback_query(filters.regex(r"^(adm_pub_|adm_fs_|adm_pln_free_|adm_pln_p_)"))\nasync def admin_pub_callback',
    content
)

with open('plugins/admin.py', 'w') as f:
    f.write(content)
