import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

router_start = content.find("ADMIN_TEXT_ROUTERS = {")
router_end = content.find("}", router_start)
routers_text = content[router_start:router_end]

keys = re.findall(r'"([^"]+)":', routers_text)
if len(keys) != len(set(keys)):
    print("Duplicates:", [k for k in set(keys) if keys.count(k) > 1])
else:
    print("No duplicates in actual ADMIN_TEXT_ROUTERS")
