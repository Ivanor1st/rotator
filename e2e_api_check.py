from fastapi.testclient import TestClient
import json
import sys

from main import app


def pretty(obj):
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return str(obj)


with TestClient(app) as client:
    print('-> GET /api/config/keys')
    r = client.get('/api/config/keys')
    print(r.status_code)
    print(pretty(r.json()))

    print('\n-> POST /api/config/keys/test (invalid sample)')
    r2 = client.post('/api/config/keys/test', json={'provider': 'openrouter', 'value': 'invalid_sample_key'})
    print(r2.status_code)
    print(pretty(r2.json()))

    print('\n-> POST /api/reload-config')
    r3 = client.post('/api/reload-config')
    print(r3.status_code)
    try:
        print(pretty(r3.json()))
    except Exception:
        print(r3.text)

print('\nDone')
