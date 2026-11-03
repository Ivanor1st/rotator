import requests
import json
import base64

# Test Ollama Cloud vision with a simple image
url = "http://localhost:47822/v1/chat/completions"
headers = {"Content-Type": "application/json", "Authorization": "Bearer rotator"}

# Use a simple test image URL
payload = {
    "model": "gemma4:31b:cloud",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image? Reply in one word."},
                {"type": "image_url", "image_url": {"url": "https://picsum.photos/200/200"}}
            ]
        }
    ],
    "max_tokens": 50
}

print("Testing Ollama Cloud gemma4:31b:cloud with image...")
try:
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test OpenRouter vision with nemotron-3.5-super-vl:free
payload2 = {
    "model": "nvidia/nemotron-3.5-super-vl:free",
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image? Reply in one word."},
                {"type": "image_url", "image_url": {"url": "https://picsum.photos/200/200"}}
            ]
        }
    ],
    "max_tokens": 50
}

print("\n\nTesting OpenRouter nvidia/nemotron-3.5-super-vl:free with image...")
try:
    r = requests.post(url, headers=headers, json=payload2, timeout=60)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")