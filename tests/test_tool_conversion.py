"""Quick validation for the Anthropic ↔ OpenAI tool-call conversions."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import _anthropic_messages_to_openai, _openai_response_to_anthropic


def test_response_with_tool_calls():
    """OpenAI response with tool_calls → Anthropic tool_use content blocks."""
    body = {
        "id": "chatcmpl-123",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Let me read that.",
                "tool_calls": [{
                    "id": "call_xyz",
                    "type": "function",
                    "function": {
                        "name": "Read",
                        "arguments": '{"file_path": "main.py"}',
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 50, "completion_tokens": 30},
    }
    result = _openai_response_to_anthropic(body, "gemini-2.5-flash")
    assert result["stop_reason"] == "tool_use"
    assert len(result["content"]) == 2  # text + tool_use
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "Let me read that."
    assert result["content"][1]["type"] == "tool_use"
    assert result["content"][1]["name"] == "Read"
    assert result["content"][1]["input"] == {"file_path": "main.py"}
    assert result["content"][1]["id"] == "call_xyz"
    print("  response_with_tool_calls OK")


def test_request_tool_use_round_trip():
    """Anthropic tool_use + tool_result → OpenAI tool_calls + tool messages."""
    payload = {
        "model": "test",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "read main.py"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Reading file..."},
                    {"type": "tool_use", "id": "toolu_abc", "name": "Read", "input": {"path": "main.py"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_abc", "content": "file data here"},
                ],
            },
        ],
        "tools": [
            {"name": "Read", "description": "Read a file", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
        ],
        "tool_choice": {"type": "auto"},
        "stream": True,
    }
    result = _anthropic_messages_to_openai(payload)

    # Check tools converted
    assert len(result["tools"]) == 1
    assert result["tools"][0]["type"] == "function"
    assert result["tools"][0]["function"]["name"] == "Read"
    assert result["tools"][0]["function"]["parameters"]["type"] == "object"

    # Check tool_choice
    assert result["tool_choice"] == "auto"

    # Check messages
    msgs = result["messages"]
    assert msgs[0] == {"role": "user", "content": "read main.py"}
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Reading file..."
    assert len(msgs[1]["tool_calls"]) == 1
    assert msgs[1]["tool_calls"][0]["id"] == "toolu_abc"
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "Read"
    assert json.loads(msgs[1]["tool_calls"][0]["function"]["arguments"]) == {"path": "main.py"}
    assert msgs[2]["role"] == "tool"
    assert msgs[2]["tool_call_id"] == "toolu_abc"
    assert msgs[2]["content"] == "file data here"
    print("  request_tool_use_round_trip OK")


def test_response_no_tool_calls():
    """Normal response without tool_calls still works."""
    body = {
        "id": "chatcmpl-456",
        "choices": [{
            "message": {"role": "assistant", "content": "Hello!"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    result = _openai_response_to_anthropic(body, "test-model")
    assert result["stop_reason"] == "end_turn"
    assert len(result["content"]) == 1
    assert result["content"][0] == {"type": "text", "text": "Hello!"}
    print("  response_no_tool_calls OK")


def test_tool_choice_variants():
    """All Anthropic tool_choice types are mapped correctly."""
    base = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}

    # auto
    r = _anthropic_messages_to_openai({**base, "tool_choice": {"type": "auto"}})
    assert r["tool_choice"] == "auto"

    # any → required
    r = _anthropic_messages_to_openai({**base, "tool_choice": {"type": "any"}})
    assert r["tool_choice"] == "required"

    # specific tool
    r = _anthropic_messages_to_openai({**base, "tool_choice": {"type": "tool", "name": "Read"}})
    assert r["tool_choice"] == {"type": "function", "function": {"name": "Read"}}

    # none
    r = _anthropic_messages_to_openai({**base, "tool_choice": {"type": "none"}})
    assert r["tool_choice"] == "none"
    print("  tool_choice_variants OK")


if __name__ == "__main__":
    print("Tool conversion tests:")
    test_response_with_tool_calls()
    test_request_tool_use_round_trip()
    test_response_no_tool_calls()
    test_tool_choice_variants()
    print("All tool conversion tests passed!")
