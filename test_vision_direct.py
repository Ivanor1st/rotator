import requests

# Test a direct vision request to see what error we get
import json

url = "http://localhost:47822/v1/chat/completions"
headers = {"Content-Type": "application/json", "Authorization": "Bearer rotator"}
payload = {
    "model": "vision",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": "https://picsum.photos/200/300"}}
            ]
        }
    ],
    "max_tokens": 100
}

r = requests.post(url, headers=headers, json=payload, timeout=30)
print(f"Status: {r.status_code}")
print(f"Response: {r.text}")