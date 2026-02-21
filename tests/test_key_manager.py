from key_manager import KeyManager
from router import RouteTarget


def test_key_selection_prefers_low_usage():
    config = {
        "keys": {
            "nvidia": [
                {"label": "k1", "key": "a"},
                {"label": "k2", "key": "b"},
            ]
        }
    }
    km = KeyManager(config, daily_quota_map={})
    target = RouteTarget("nvidia", "minimaxai/minimax-m2.1", "rpm")
    key = km.choose_key_for_target(target)
    assert key is not None
    assert key.provider == "nvidia"
