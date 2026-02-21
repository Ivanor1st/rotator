# Contributing to API Rotator

Thanks for your interest in contributing! Here's how to get started.

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/Ivanor1st/rotator.git
cd rotator
```

### 2. Create a virtual environment

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your config

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your API keys
```

### 5. Run the server

```bash
python main.py
```

The dashboard will be available at `http://localhost:47822`.

---

## Running Tests

```bash
pytest tests/ -v
```

All tests must pass before submitting a PR.

---

## Submitting Changes

1. **Fork** the repository
2. Create a **feature branch** (`git checkout -b feat/my-feature`)
3. Make your changes
4. Run `pytest tests/ -v` — all tests must pass
5. **Commit** with a clear message (`git commit -m "feat: add X"`)
6. **Push** to your fork (`git push origin feat/my-feature`)
7. Open a **Pull Request** against `main`

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code restructuring without behavior change
- `test:` — adding or updating tests

---

## Code Style

- Python 3.10+ — use type hints
- Keep `main.py` endpoints consistent with existing patterns
- JS files use plain functions (no build step)
- All API responses return JSON with `{"ok": true}` or `{"detail": "..."}`

---

## Reporting Bugs

Open an [issue](../../issues) with:

- Steps to reproduce
- Expected vs. actual behavior
- OS / Python version
- Relevant logs

---

## Security Issues

**Do NOT open a public issue for security vulnerabilities.**
See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.
