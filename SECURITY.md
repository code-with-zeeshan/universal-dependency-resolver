# Security Policy

## Reporting a Vulnerability

If you find a security vulnerability, **do not** open a public GitHub issue. Report privately via:

- [GitHub Security Advisories](https://github.com/code-with-zeeshan/universal-dependency-resolver/security/advisories)

Include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact

## What to expect

- Acknowledgment within 48 hours
- Regular updates on progress
- Coordinated disclosure once a fix is released

## What this project does

- All API inputs validated via Pydantic schemas
- SQL injection prevented through SQLAlchemy ORM parameterized queries
- JWT authentication with bcrypt password hashing (opt-in via `ENABLE_AUTH=true`)
- Rate limiting via slowapi on all API endpoints
- Correlation IDs on every request for traceability
- Security headers (HSTS, CSP, XFO, nosniff) on all API responses
- Input size limits on request bodies
- Output encoding to prevent XSS in exported content

## Scope

The `ud-resolver` Python package and the Desktop app (Electron). Dependencies are scanned by Dependabot and Trivy in CI.
