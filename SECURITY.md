# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by opening a private issue or contacting the maintainer directly.

## Secrets Management

- API keys and credentials must never be committed to the repository.
- Use `.env` files locally (listed in `.gitignore`).
- Use GitHub Actions secrets for CI/CD.

## Dependencies

- Dependencies are pinned via `uv.lock`.
- Automated vulnerability scanning via GitHub Dependabot.
