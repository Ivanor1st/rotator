import re

with open(r'D:\Project\rotator\main.py', 'r', encoding='utf-8') as f:
    c = f.read()

matches = re.findall(r'@app\.(post|get)\("([^"]+)', c)
for m in matches:
    if 'v1beta' in m[1] or 'generate' in m[1] or 'stream' in m[1] or 'count' in m[1]:
        print(m)