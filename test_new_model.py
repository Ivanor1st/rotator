import requests
import json
import base64

# Download a test image and encode as base64
img_url = 'https://picsum.photos/200/200'
img_resp = requests.get(img_url, timeout=10)
img_b64 = base64.b64encode(img_resp.content).decode('utf-8')
data_url = f'data:image/jpeg;base64,{img_b64}'

url = 'http://localhost:47822/v1/chat/completions'
headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer rotator'}

# Test the new model
payload = {
    'model': 'nvidia/nemotron-3.5-super-vl:free',
    'messages': [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': "What's in this image? Reply in one word."},
                {'type': 'image_url', 'image_url': {'url': data_url}}
            ]
        }
    ],
    'max_tokens': 50
}

print("Testing OpenRouter nvidia/nemotron-3.5-super-vl:free with base64 image...")
try:
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:1000]}")
except Exception as e:
    print(f"Error: {e}")