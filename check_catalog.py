import requests

# Check NVIDIA catalog
r = requests.get('http://localhost:47822/api/catalogue/nvidia', timeout=10)
data = r.json()
print('=== NVIDIA Models ===')
print(data)