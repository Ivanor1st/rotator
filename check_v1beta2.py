with open(r'D:\Project\rotator\main.py', 'r', encoding='utf-8') as f:
    c = f.read()
idx = c.find('@app.post("/v1beta')
with open('check_v1beta2.txt', 'w', encoding='utf-8') as f:
    f.write(c[idx:idx+2000] if idx != -1 else 'NOT FOUND')