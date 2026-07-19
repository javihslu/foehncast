# Security Policy

## Project Status

FoehnCast is an educational project built for the HSLU MLOps module and is no
longer under active development. Security reports are read and handled on a
best-effort basis, with no committed response time.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it privately via the
repository's Security tab (Report a vulnerability). Do not open a public
issue for security problems.

## Secrets Management

- API keys and credentials must never be committed to the repository.
- Use `.env` files locally for disposable or developer-specific secrets, and keep them out of git.
- Use GitHub repository variables for non-secret cloud identifiers and rollout inputs only.
- Prefer GitHub OIDC for CI/CD cloud auth instead of stored service account keys.
- Put shared cloud runtime secrets in the runtime environment or a managed secret path, not in committed examples or repository-variable sync.

## Dependencies

- Dependencies are pinned via `uv.lock`.
- Automated vulnerability scanning via GitHub Dependabot.

### Accepted Transitive Risks

| Package | Via | Severity | Status | Rationale |
|---------|-----|----------|--------|-----------|
| `diskcache` (pickle deserialization) | `dvc` → `dvc-data` | moderate | no fix available | DVC-internal cache on local filesystem only; not imported by application code; not present in the production container; exploitation requires local filesystem write access to the DVC cache directory |
