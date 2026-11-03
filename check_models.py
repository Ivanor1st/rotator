import requests
try:
    r = requests.get('http://localhost:47822/v1/models', timeout=5)
    data = r.json()
    for model in data.get('data', []):
        profiles = model.get('profiles', [])
        if 'vision' in profiles:
            print(f'Vision model: {model["id"]} - provider: {model.get("owned_by", "unknown")} - profiles: {profiles}')
except Exception as e:
    print('Error:', e)