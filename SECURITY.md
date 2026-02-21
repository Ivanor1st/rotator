# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | ✅        |

## Important: Local-Only Design

API Rotator is designed to run **locally on your machine** (`127.0.0.1`). It is **not intended** to be exposed to the public internet or untrusted networks.

### Known Risks

- **Subprocess execution** — The Ollama catalogue endpoints (`/api/catalogue/install`, `/api/catalogue/delete`) execute system commands (`ollama pull`, `ollama rm`). Model names are validated with a strict regex, but these endpoints should only be accessible from localhost.
- **File writes** — `/api/claude-code/memory` writes `CLAUDE.md` files to disk. Paths are validated and restricted, but this endpoint requires authentication.
- **Admin endpoints** — All `/api/*` endpoints require a valid authentication token. The default token is `rotator` — change it in production via `config.yaml`.

### Recommendations

1. **Never expose the server to `0.0.0.0`** — Keep the default `127.0.0.1` binding
2. **Change the default token** — Replace `rotator` with a strong, unique token in your `config.yaml`
3. **Keep API keys in `.env`** — Never commit `.env` or `config.yaml` to version control
4. **Use a firewall** — Even on localhost, restrict port `47822` if you're on a shared machine

## Reporting a Vulnerability

If you discover a security vulnerability, **please do NOT open a public issue**.

Instead, report it privately:

1. **Email**: Open a [private security advisory](../../security/advisories/new) on GitHub
2. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge your report within **48 hours** and aim to release a fix within **7 days** for critical issues.

## Disclosure Policy

- We follow [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure)
- Credit will be given to reporters in the release notes (unless you prefer anonymity)
- We will not take legal action against good-faith security researchers
