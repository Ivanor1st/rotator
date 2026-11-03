import os

# Check environment variables for each provider
providers = ['ollama_cloud', 'nvidia', 'openrouter', 'google']
for p in providers:
    env_var = f'{p.upper().replace(".", "_").replace("-", "_")}_API_KEY'
    # Also check common variants
    variants = [
        f'{p.upper().replace(".", "_").replace("-", "_")}_API_KEY',
        f'{p.upper().replace(".", "_").replace("-", "_")}_KEY',
        f'{p.upper()}_API_KEY',
        f'{p.upper()}_KEY'
    ]
    for v in variants:
        val = os.environ.get(v)
        if val:
            print(f'{p}: {v} = {val[:20]}...')
            break
    else:
        print(f'{p}: NO KEY FOUND (checked: {variants})')

# Also check config.yaml keys
print("\n--- Config.yaml keys ---")
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

for provider, keys in config.get('keys', {}).items():
    print(f"\nProvider: {provider}")
    for i, k in enumerate(keys):
        if 'token' in k:
            val = k['token']
            if val.startswith('env:'):
                env_name = val[4:]
                val_actual = os.environ.get(env_name)
                if val_actual:
                    print(f"  Key {i+1}: {env_name} = {val_actual[:20]}...")
                else:
                    print(f"  Key {i+1}: {env_name} = NOT SET")
            else:
                print(f"  Key {i+1}: {k}")
        elif 'key' in k:
            val = k['key']
            if val.startswith('env:'):
                env_name = val[4:]
                val_actual = os.environ.get(env_name)
                if val_actual:
                    print(f"  Key {i+1}: {env_name} = {val_actual[:20]}...")
                else:
                    print(f"  Key {i+1}: {env_name} = NOT SET")
            else:
                print(f"  Key {i+1}: {k}")