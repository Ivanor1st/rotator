from key_manager import KeyManager
from router import RouteTarget
from constants import Provider


def test_key_selection_prefers_low_usage():
    config = {
        "keys": {
            Provider.NVIDIA.value: [
                {"label": "k1", "key": "a"},
                {"label": "k2", "key": "b"},
            ]
        }
    }
    km = KeyManager(config, daily_quota_map={})
    target = RouteTarget(Provider.NVIDIA.value, "minimaxai/minimax-m2.1", "rpm")
    key = km.choose_key_for_target(target)
    assert key is not None
    assert key.provider == Provider.NVIDIA.value
