import time
import sys
import yaml
import httpx


def load_port():
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
            return cfg.get('settings', {}).get('port', 47822)
    except Exception:
        return 47822


def poll_ping(url=None, timeout=20):
    if url is None:
        port = load_port()
        url = f'http://localhost:{port}/api/ping'
    for i in range(timeout):
        try:
            r = httpx.get(url, timeout=2.0)
            print('PING', r.status_code, r.text[:200])
            return 0
        except Exception:
            print('wait', i+1)
            time.sleep(1)
    print('timeout')
    return 2


def check_models(url=None):
    if url is None:
        port = load_port()
        url = f'http://localhost:{port}/v1/models'
    try:
        r = httpx.get(url, timeout=5.0)
        print('/v1/models', r.status_code)
        data = r.json()
        ids = [d['id'] for d in data.get('data', [])]
        print('models:', ids)
        return 0
    except Exception as e:
        print('models check failed', e)
        return 3


if __name__ == '__main__':
    code = poll_ping()
    if code == 0:
        code = check_models()
    sys.exit(code)
