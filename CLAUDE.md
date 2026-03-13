# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

API Rotator is a local proxy server compatible with OpenAI/Anthropic APIs that:
- Routes requests to the best AI provider based on task type (coding, reasoning, chat, long, vision, audio, translate)
- Automatically rotates API keys when quotas are hit or errors occur
- Provides a web dashboard for monitoring and configuration
- Supports Claude Code and OpenClaw integrations

## Common Commands

```powershell
# Install dependencies
pip install -r requirements.txt

# Run the server (port 47822)
python main.py

# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_router.py -v

# Run a specific test
pytest tests/test_router.py::test_profile_detection -v

# Start with auto-install (PowerShell launcher)
.\start.ps1

# Non-interactive mode (CI/scripts) - auto-install + start + verify
.\start.ps1 go

# Quick start (if already installed)
.\rotator-quick.ps1

# Quick start options
.\rotator-quick.ps1 -StatusOnly   # Quick status check
.\rotator-quick.ps1 -Stop         # Stop the proxy
.\rotator-quick.ps1 -Restart      # Restart the proxy
.\rotator-quick.ps1 -Claude       # Start with Claude Code

# Register global 'rotator' command
.\rotator-register.ps1

# CLI commands (rotator.ps1)
.\rotator.ps1 status                     # State of the proxy
.\rotator.ps1 force coding nvidia        # Force coding → NVIDIA
.\rotator.ps1 force chat local           # Force chat → local
.\rotator.ps1 key block "Google 1"       # Block a key
.\rotator.ps1 key unblock "Google 1"     # Unblock a key
.\rotator.ps1 reset                      # Reset all to auto
.\rotator.ps1 force all local           # Emergency: all to local
.\rotator.ps1 benchmark                  # Run benchmark
.\rotator.ps1 logs --follow              # Live logs
```

## Architecture

The rotator acts as a smart proxy that:
1. Receives API requests (OpenAI `/v1/chat/completions` or Anthropic `/v1/messages`)
2. Detects the task profile from the model name or request content
3. Selects the best available provider from the routing chain
4. Rotates API keys on quota/expiry errors
5. Forwards the request to the chosen provider

### Core Files

- **main.py** - FastAPI entry point (~4000 lines). All route handlers, auth, dashboard HTML generation
- **router.py** - Profile detection (keyword matching) + routing chain resolution. Falls back to `ROUTING_CHAINS` constants if DB is empty
- **key_manager.py** - Key validation, quota checking, automatic rotation on errors
- **db.py** - SQLite via aiosqlite. Stores routing chains, key status, usage stats, projects/tokens
- **constants.py** - Enums (Profile, Provider, KeyStatus), default routing chains, API endpoints

### Request Flow

```
Client Request (OpenAI /v1/chat/completions or Anthropic /v1/messages)
         ↓
main.py: receive_request() - auth check, parse request
         ↓
router.py: detect_profile() - extract profile from model or auto-detect keywords
         ↓
router.py: get_routing_chain() - get provider chain (from DB or fallback constants)
         ↓
key_manager.py: select_key() - find first available key in chain
         ↓
main.py: forward_request() - call provider API with selected key
         ↓
Response returned to client
```

On error (quota/expiry): key_manager.py marks key as failed, rotates to next key in chain, retries.

### Routing Chain

Each profile (`coding`, `reasoning`, etc.) has a chain of (provider, model) tuples tried in order:

```python
# router.py - default fallback chains
ROUTING_CHAINS = {
    "coding": [
        (Provider.OLLAMA_CLOUD, "minimax-m2.5:cloud"),
        (Provider.NVIDIA, "minimaxai/minimax-m2.1"),
        # ... more fallbacks
    ],
    # ...
}
```

Chains can be customized via the database (Dashboard → Presets tab) or fall back to hardcoded constants.

### Profile Detection

Detection priority:
1. Explicit: model name matches a profile (`coding`, `reasoning`, etc.)
2. Auto-detect: keywords in request content
3. Default: `chat` profile

**Auto-detection keywords** (in router.py):
| Profile | Keywords |
|---------|----------|
| coding | code, fix, bug, function, implement, debug, script, class |
| reasoning | explain, why, analyze, compare, reason, think, solve, math, proof |
| long | document, file, entire, full |
| vision | image, photo, picture, screenshot, vision, ocr, visual |
| audio | transcribe, speech, audio |
| translate | translate, translation |
| chat | (default fallback - no keywords) |

### Default Routing Chains

Each profile has a fallback chain tried in order. The chain can be customized via the database or uses these defaults:

| Profile | Chain (in order) |
|---------|-----------------|
| coding | Ollama Cloud (minimax-m2.5:cloud) → NVIDIA (minimax-m2.1) → Ollama Cloud (qwen3-coder-next:cloud) → NVIDIA (qwen3-coder) → NVIDIA (devstral) → OpenRouter (qwen3-coder:free) → Local (qwen3-coder-next) |
| reasoning | Ollama Cloud (minimax-m2.5:cloud) → Ollama Cloud (qwen3.5:397b-cloud) → NVIDIA (deepseek-v3.2) → NVIDIA (qwen3-next-80b-thinking) → NVIDIA (gpt-oss-120b) → Ollama Cloud (glm-5:cloud) → OpenRouter (deepseek-r1:free) |
| chat | Ollama Cloud (minimax-m2.5:cloud) → NVIDIA (minimax-m2.1) → OpenRouter (trinity-large:free) → Google (gemma-3-27b-it) → OpenRouter (llama-3.3-70b:free) → OpenRouter (mistral-small-3.1:free) → Google (gemini-2.5-flash) → Local (lfm2.5-thinking) |
| long | NVIDIA (minimax-m2.1) → NVIDIA (nemotron-3-nano) → Ollama Cloud (kimi-k2.5:cloud) → Ollama Cloud (qwen3.5:397b-cloud) → NVIDIA (llama-4-maverick) → Google (gemini-2.5-flash) → OpenRouter (qwen3-next-80b:free) |
| vision | OpenRouter (qwen3-vl-235b:free) → OpenRouter (qwen3-vl-30b:free) → NVIDIA (llama-3.2-90b-vision) → NVIDIA (kimi-k2.5) → Ollama Cloud (kimi-k2.5:cloud) → Ollama Cloud (qwen3.5-397b:cloud) → Google (gemini-2.5-flash) → Local (glm-ocr) |
| audio | NVIDIA (phi-4-multimodal) → Google (gemini-2.5-flash-native-audio) |
| translate | NVIDIA (riva-translate-4b) → Local (translategemma:27b) → OpenRouter (gemma-3-27b:free) |

### Key Rotation

`key_manager.py` handles:
- Validating keys on startup
- Tracking quota usage
- Blocking keys on repeated failures
- Selecting the next available key from the chain

### Database Schema (key tables)

- `routing_chains` - Custom provider/model chains per profile
- `api_keys` - Provider keys with status (active/blocked/suspended)
- `usage_stats` - Per-provider request counts
- `projects` - Named projects with auto-generated tokens
- `locks` - Manual provider overrides

### Dashboard

13 tabs served at `/dashboard`. HTML is auto-generated in `main.py` (search for `generate_dashboard_html`). Frontend JS in `static/js/`.

**Dashboard tabs**: Overview, Presets, Tests & Benchmark, Stats, Logs, API Keys, Projects & Tokens, Claude Code, OpenClaw, Backups, Model Catalogue, Configuration, Documentation

### Key API Endpoints

| Path | Description |
|------|-------------|
| `/v1/chat/completions` | OpenAI-compatible endpoint |
| `/v1/messages` | Anthropic-compatible endpoint |
| `/v1/models` | List available models |
| `/dashboard` | Web UI |
| `/docs` | Swagger API documentation |
| `/openapi.json` | OpenAPI schema |

### Configuration & Keys

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/config` | Read config.yaml |
| `POST` | `/api/config` | Write config.yaml |
| `GET` | `/api/config/keys` | Get structured keys |
| `POST` | `/api/config/keys` | Register keys |
| `POST` | `/api/config/keys/test` | Test a cloud key |
| `POST` | `/api/pause` | Pause the proxy |
| `POST` | `/api/resume` | Resume the proxy |
| `POST` | `/api/restart` | Restart the proxy |
| `POST` | `/api/reload-config` | Hot reload config |

### Routing & Overrides

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/override/force` | Force profile → provider |
| `POST` | `/api/override/block` | Block a provider |
| `POST` | `/api/override/unblock` | Unblock a provider |
| `POST` | `/api/override/reset` | Reset all to auto |
| `POST` | `/api/lock` | Lock a model to provider |
| `DELETE` | `/api/lock/{profile}` | Remove lock |

### Projects & Claude Code

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects` | List projects |
| `POST` | `/api/projects` | Create project |
| `GET` | `/api/projects/{id}` | Get project details |
| `PUT` | `/api/projects/{id}` | Update project |
| `DELETE` | `/api/projects/{id}` | Delete project |
| `POST` | `/api/projects/{id}/revoke` | Revoke token |
| `GET` | `/api/projects/{id}/usage` | Get usage history |
| `POST` | `/api/projects/claude-onboarding` | Create Claude token |
| `GET` | `/api/claude-code/memory` | Read CLAUDE.md |
| `POST` | `/api/claude-code/memory` | Write CLAUDE.md |

### Maintenance & Backups

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/maintenance/backups` | List snapshots |
| `POST` | `/api/maintenance/backup` | Create snapshot |
| `POST` | `/api/maintenance/restore` | Restore snapshot |
| `DELETE` | `/api/maintenance/backups/{name}` | Delete snapshot |
| `POST` | `/api/maintenance/reset-all` | Reset database |

### Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | Global proxy status |
| `GET` | `/api/health` | Provider health check |
| `GET` | `/api/quota` | Quotas per provider |
| `GET` | `/api/logs` | Recent logs |
| `GET` | `/api/stats` | Statistics |
| `GET` | `/api/security/status` | Security status |

### Profile System

Request routing uses profiles: `coding`, `reasoning`, `chat`, `long`, `vision`, `audio`, `translate`. The profile can be specified via `model` parameter or auto-detected from request content.

### Supported Providers

OpenRouter, NVIDIA NIM, Google AI, Ollama (local/cloud), and other OpenAI-compatible providers. Model catalogs are cached in JSON files: `openrouter_models.json`, `nvidia_models.json`, `ollama_models_cloud.json`.

**Provider API Endpoints** (base URLs):
| Provider | Endpoint |
|----------|----------|
| NVIDIA | `https://integrate.api.nvidia.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| Google | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Ollama (local) | `http://localhost:11434` |
| Ollama Cloud | `https://cloud.ollama.ai` |
| OpenAI | `https://api.openai.com/v1` |
| Anthropic | `https://api.anthropic.com` |

**Default Rate Limits** (requests per minute):
- NVIDIA: 35 RPM
- OpenRouter: 5 RPM
- Google: 3 RPM

## Development Notes

- The project uses Python 3.10-3.13
- Configuration via `config.yaml` (copy from `config.example.yaml`) and `.env` file
- The `.env` file contains API keys referenced as `env:VAR_NAME` in config.yaml (never commit this)
- Database is `rotator.db` (SQLite)
- Auto-backups stored in `backups/` directory
- Tests in `tests/` directory using pytest with pytest-asyncio

### OpenClaw Integration

Connect messaging apps (WhatsApp, Telegram, Discord, iMessage, Slack, Signal) to AI models via the rotator. OpenClaw is a separate Node.js service (Node 22+) that acts as a gateway.

```bash
npm install -g openclaw@latest
openclaw onboard --install-daemon
openclaw gateway --port 18789
```

Configure rotator as provider via Dashboard → OpenClaw → Connexion.

### IDE Integrations

Compatible with any app accepting OpenAI-compatible endpoints:

| App | Base URL | API Key | Model |
|-----|----------|---------|-------|
| Continue | `http://localhost:47822/v1` | `rotator` | `coding` |
| Cline | `http://localhost:47822/v1` | `rotator` | `coding` |
| Cursor | `http://localhost:47822/v1` | `rotator` | Override in settings |
| Open WebUI | `http://localhost:47822/v1` | `rotator` | - |
| Aider CLI | `--openai-api-base http://localhost:47822/v1` | `--openai-api-key rotator` | - |

### Security Features

- Brute-force protection: blocks IPs after too many invalid tokens
- Configurable auth header requirement
- Default API key: `rotator` (change in production)
- Security status: `GET /api/security/status`

### Claude Code Connection

```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:47822"
$env:ANTHROPIC_AUTH_TOKEN = "rotator"
$env:CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS = "1"
claude --model coding
```

Model aliases: `claude-sonnet-4-6`, `gpt-5-mini`, `github/gpt5mini` → profile `coding`

### Key Test Files

- `tests/test_main_api.py` - Main API endpoint tests
- `tests/test_router.py` - Profile detection and routing tests
- `tests/test_db.py` - Database operations tests
- `tests/test_key_manager.py` - Key validation and rotation tests
- `tests/test_tool_conversion.py` - Tool conversion tests

### Model Catalogs

Model catalogs are cached locally in JSON format:
- `openrouter_models.json` - OpenRouter available models
- `nvidia_models.json` - NVIDIA NIM models
- `ollama_models_cloud.json` - Ollama Cloud models

Refresh catalogs via dashboard or `/api/catalogue/refresh` endpoint.

### Core Enums (in constants.py)

**Profiles**: `coding`, `reasoning`, `chat`, `long`, `vision`, `audio`, `translate`

**Providers**: `ollama_cloud`, `local`, `nvidia`, `openrouter`, `google`, `openai`, `anthropic`, `custom`

**KeyStatus**: `active`, `blocked`, `suspended`, `error`, `quota_exceeded`

**Default API Key**: `rotator`

**Default Port**: `47822`

### Troubleshooting

| Problem | Solution |
|---------|----------|
| Proxy inaccessible | Check `start.ps1` is running, port `47822` available |
| No providers available | Verify keys in `config.yaml` and check `blocked`/`force` states |
| Google quotas exhausted | Wait for reset or force `local`/`openrouter` |
| Config not applied | `POST /api/reload-config` |
| `running scripts is disabled` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `python is not recognized` | Install Python 3.10+ |
| Port already in use | `.\rotator.ps1 stop --force` then `.\start.ps1` |
| Claude says "model doesn't exist" | Verify `.env` file exists with required keys |

### Configuration Files

- `config.yaml` - Main configuration (copy from `config.example.yaml`)
- `.env` - API keys (never commit this file)
- `rotator.db` - SQLite database
- `backups/` - Auto-backup directory
