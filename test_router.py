import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Verify no duplicate keys in ADMIN_TEXT_ROUTERS
routers = re.findall(r'"([^"]+)": ([^,]+),', content)
keys = [r[0] for r in routers]
if len(keys) != len(set(keys)):
    print(f"Duplicate keys found! {keys}")
else:
    print("No duplicate keys in ADMIN_TEXT_ROUTERS.")
