import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Fix 1: Missing Callback Logic (prompt_myfiles_db_, adm_pub_p_nam, etc)
# Let's run the replacement for prompt_myfiles_db_ that I clearly missed earlier.
content = content.replace('data.startswith("prompt_myfiles_db_")', 'data.startswith("adm_myf_db_")')
content = content.replace('data.replace("prompt_myfiles_db_", "")', 'data.replace("adm_myf_db_", "")')

content = content.replace('data.startswith("prompt_public_")', 'data.startswith("adm_pub_p_")')
content = content.replace('data.startswith("prompt_daily_")', 'data.startswith("adm_pln_p_")')
content = content.replace('data.replace("prompt_public_", "")', 'data.replace("adm_pub_p_", "")')
content = content.replace('data.replace("prompt_daily_", "daily_")', 'data.replace("adm_pln_p_", "daily_")')

content = content.replace('data.startswith("dumb_del_")', 'data.startswith("adm_dmb_del_")')
content = content.replace('data.replace("dumb_del_", "")', 'data.replace("adm_dmb_del_", "")')

content = content.replace('data.startswith("prompt_myfiles_lim_")', 'data.startswith("adm_myf_l_")')
content = content.replace('data.replace("prompt_myfiles_lim_", "")', 'data.replace("adm_myf_l_", "")')

# Fix 2: NameError (admin_fs_callback deleted but still called in dispatcher)
# In my last script I deleted `admin_fs_callback` and `admin_pln_free_callback`, and modified `admin_pub_callback` decorator.
# Since I am using a manual dispatcher inside `admin_callback`, I need to update the dispatcher to not call them!
content = content.replace('elif data.startswith("adm_fs_") or data.startswith("adm_pln_free_"):', '')
content = content.replace('        await admin_fs_callback(client, callback_query)', '')
# Route them to admin_pub_callback instead
content = content.replace('    elif data.startswith("adm_pub_"):', '    elif data.startswith("adm_pub_") or data.startswith("adm_fs_") or data.startswith("adm_pln_free_") or data.startswith("adm_pln_p_"):')

# Fix 3: Swallowed Callbacks (adm_pln_ intercepts adm_pln_free_)
# Wait, `admin_pln_callback` is registered with `^adm_pln_`, which intercepts EVERYTHING starting with `adm_pln_`.
# Including `adm_pln_free_` and `adm_pln_p_` which I just routed to `admin_pub_callback`.
# The best way is to let `admin_pln_callback` handle ALL of `adm_pln_`!
# BUT the logic for `adm_pln_free_eg` etc. was stuffed inside `admin_pub_callback` because they were originally under `if Config.PUBLIC_MODE:` block.
# Actually, the entire Plans & Limits is under `Config.PUBLIC_MODE`.
# Rather than fighting the decorators, the simplest solution is to change `admin_pln_callback` decorator to be explicit,
# OR just move the logic from `admin_pub_callback` into `admin_pln_callback`.
# Let's change the decorator for `admin_pln_callback` to exclude the free/p callbacks, OR just route them properly.
# The issue is the `Client.on_callback_query` decorator.
# `admin_pln_callback` regex: `^adm_pln_(?!free_|p_)`
content = content.replace(
    '@Client.on_callback_query(filters.regex(r"^adm_pln_"))\nasync def admin_pln_callback(client, callback_query):',
    '@Client.on_callback_query(filters.regex(r"^adm_pln_(?!free_|p_)"))\nasync def admin_pln_callback(client, callback_query):'
)

# And `admin_pub_callback` regex: `^(adm_pub_|adm_fs_|adm_pln_free_|adm_pln_p_)`
# This is already what I set it to in the previous script.

# Fix 4: IndexError Crash (adm_tpl_s_us split by _set_sep_)
content = content.replace('data.split("_set_sep_")[1]', 'data.split("adm_tpl_s_")[1]')


with open('plugins/admin.py', 'w') as f:
    f.write(content)
