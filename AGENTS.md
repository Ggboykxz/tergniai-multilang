# AGENTS.md — Terngi AI (tergniai-multilang)

Project instructions for AI coding agents working in this repository. ECC
(`ecc-universal`) is enabled at project scope through `opencode.json`; apply its
agents, skills, and rules to the whole codebase.

## Project

FastAPI service that exposes translation, conversation, streaming chat, and a
tool-using AI agent for 96 languages, with an African-language focus (Yoruba,
Hausa, Igbo, Nigerian Pidgin, Swahili, Amharic, isiZulu, and others). Providers
are pluggable and tried in order: Azure Translator, Groq / OpenAI-compatible
APIs, and MORENA (local llama.cpp).

- Runtime: Python 3.10–3.13, FastAPI, Pydantic v2, httpx, uvicorn.
- Tests: pytest + pytest-asyncio, `TestClient`, `respx`, `fakeredis`.
- Lint/format: ruff (line length 100). Types: mypy. Coverage: pytest-cov.
- Storage: in-memory by default; optional Redis for cache, rate limits, and
  conversations (`REDIS_URL`).
- Web UI: `static/` + the `/chat` route.

## Layout

```
main.py                 FastAPI app, middleware order, exception envelopes
config.py               Environment parsing, language catalogue, provider config
middleware.py           Auth, rate limiting, request IDs, security headers, body limit
metrics.py              Prometheus counters/histograms
models.py               Pydantic request/response models
routes/                 base, translation, conversation, agent, chat endpoints
services/               providers, key pool, retry, cache, store, conversations, agent
clients/python/         Typed Python SDK (tested by tests/test_client_sdk.py)
tests/                  Unit and integration tests
docs/                   Design and provider documentation
```

## Commands

```bash
# One-time setup (Python 3.12 is known good; 3.10–3.13 supported)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.lock   # reproducible, hashed
# or: uv venv --python 3.12 .venv && uv pip install -r requirements-dev.txt

# ECC/OpenCode plugin (creates node_modules/ only; it is git-ignored)
npm install --no-save ecc-universal

# Run the API
uvicorn main:app --reload

# Quality gates
pytest -q
pytest --cov=. --cov-report=term-missing
ruff check .
ruff format --check .
mypy .
```

## ECC workflow (mandatory for non-trivial work)

1. **Plan** — use the ECC `planner` role for multi-file features or refactors.
   Identify affected routes, services, config, and tests before editing.
2. **TDD** — write or update a failing test first, then the minimal
   implementation, then refactor. Keep coverage at or above 80%.
3. **Review** — run the ECC `python-reviewer` and `security-reviewer` roles on
   every change. Address CRITICAL/HIGH findings before finishing.
4. **Verify** — run `pytest`, `ruff check`, and `mypy` and report the exact
   commands and results.

Use ECC skills when relevant: `python-patterns`, `python-testing`,
`security-review`, `tdd-workflow`, `verification-loop`, `docker-patterns`,
`redis-patterns`, `api-design`, `error-handling`.

## Code rules

- Follow existing style: `typing.List/Optional/Dict` (not `list[...]` /
  `X | None`), module-level imports grouped stdlib → third-party → local.
- Keep changes small and focused; prefer many small modules over large files
  (200–400 lines typical, 800 hard maximum).
- Never mutate shared state in place. Return new objects; use copies for
  updates. Concurrency-sensitive caches, key pools, and stores must be
  lock-protected or atomic.
- Async correctness: no blocking I/O in `async def`; use `httpx.AsyncClient`
  with explicit timeouts. Never `time.sleep` in request paths.
- Validate every external input at the boundary with Pydantic models or explicit
  checks. Never trust provider responses, headers, or environment values.
- Handle errors explicitly. No bare `except:` and no silent `pass`. Preserve
  the API error envelope `{"error": true, "message": ..., "status_code": ...}`.
- Never log or return secrets, API keys, full request bodies, or PII. Read
  secrets from environment variables only; `.env` is git-ignored.
- Security: parameterized queries only, no `eval`/`exec` on user input, no
  shell interpolation, validate URLs before outbound requests (SSRF), enforce
  auth and rate limits on every non-public route.
- Add type hints to every public function. Keep functions under ~50 lines and
  nesting under 4 levels.
- Tests must be deterministic and isolated: reset caches, key pools, rate
  limiters, and conversation stores via the existing fixtures. Mock all
  upstream HTTP; never call real providers in tests.
- Update `README.md`, `.env.example`, and `docs/` when behavior or configuration
  changes. Add a `CHANGELOG.md` entry for user-visible changes.

## Review gates

- **Block** on CRITICAL security findings (secrets, auth bypass, injection,
  SSRF, unsafe deserialization).
- **Fix** HIGH findings (missing validation, blocking calls in async paths,
  unbounded resources, swallowed exceptions) before declaring done.
- **Report** MEDIUM/LOW findings with file and line, but do not silently
  refactor unrelated code.

A clean review with zero findings is valid. Do not invent issues to look
thorough.
