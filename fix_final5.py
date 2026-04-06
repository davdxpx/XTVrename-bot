import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

content = content.replace('    elif data.startswith("adm_fs_"):\n\n', '')

with open('plugins/admin.py', 'w') as f:
    f.write(content)
