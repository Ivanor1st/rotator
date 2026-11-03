import requests

# Check Google catalog
r = requests.get('http://localhost:47822/api/catalogue/google', timeout=10)
data = r.json()
print('=== Google Models ===')
for m in data.get('models', []):
    print(f'  {m["name"]} - {m.get("description", "")}')