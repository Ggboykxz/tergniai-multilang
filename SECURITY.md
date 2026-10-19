# Security Policy

## Supported versions

Security fixes are applied to the latest release on the `main` branch.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately using GitHub's
[private vulnerability reporting](../../security/advisories/new)
(Security tab → "Report a vulnerability").

Please include:

- A description of the issue and its impact
- Steps to reproduce or a proof of concept
- Any suggested fix

We aim to acknowledge reports within 3 working days and to share a fix timeline within 10 working days.

## Handling secrets

- API keys are read only from environment variables. Never commit them.
- If you accidentally commit a key, **revoke it immediately** at the provider (Azure portal / Groq console);
  removing it from git history is not enough.
- CI scans every push and pull request for secrets with gitleaks.
