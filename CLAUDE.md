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
```

## Architecture

- **main.py** - FastAPI application entry point (~4000 lines). Contains all route handlers, authentication, key management, proxy logic, dashboard HTML generation
- **router.py** - Model routing logic, profile detection from request content
- **db.py** - SQLite database operations using aiosqlite
- **key_manager.py** - API key validation and rotation logic
- **static/** - Dashboard frontend (CSS/JS)

### API Endpoints

| Path | Description |
|------|-------------|
| `/v1/chat/completions` | OpenAI-compatible endpoint |
| `/v1/messages` | Anthropic-compatible endpoint |
| `/v1/models` | List available models |
| `/dashboard` | Web UI |
| `/api/*` | Management APIs (config, keys, routing, backups, etc.) |

### Profile System

Request routing uses profiles: `coding`, `reasoning`, `chat`, `long`, `vision`, `audio`, `translate`. The profile can be specified via `model` parameter or auto-detected from request content.

### Supported Providers

OpenRouter, NVIDIA NIM, Google AI, Ollama (local), and other OpenAI-compatible providers. Model catalogs are cached in JSON files: `openrouter_models.json`, `nvidia_models.json`, `ollama_models_cloud.json`.

## Development Notes

- The project uses Python 3.10-3.13
- Configuration via `config.yaml` and `.env` file
- The `.env` file contains API keys (never commit this)
- Database is `rotator.db` (SQLite)
- Auto-backups stored in `backups/` directory
- Tests are in `tests/` directory using pytest with pytest-asyncio
