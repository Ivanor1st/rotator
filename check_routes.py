import re

with open(r'D:\Project\rotator\main.py', 'r', encoding='utf-8') as f:
    c = f.read()

m = re.findall(r'@app\.(post|get)\("([^"]+)', c)
for route in m:
    if 'v1beta' in route[1]:
        print(route)