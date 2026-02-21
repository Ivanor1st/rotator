from router import detect_profile


def test_detect_profile_keywords():
    payload = {"messages": [{"role": "user", "content": "Please fix this bug"}]}
    assert detect_profile(payload) == "coding"


def test_detect_profile_reasoning():
    payload = {"messages": [{"role": "user", "content": "Explain why 2+2=4"}]}
    assert detect_profile(payload) == "reasoning"


def test_detect_profile_default_chat():
    payload = {"messages": [{"role": "user", "content": "Hello there"}]}
    assert detect_profile(payload) == "chat"
