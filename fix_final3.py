import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

content = content.replace("state_obj)ADMIN_TEXT_ROUTERS", "state_obj)\n\nADMIN_TEXT_ROUTERS")

with open('plugins/admin.py', 'w') as f:
    f.write(content)
