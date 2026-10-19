# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Security
- Removed hardcoded Azure and Groq API keys; configuration now comes from environment variables.
- Upstream error details are logged instead of returned to clients.
- `memory_context` only accepts `user` / `assistant` roles (blocks system-prompt injection).
- Docker image runs as a non-root user; `--reload` removed from production.

### Added
- `POST /v1/detect` language detection and `"auto"` source language on translate/converse.
- `POST /v1/translate/batch` for translating up to 25 texts in one request.
- In-memory TTL/LRU translation cache.
- Optional client API-key authentication (`API_KEYS`, `X-API-Key` header).
- Per-client rate limiting with `X-RateLimit-*` and `Retry-After` headers.
- `X-Request-ID` / `X-Process-Time-Ms` headers and structured request logs.
- `/health/ready` readiness probe.
- MIT license, contributing guide, code of conduct, security policy, issue/PR templates.
- CI: lint, mypy, tests on Python 3.10–3.13, Docker smoke test, gitleaks, pip-audit, CodeQL, Dependabot.
- `/health` endpoint and Docker `HEALTHCHECK`.
- Test suite with mocked upstream services.
- Request size limits and optional CORS.

### Changed
- Default Groq model is now `openai/gpt-oss-120b` (`llama-3.3-70b-versatile` was retired by Groq).
- Azure and Groq calls are now async with timeouts (no longer block the event loop).
- Upstream failures return `502`, missing configuration returns `503`.
- Pinned dependency versions; removed the invalid `typing` requirement.
- Deploy workflows run CI first, skip on forks, inject secrets as env vars and tag images by commit SHA.
