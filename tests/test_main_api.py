import pytest
from fastapi.testclient import TestClient
import main
import uuid
from datetime import UTC, datetime, timedelta


client = TestClient(main.app)


def test_v1_models():
    r = client.get("/v1/models")
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    ids = [d["id"] for d in data["data"]]
    assert "coding" in ids
    assert "claude-sonnet-4-6" in ids


def test_get_config_keys():
    r = client.get("/api/config/keys")
    assert r.status_code == 200
    data = r.json()
    assert "keys" in data
    assert isinstance(data["keys"], dict)


def test_test_provider_key_empty():
    r = client.post("/api/config/keys/test", json={"provider": "google", "value": ""})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "Empty key" in data["message"]


def test_test_provider_key_bad_format():
    r = client.post("/api/config/keys/test", json={"provider": "google", "value": "badkey"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "Invalid key format" in data["message"] or "Format" in data["message"]


def test_test_provider_key_env_reference_missing_var():
    r = client.post("/api/config/keys/test", json={"provider": "google", "value": "env:__MISSING_TEST_VAR__"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "Environment variable not found" in data["message"]


def test_ollama_status_and_catalogue_local():
    r = client.get("/api/ollama/status")
    assert r.status_code == 200
    st = r.json()
    assert "installed" in st and "model_count" in st

    r2 = client.get("/api/catalogue/local")
    assert r2.status_code == 200
    d2 = r2.json()
    assert "models" in d2


def test_reload_config():
    r = client.post("/api/reload-config")
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True


def test_resume_proxy_and_provider_behaviors():
    paused = client.post("/api/pause")
    assert paused.status_code == 200

    status_paused = client.get("/api/status")
    assert status_paused.status_code == 200
    assert status_paused.json().get("paused") is True

    resumed_proxy = client.post("/api/resume")
    assert resumed_proxy.status_code == 200
    assert resumed_proxy.json().get("ok") is True

    status_resumed = client.get("/api/status")
    assert status_resumed.status_code == 200
    assert status_resumed.json().get("paused") is False

    suspended = client.post("/api/suspend", json={"provider": "nvidia"})
    assert suspended.status_code == 200

    with_susp = client.get("/api/suspensions")
    assert with_susp.status_code == 200
    assert "nvidia" in with_susp.json().get("suspensions", {})

    resumed_provider = client.post("/api/resume", json={"provider": "nvidia"})
    assert resumed_provider.status_code == 200
    assert resumed_provider.json().get("ok") is True

    no_susp = client.get("/api/suspensions")
    assert no_susp.status_code == 200
    assert "nvidia" not in no_susp.json().get("suspensions", {})


def test_invalid_project_token_rejected_on_models():
    r = client.get("/v1/models", headers={"Authorization": "Bearer invalid-token"})
    assert r.status_code == 401


def test_models_requires_authorization_header_when_strict_mode_enabled():
    prev = main.state.config.get("settings", {}).get("require_auth_header", False)
    main.state.config.setdefault("settings", {})["require_auth_header"] = True
    try:
        r = client.get("/v1/models")
        assert r.status_code == 401
        assert "Authorization header required" in r.json().get("detail", "")
    finally:
        main.state.config.setdefault("settings", {})["require_auth_header"] = prev


def test_invalid_token_rate_limit_blocks_after_threshold():
    settings = main.state.config.setdefault("settings", {})
    prev_enabled = settings.get("auth_bruteforce_protection", True)
    prev_limit = settings.get("invalid_token_limit_per_minute", 12)
    prev_window = settings.get("invalid_token_window_seconds", 60)
    prev_block = settings.get("invalid_token_block_seconds", 120)

    settings["auth_bruteforce_protection"] = True
    settings["invalid_token_limit_per_minute"] = 2
    settings["invalid_token_window_seconds"] = 60
    settings["invalid_token_block_seconds"] = 120
    main.state.invalid_auth_attempts.clear()
    main.state.auth_block_until.clear()
    main.state.security_metrics = {
        "invalid_token_failures_total": 0,
        "auth_blocks_triggered_total": 0,
        "auth_block_hits_total": 0,
        "auth_success_resets_total": 0,
    }

    try:
        r1 = client.get("/v1/models", headers={"Authorization": "Bearer invalid-token"})
        r2 = client.get("/v1/models", headers={"Authorization": "Bearer invalid-token"})
        r3 = client.get("/v1/models", headers={"Authorization": "Bearer invalid-token"})
        assert r1.status_code == 401
        assert r2.status_code == 401
        assert r3.status_code == 429
        assert "Too many invalid authentication attempts" in r3.json().get("detail", "")
        assert main.state.security_metrics.get("invalid_token_failures_total", 0) >= 2
        assert main.state.security_metrics.get("auth_blocks_triggered_total", 0) >= 1
        assert main.state.security_metrics.get("auth_block_hits_total", 0) >= 1
    finally:
        settings["auth_bruteforce_protection"] = prev_enabled
        settings["invalid_token_limit_per_minute"] = prev_limit
        settings["invalid_token_window_seconds"] = prev_window
        settings["invalid_token_block_seconds"] = prev_block
        main.state.invalid_auth_attempts.clear()
        main.state.auth_block_until.clear()


def test_security_status_endpoint_exposes_auth_settings():
    r = client.get("/api/security/status")
    assert r.status_code == 200
    security = r.json().get("security", {})
    assert "require_auth_header" in security
    assert "auth_bruteforce_protection" in security
    assert "invalid_token_limit_per_minute" in security
    assert "blocked_clients_count" in security
    assert "metrics" in security
    assert "invalid_token_failures_total" in security.get("metrics", {})


def test_security_status_cleans_expired_auth_entries():
    now = datetime.now(UTC)
    main.state.auth_block_until["expired-client"] = now - timedelta(seconds=5)
    main.state.invalid_auth_attempts["stale-client"] = main.deque([now - timedelta(seconds=999)])

    r = client.get("/api/security/status")
    assert r.status_code == 200

    security = r.json().get("security", {})
    assert "expired-client" not in security.get("blocked_clients", {})
    assert "expired-client" not in main.state.auth_block_until
    assert "stale-client" not in main.state.invalid_auth_attempts


def test_create_project_and_coding_only_policy_models():
    project_name = f"proj-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/projects",
        json={"name": project_name, "policy": "coding_only", "quota_mode": "hard_block"},
    )
    assert created.status_code == 200
    token = created.json()["project"]["token"]

    models = client.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
    assert models.status_code == 200
    ids = [d["id"] for d in models.json().get("data", [])]
    assert "coding" in ids
    assert "claude-sonnet-4-6" in ids


def test_chat_accepts_alias_model_hint_with_mocked_upstream(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"id": "mocked", "object": "chat.completion", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}

    async def fake_post(*args, **kwargs):
        return FakeResponse()

    with TestClient(main.app) as live_client:
        monkeypatch.setattr(main.state.client, "post", fake_post)
        payload = {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hello"}]}
        r = live_client.post("/v1/chat/completions", json=payload, headers={"Authorization": "Bearer rotator"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("choices")


def test_chat_accepts_explicit_provider_model_alias(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"id": "mocked", "object": "chat.completion", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}

    async def fake_post(url, *args, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs.get("json", {})
        return FakeResponse()

    with TestClient(main.app) as live_client:
        previous_aliases = dict(main.state.config.get("compat_aliases", {}))
        main.state.config["compat_aliases"] = {**previous_aliases, "alias-local-coder": "local:qwen3-coder-next:latest"}
        try:
            monkeypatch.setattr(main.state.client, "post", fake_post)
            payload = {"model": "alias-local-coder", "messages": [{"role": "user", "content": "hello"}]}
            r = live_client.post("/v1/chat/completions", json=payload, headers={"Authorization": "Bearer rotator"})
            assert r.status_code == 200
            assert captured.get("url", "").endswith("/chat/completions")
            assert captured.get("payload", {}).get("model") == "qwen3-coder-next:latest"
        finally:
            main.state.config["compat_aliases"] = previous_aliases


def test_project_quota_hard_block_returns_429():
    project_name = f"quota-{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/projects",
        json={"name": project_name, "daily_limit": 0, "policy": "full_access", "quota_mode": "hard_block"},
    )
    assert created.status_code == 200
    token = created.json()["project"]["token"]

    payload = {"messages": [{"role": "user", "content": "hello"}]}
    call = client.post("/v1/chat/completions", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert call.status_code == 429


def test_claude_onboarding_project_creation_is_coding_only():
    created = client.post("/api/projects/claude-onboarding", json={})
    assert created.status_code == 200
    data = created.json()
    assert data.get("ok") is True
    project = data.get("project", {})
    token = project.get("token")
    assert token and token.startswith("proj-")
    assert str(project.get("name", "")).startswith("ar_claudecode_api")
    assert project.get("policy") == "coding_only"

    models = client.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
    assert models.status_code == 200
    ids = [d["id"] for d in models.json().get("data", [])]
    assert "coding" in ids
    assert "claude-sonnet-4-6" in ids

    usage = data.get("usage", [])
    assert any("claude --model coding" in line for line in usage)


def test_maintenance_backup_and_purge_endpoints():
    backup = client.post("/api/maintenance/backup", json={})
    assert backup.status_code == 200
    backup_data = backup.json()
    assert backup_data.get("ok") is True
    assert "backup" in backup_data

    listed = client.get("/api/maintenance/backups")
    assert listed.status_code == 200
    assert isinstance(listed.json().get("items"), list)

    purge = client.post("/api/maintenance/purge-before", json={"before_date": "1900-01-01", "create_backup": False})
    assert purge.status_code == 200
    purge_data = purge.json()
    assert purge_data.get("ok") is True
    assert "deleted" in purge_data


def test_maintenance_restore_and_delete_backup_endpoints():
    created = client.post("/api/maintenance/backup", json={})
    assert created.status_code == 200
    name = created.json().get("backup", {}).get("name")
    assert name

    restored = client.post("/api/maintenance/restore", json={"name": name})
    assert restored.status_code == 200
    assert restored.json().get("ok") is True

    deleted = client.delete(f"/api/maintenance/backups/{name}")
    assert deleted.status_code == 200
    assert deleted.json().get("ok") is True


def test_maintenance_schedule_restore_next_endpoint():
    backup = client.post("/api/maintenance/backup", json={})
    assert backup.status_code == 200
    name = backup.json().get("backup", {}).get("name")
    assert name

    scheduled = client.post("/api/maintenance/restore-next", json={"name": name})
    assert scheduled.status_code == 200
    data = scheduled.json()
    assert data.get("ok") is True
    assert data.get("pending_restore") == name


def test_maintenance_settings_get_and_update_endpoint():
    got = client.get("/api/maintenance/settings")
    assert got.status_code == 200
    settings = got.json().get("settings", {})
    assert "auto_backup_on_shutdown" in settings
    assert "auto_restore_latest_on_startup" in settings

    updated = client.post(
        "/api/maintenance/settings",
        json={"auto_backup_on_shutdown": False, "auto_restore_latest_on_startup": False},
    )
    assert updated.status_code == 200
    u = updated.json().get("settings", {})
    assert u.get("auto_backup_on_shutdown") is False
    assert u.get("auto_restore_latest_on_startup") is False

    restore = client.post(
        "/api/maintenance/settings",
        json={"auto_backup_on_shutdown": True, "auto_restore_latest_on_startup": True},
    )
    assert restore.status_code == 200


def test_v1_messages_anthropic_format_with_mocked_upstream(monkeypatch):
    """Test /v1/messages endpoint accepts Anthropic Messages API format."""

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    async def fake_post(*args, **kwargs):
        return FakeResponse()

    with TestClient(main.app) as live_client:
        monkeypatch.setattr(main.state.client, "post", fake_post)
        payload = {
            "model": "coding",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "hello"}],
        }
        r = live_client.post("/v1/messages", json=payload, headers={"Authorization": "Bearer rotator"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("type") == "message"
        assert data.get("role") == "assistant"
        assert data.get("model") == "coding"
        assert len(data.get("content", [])) > 0
        assert data["content"][0]["type"] == "text"
        assert data["content"][0]["text"] == "Hello!"
        assert data.get("stop_reason") == "end_turn"
        assert "usage" in data


def test_v1_messages_with_system_prompt(monkeypatch):
    """Test /v1/messages with system prompt is properly converted."""
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "id": "chatcmpl-mock2",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }

    async def fake_post(url, *args, **kwargs):
        captured["payload"] = kwargs.get("json", {})
        return FakeResponse()

    with TestClient(main.app) as live_client:
        monkeypatch.setattr(main.state.client, "post", fake_post)
        payload = {
            "model": "coding",
            "max_tokens": 1024,
            "system": "You are a coding assistant.",
            "messages": [{"role": "user", "content": "write hello world"}],
        }
        r = live_client.post("/v1/messages", json=payload, headers={"Authorization": "Bearer rotator"})
        assert r.status_code == 200
        sent_messages = captured.get("payload", {}).get("messages", [])
        assert sent_messages[0]["role"] == "system"
        assert "coding assistant" in sent_messages[0]["content"]
        assert sent_messages[1]["role"] == "user"