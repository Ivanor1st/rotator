with open(r'D:\Project\rotator\main.py', 'r', encoding='utf-8') as f:
    c = f.read()
idx = c.find('@app.post("/v1beta/models/{model}/countTokens")')
with open('check_count.txt', 'w', encoding='utf-8') as f:
    f.write(c[idx:idx+300] if idx != -1 else 'NOT FOUND')