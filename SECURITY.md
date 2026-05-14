# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by opening a private issue or contacting the maintainer directly.

## Secrets Management

- API keys and credentials must never be committed to the repository.
- Use `.env` files locally for disposable or developer-specific secrets, and keep them out of git.
- Use GitHub repository variables for non-secret cloud identifiers and rollout inputs only.
- Prefer GitHub OIDC for CI/CD cloud auth instead of stored service account keys.
- Put shared cloud runtime secrets in the runtime environment or a managed secret path, not in committed examples or repository-variable sync.

## Dependencies

- Dependencies are pinned via `uv.lock`.
- Automated vulnerability scanning via GitHub Dependabot.
