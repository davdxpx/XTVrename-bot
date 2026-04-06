import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

# Find all remaining un-shortened `data == "..."` or `data.startswith("...")`
matches = re.findall(r'data (?:==|!=|\.startswith\()[\'"]([^\'"]+)[\'"]\)?', content)

long_callbacks = []
for m in matches:
    if len(m) > 12 and not m.startswith('adm_'):
        long_callbacks.append(m)

print("Remaining potentially long callbacks:", set(long_callbacks))
