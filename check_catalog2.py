import requests

# Check OpenRouter catalog
r = requests.get('http://localhost:47822/api/catalogue/openrouter', timeout=10)
data = r.json()
print('=== OpenRouter Vision Models ===')
for m in data.get('models', []):
    if 'vision' in m.get('name', '').lower() or 'vl' in m.get('name', '').lower() or 'nemotron' in m.get('name', '').lower():
        print(f'  {m["name"]} - {m.get("description", "")}')