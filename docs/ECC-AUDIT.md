# ECC Audit — Terngi AI (`tergniai-multilang`)

- **Date:** 2026-10-23
- **Commit:** `4271ffd` (`feat(clients): add typed Python client SDK for API endpoints`)
- **Scope:** entire repository — application, services, tests, SDK, static UI, Docker, CI, dependency pins
- **Method:** ECC `python-reviewer`, `code-reviewer`, `security-reviewer`, `tdd-guide`, `pr-test-analyzer`, `architect`, and `performance-optimizer` roles, with the `python-patterns`, `coding-standards`, `security-review`, `python-testing`, `tdd-workflow`, `verification-loop`, `api-design`, `backend-patterns`, and `latency-critical-systems` skills
- **ECC setup added to this repo:** `opencode.json` (project-scoped plugin, instructions, skills) and `AGENTS.md` (project rules and workflow)
- **Runtime verification (Python 3.12.15):** `188 passed` in ~21s, `ruff check .` clean, `mypy .` clean, total coverage **95%**. Remaining gaps are branch/error paths listed below.

### Verification baseline

| Gate | Command | Result |
|---|---|---|
| Tests | `python -m pytest -q` | **188 passed** |
| Lint | `ruff check .` | **clean** |
| Types | `mypy .` | **clean** (28 source files) |
| Coverage | `pytest --cov=. --cov-report=term-missing` | **95%** (1544 statements, 71 missed) |

Lowest-covered modules: `routes/translation.py` 84%, `services/conversations.py` 89%, `routes/chat.py` 90%, `routes/conversation.py` 90%, `services/azure_translator.py` 90%, `services/agent.py` 93%.

## Executive summary

| Severity | Count | Merge status |
|---|---:|---|
| CRITICAL | 0 | pass |
| HIGH | 8 | block production exposure |
| MEDIUM | 14 | fix in the next iteration |
| LOW | 10 | schedule / hygiene |
| Test gaps | 6 × P0, 18 × P1 | add before relying on the suite as a gate |

No hardcoded secrets, SQL/shell injection sink, authentication bypass, unsafe deserialization, or user-reachable SSRF was found. The architecture is sound for its size: clear routes → services → providers layering, ordered provider fallback, key rotation with cooldowns, jittered retry/`Retry-After` handling, hash-based cache keys, optional Redis, owner-scoped conversations, route-template metrics, request IDs, security headers, and a non-root, hash-locked container.

The eight HIGH findings are concentrated in **state that scales badly**: Redis conversation writes, unbounded conversation growth, missing request deadlines, per-call HTTP clients, inverted health probes, proxy-derived identity, and API error-envelope holes.

## How ECC is enabled in this repository

| File | Purpose |
|---|---|
| `opencode.json` | Loads the `ecc-universal` plugin, ECC instructions, the full ECC skill path, 26 agents, and 26 commands. |
| `AGENTS.md` | Project-scoped rules: stack, layout, quality gates, TDD/review workflow, security and style requirements. |
| `.opencode/commands/`, `.opencode/prompts/`, `.opencode/instructions/` | ECC command templates, agent prompts, and consolidated rules used by `opencode.json`. |

Available workflows include `/plan`, `/tdd`, `/code-review`, `/security`, `/build-fix`, `/e2e`, `/refactor-clean`, `/verify`, `/test-coverage`, and `/orchestrate`. ECC agent roles include `planner`, `architect`, `python-reviewer`, `security-reviewer`, `code-reviewer`, `tdd-guide`, `build-error-resolver`, `e2e-runner`, `database-reviewer`, `performance-optimizer`, and `docs-lookup`.

> Dependency note: `opencode.json` expects `ecc-universal` under `node_modules/`. Run `npm install --no-save ecc-universal` in the repository before starting OpenCode; `node_modules/` is git-ignored.

---

## P0 — fix before production exposure

### H-1. Concurrent chat turns can silently lose messages (lost-update race)

- **File:** `services/conversations.py:61-67`
- **Trigger:** two overlapping `/v1/chat` requests for the same `conversation_id` (double-click, retry, two tabs), especially with `RedisStore`.
- **Failure:** `append()` is a non-atomic load → modify → save. Both requests read the same history; the later `SET` overwrites the earlier turn. One exchange disappears and the next reply uses stale context.
- **Why current guards fail:** the ownership check is correct, but there is no version check or lock; sequential tests cannot catch the interleaving.
- **Fix:** store messages as a Redis list and use an atomic `RPUSH` + `LTRIM` + `EXPIRE`, or `WATCH`/`MULTI` with retry. Add a concurrent-append test against the Redis backend.

### H-2. Redis conversation storage is unbounded (`CONVERSATION_MAX_ITEMS` is ignored)

- **Files:** `services/store.py:105-107`, `services/store.py:141-143`, `services/conversations.py:20`, `config.py:261`
- **Trigger:** any caller creating conversations without an ID (`routes/chat.py:37`), then growing each to 40 × 5,000 characters.
- **Failure:** `make_store()` passes `max_items` only to `MemoryStore`. `RedisStore` neither accepts nor enforces it, and `docker-compose.yml` starts Redis without `maxmemory`. At 60 requests/minute, one IP can create roughly 86,000 conversations/day; Redis OOM turns into API-wide `StoreError` 503s.
- **Fix:** enforce a global key cap (sorted-set index + `ZCARD`, or `maxmemory-policy` with alerting), add per-owner quotas, and reject creates at the cap.

### H-3. No end-to-end deadline; retries and fallbacks multiply latency

- **Files:** `config.py:273-280`, `services/azure_translator.py:69-118`, `services/llm.py:330-409`, `services/agent.py:296-312`, `routes/conversation.py:42-65`
- **Trigger:** Azure is blackholed or slow.
- **Failure:** each attempt can burn `REQUEST_TIMEOUT=30s`; three attempts plus jitter means Groq is not tried for roughly 90s. The agent repeats this per step (up to 6 steps × 8 tool calls). Requests outlive the SDK's 120s default and common 60s proxy idle timeouts, while paid work is duplicated and workers saturate.
- **Fix:** request-scoped deadline (~55s JSON, ~120s stream) via `asyncio.timeout`; per-attempt timeout `min(remaining, REQUEST_TIMEOUT)`; global attempt cap; return 503/504 with `Retry-After` on exhaustion.

### H-4. A new `httpx.AsyncClient` is created for every upstream call

- **Files:** `services/llm.py:95`, `services/llm.py:161`, `services/azure_translator.py:69`
- **Failure:** every translation, detection, agent step, and tool call builds a fresh connection pool and pays TCP/TLS setup. `/v1/translate` with `"auto"` pays two handshakes; one agent turn can pay seven or more. This adds roughly 50–300ms per hop, churns sockets/file descriptors, and prevents keep-alive, HTTP/2, and pool limits.
- **Fix:** lifespan-owned shared clients per provider/base URL with explicit `httpx.Limits`, closed on shutdown and injectable for tests.

### H-5. Liveness and readiness are inverted

- **Files:** `routes/base.py:32-57`, `Dockerfile:27-31`, `.github/workflows/deploy_ai.yaml:95-106`
- **Failure:** with no provider keys, `/health` returns 200, Docker marks the container healthy, and deploy verification passes while every real request returns 503. Conversely, `/health/ready` returns 503 whenever optional Redis is down, although the cache fails open and translation still works — a Redis blip drains every replica behind a readiness-based load balancer.
- **Fix:** `/health/live` always 200; `/health/ready` returns 200 with `status: degraded` and per-dependency detail for optional Redis; reserve 503 for “no translation and no chat path”. Gate deploys and CI smoke tests on readiness.

### H-6. Conversation prompts and writes grow without a token/byte budget

- **Files:** `config.py:260-262`, `models.py:35`, `models.py:44-46`, `services/conversations.py:61-67`, `services/agent.py:287-291`, `services/assistant.py:38-43`
- **Failure:** 40 messages × 5,000 characters is ~200k characters (roughly 40–60k tokens) re-sent every turn. Each append loads, parses, rewrites, and stores the whole JSON — with Redis, a `GET` plus a `SET` of up to 200KB per message. The in-memory worst case is ~2GB; providers return context-length 400s that are treated as model failures.
- **Fix:** trim by characters/tokens with summarisation, lower the per-message cap, and use a Redis list (`RPUSH` + `LTRIM` + `EXPIRE`) so appends are O(1) and atomic.

### H-7. Client identity collapses behind a proxy

- **Files:** `middleware.py:103-104`, `Dockerfile:31`
- **Trigger:** deploy behind ALB, Nginx, or Docker Desktop.
- **Failure:** uvicorn only trusts `X-Forwarded-For` from `FORWARDED_ALLOW_IPS` (default `127.0.0.1`). Behind a proxy, `request.client.host` is the proxy for everyone, so all anonymous users share one 60 rpm bucket and one conversation owner. This causes global 429 storms, unfair quotas, and a weaker privacy boundary than `docs/USAGE.md:180-183` claims.
- **Fix:** set `--forwarded-allow-ips` to the proxy CIDRs, derive identity from a validated XFF only when the peer is trusted, prefer a validated API key, and test an XFF request through a trusted peer.

### H-8. The documented JSON error envelope has holes

- **Files:** `main.py:56-84`, `routes/translation.py:84-89`
- **Failure:** the custom handler is registered for `fastapi.HTTPException`, not `starlette.exceptions.HTTPException`, so routing 404/405 still return `{"detail": ...}`. Unhandled exceptions reach Starlette's plain-text 500 (`ValidationError` from long stored replies, malformed provider payloads, `/v1/detect` without the route-level guard). The custom handler also drops `exc.headers` (`WWW-Authenticate`, `Allow`), and 500s lack `X-Request-ID` and security headers.
- **Fix:** register handlers for Starlette `HTTPException` and generic `Exception`, preserve headers, attach request ID/security headers, add a machine-readable `code`, and add a guard to `detect_language_route()`.

---

## P1 — next iteration

| # | Severity | Finding | Files | Fix |
|---|---|---|---|---|
| M-1 | MEDIUM | Failed authentication bypasses rate limiting — repeated bad `X-API-Key` requests are unthrottled, enabling key guessing and log flooding. | `main.py:34-35`, `middleware.py:173-186` | Rate-limit outside auth, keyed by IP for unauthenticated requests. |
| M-2 | MEDIUM | Non-ASCII `X-API-Key` raises `TypeError` in `hmac.compare_digest` → unhandled 500. | `middleware.py:131-135` | Compare encoded bytes or reject non-ASCII with 401 before comparison. |
| M-3 | MEDIUM | API key stored in `localStorage`, while `/docs` loads CDN JavaScript without CSP; `'unsafe-inline'` is allowed on `/chat`. Same-origin script can steal the key. | `static/chat.html:117-121`, `middleware.py:219-220,232-233` | Keep keys in memory/session storage, self-host docs assets or add CSP + SRI, remove `'unsafe-inline'` where feasible. |
| M-4 | MEDIUM | `/metrics` and `/health/ready` are public and unrate-limited. `/metrics` discloses traffic/latency; readiness performs a live Redis `PING` per request and reveals provider config. | `middleware.py:26-36,183`, `routes/base.py:38-52` | Restrict metrics to a private listener/token, cache readiness briefly, rate-limit both by IP. |
| M-5 | MEDIUM | Authentication is silently disabled when `API_KEYS` is empty — the default in `docker-compose.yml`. Public port → unauthenticated paid quota and shared IP-based conversation ownership. | `config.py:296-298`, `middleware.py:175`, `docker-compose.yml:7-14` | Fail startup on non-loopback bind without keys, or require explicit `ALLOW_UNAUTHENTICATED=true`. |
| M-6 | MEDIUM | Agent cost amplification: 6 steps × 8 tool calls × 5,000-character translations, and no `max_tokens` on completions. | `services/agent.py:28,296-312,334-362`, `services/llm.py:231-233` | Set `max_tokens`, cap total translated characters/tool calls per request, add a per-client cost budget. |
| M-7 | MEDIUM | Streaming bypasses retry policy and has no overall deadline; a provider trickling tokens holds the stream indefinitely. | `services/llm.py:160-194` vs `89-124` | Retry before the first emitted token, add a total stream deadline, disable retry after output starts. |
| M-8 | MEDIUM | `/chat` does blocking `Path.read_text()` on the event loop, unauthenticated and unrate-limited; missing file → plain-text 500. | `routes/chat.py:176-179` | Cache the HTML at import/startup or `asyncio.to_thread`; handle `FileNotFoundError` with the envelope. |
| M-9 | MEDIUM | Streaming latency is measured at response start, not completion. `X-Process-Time-Ms`, `REQUEST_LATENCY`, and access logs under-report the slowest endpoint. | `middleware.py:148-161` | Instrument the ASGI `send` path until `more_body=False`, or wrap the body iterator; add TTFT metric. |
| M-10 | MEDIUM | CORS allows only GET/POST, but `DELETE /v1/chat/{id}` exists; no `expose_headers` for `X-Request-ID`, rate-limit, or `Retry-After`. | `main.py:40-46`, `routes/chat.py:168` | Add `DELETE` and `expose_headers`; add a preflight test. |
| M-11 | MEDIUM | Injected `httpx.Client` is mutated and its `base_url`/`timeout` are ignored; the documented injection path fails or leaks the API key to other hosts. | `clients/python/terngi/client.py:50-52` | Wrap/copy the client with the SDK base URL/timeout and send headers per request. |
| M-12 | MEDIUM | Long assistant replies (>5,000 chars) are stored, then rejected by `MemoryMessage` validation on `GET /v1/chat/{id}` — the conversation becomes unreadable. | `models.py:35`, `routes/chat.py:162-165` | Use a separate stored/response model without the request cap, or cap generated replies. |
| M-13 | MEDIUM | Conversations are created before source-language validation; invalid first turns leave empty conversations that consume the 10,000-item LRU/Redis keyspace. | `routes/chat.py:29-37`, `services/agent.py:275` | Validate languages before `create()`, persist only after a successful first turn, delete on failure. |
| M-14 | MEDIUM | Redis failure costs ~2s per operation and silently removes rate limiting (fail-open); Redis pool is unbounded. | `services/store.py:38-43,159-187`, `services/translator.py:32-44` | 200–500ms timeout, circuit breaker, process-local fallback limiter, `max_connections`, `redis_unavailable` metric. |

---

## P2 — quick wins, performance, hygiene

| # | Finding | Files | Recommendation |
|---|---|---|---|
| L-1 | Batch cache I/O is sequential (25 GETs + 25 SETs) with no single-flight; concurrent misses duplicate provider spend. | `services/translator.py:116-132` | `asyncio.gather` or `MGET`/`MSET`, deduplicate texts, per-key single-flight. |
| L-2 | `/v1/converse` serialises independent work: target translation can run in parallel with the LLM call. | `routes/conversation.py:39-65` | `asyncio.gather`; reuse the English translation where quality allows. |
| L-3 | Language detection is never cached and is repeated per agent turn; the detector prompt lists all 96 languages. | `services/languages.py:25-30`, `services/translator.py:165-177`, `services/agent.py:119,280` | Cache by content hash for 5–30 min; ask the LLM for language + translation in one call. |
| L-4 | SSE queue is unbounded, has no heartbeat, and `task.cancel()` is not awaited; a missing provider returns 200 with an `error` event instead of HTTP 503. | `routes/chat.py:99,139-147` | Bounded queue, 15s `: ping`, await cancellation, preflight provider availability. |
| L-5 | Configuration is import-time and unvalidated: `AGENT_MAX_STEPS=abc` crashes at import; negative `RATE_LIMIT_PER_MINUTE`/`MAX_REQUEST_BYTES` silently disable protections; unknown providers are ignored. | `config.py:16,230-301`, `main.py:26` | Validated Settings object in lifespan, fail fast with clear messages, log redacted effective config, warn on empty keys/negative limits. |
| L-6 | All providers exhausted returns 502 (gateway fault) instead of 503 + `Retry-After` for throttling/timeouts. | `services/llm.py:409`, `services/azure_translator.py:61-63` | Return 503 with `Retry-After`; reserve 502 for bad provider responses. |
| L-7 | Upstream error bodies logged verbatim (Azure full body, LLM first 500 chars); can echo PII and flood logs. | `services/llm.py:142`, `services/azure_translator.py:123` | Truncate and log status/error code only. |
| L-8 | API-key suffix (last four chars) logged; a nine-character key exposes four characters. | `services/keypool.py:12-14`, `services/llm.py:132`, `services/azure_translator.py:90,97` | Use a fixed-length SHA-256 fingerprint. |
| L-9 | Mutable supply-chain references: `python:3.12-slim`, Redis/llama.cpp tags; static AWS keys in deploy workflow. | `Dockerfile:1`, `docker-compose.yml:20,29`, `.github/workflows/deploy_ai.yaml:39-41` | Pin images by digest; use GitHub OIDC role assumption. |
| L-10 | MORENA published on `0.0.0.0:8080` without auth; Redis has no password and stores conversation content unencrypted. | `docker-compose.yml:43-44,19-22` | Bind MORENA to localhost/API network; require Redis AUTH/TLS on shared networks. |

### Additional small items

- `conversation_id` is used directly as a Redis key with no format/length validation (`models.py:122-124`, `services/conversations.py:32-34`). Constrain to 32-hex.
- `python-multipart` is unused in `requirements.txt:6` — remove or document.
- Translation cache default of 1,000 entries is small for 96 languages and a 1h TTL (`config.py:293-294`). Raise to 10k+ or bound by bytes.
- `_route_patterns` builds the OpenAPI schema on the first 401/429 (`metrics.py:71-78`). Precompute at startup.
- In-memory rate limiter has no global entry cap before the every-1,000-call sweep (`middleware.py:54-84`).
- Key-pool cooldowns are per process; with replicas, a revoked key is retried N times (`services/keypool.py:17-60`).
- `REDIS_URL` is not set in the deploy workflow, so state is per-container and lost on restart (`.github/workflows/deploy_ai.yaml`).
- `docker-compose.yml --profile morena` sets `MORENA_BASE_URL` but not `LLM_PROVIDERS=...,morena`, so MORENA is never selected (README `94-101` vs `config.py:230-232`).
- `docs/USAGE.md:67` omits the `storage` key that `routes/base.py:52` returns; the SDK lacks `converse` (`docs/USAGE.md:215`).
- `_finalise_answer` can return an untranslated answer if the model's translation is not a substring (`services/agent.py:241-247`). Return the last validated translation or re-translate.

---

## Test and coverage gaps

Runtime coverage is 95%, and the suite is broad on happy paths and provider fallback. The highest-risk failure paths are disproportionately in the 71 missed statements: `routes/translation.py:48-50,79-81` (error re-raise), `routes/chat.py:30,64-66,133-135,147` (validation, failure, stream cancellation), `services/conversations.py:42-43,65,76-77` (store failure, append race/expiry), `services/azure_translator.py:58,62-63,128-129,155-156,175-176` (cooling/malformed responses), `services/llm.py:174-175,228-229,248-249,251,344,346,396,419` (stream/model edge cases), and `services/store.py:114,123,134-135` (corrupt Redis values). The following are the P0 tests to add first; each should fail against the current implementation.

1. **`test_unhandled_exception_returns_json_error_envelope`** — `main.py:56-76`: assert JSON envelope + request ID for 500, not Starlette plain text. Current `tests/test_metrics.py:154-170` checks only status/counter.
2. **`test_chat_stream_disconnect_cancels_generation_and_skips_append`** — `routes/chat.py:139-147`: close the stream mid-token, assert upstream cancellation, no `done` event, no stored turn.
3. **`test_azure_403_rotates_key` / `test_azure_429_cools_key_until_retry_after`** — `services/azure_translator.py:89-107,134-137`: assert call order and that the cooled key is skipped next request. `tests/test_translation.py:152-162` asserts only the final 502.
4. **`test_stream_parse_failure_after_first_token_is_502_not_retried`** — `services/llm.py:392-398`: assert exactly one upstream call after output started.
5. **`test_sdk_chat_stream_maps_401_and_429`** — `clients/python/terngi/client.py:120-125`: the SDK stream path only has a happy-path test.
6. **`test_chat_append_failure_returns_503_envelope`** — `routes/chat.py:68-73,113-118`: storage failure after generation is untested (GET failure is covered).

Additional P1 gaps: rate-limit disabled/OPTIONS; 413 headers/request-ID/metrics; public `/health/ready` and `/docs` with keys set; CORS preflight; Azure all-keys-cooling and malformed 200/detect bodies; LLM 403, missing `choices`, empty-step failover, MORENA malformed content; agent per-step tool cap/multiple calls; empty conversation after failure; cache TTL=0 and language-scoped keys; corrupt Redis JSON; 20-message model caps; SDK non-JSON/list error bodies and invalid `Retry-After`; metrics route labels on 401; HSTS behind a proxy.

### Weak tests to tighten

- `tests/test_chat.py:104-107` — named “failed reply is not stored” but asserts only 503; the empty conversation created at `routes/chat.py:53` goes unchecked.
- `tests/test_translation.py:152-162` — all-keys-rejected asserts only 502; passes if rotation is broken.
- `tests/test_streaming.py:131` — `assert got[-1] == ("done", got[-1][1])` is self-referential.
- `tests/test_agent.py:161-191` — malformed-arguments case passes on a different “missing text” error.
- `tests/test_features.py:255-265` — asserts private `limiter._hits` and depends on the 1,000th call triggering `_sweep`.
- `tests/test_metrics.py:154-170` — adds `/test-boom` to the global app and never removes it; order-sensitive.
- `tests/test_llm.py:261-303` — `importlib.reload(config)` mutates the module used by every service.
- `tests/test_retry.py:34` — patches `azure_translator.asyncio.sleep`, i.e. global `asyncio.sleep`.
- `tests/test_client_sdk.py:184-191` — asserts private `_client` internals rather than behavior.

---

## What is already good

- Clear routes → services → providers layering and a consistent provider abstraction.
- Ordered provider/model/key fallback with cooldowns, jittered exponential backoff, and `Retry-After` parsing (`services/retry.py`).
- Hash-based, fixed-length cache keys; TTL + LRU; cache failures degrade instead of failing translation.
- Optional Redis, fail-open rate limiter, owner-scoped conversations with hashed owners, sliding TTLs.
- Metrics use route templates and bounded labels; body-size middleware is pure ASGI and correctly outermost; request IDs, security headers, and chunked-body limits exist.
- Application and validation errors share one envelope; validation details do not echo input; API keys are compared in constant time; secrets are not logged.
- Tests use `respx`/`fakeredis`, cover a 3.10–3.13 matrix in CI with an 85% coverage gate.
- Docker runs non-root with hash-locked dependencies; the image is ~200MB.

## Recommended execution order

**P0 (this week)**

1. Shared lifespan-owned HTTP clients with pool limits.
2. Request deadlines + global attempt cap + 503/504 with `Retry-After`.
3. Split liveness/readiness; make optional Redis `degraded`; gate deploy/CI on readiness.
4. Atomic Redis conversation appends + token/byte budget.
5. Trusted-proxy configuration and client-identity test.
6. Error handlers for Starlette 404/405 and generic 500s; preserve headers/request ID.

**P1 (this month)**

7. Rate-limit auth failures; encode-key comparison; remove key from `localStorage`; restrict metrics/readiness.
8. Bound the SSE queue, add heartbeats, await cancellation, preflight provider availability.
9. Cap agent prompt/tool/token budgets; set `max_tokens` everywhere.
10. Redis timeout/circuit breaker/connection limits; corruption handling.
11. Startup config validation and empty-`API_KEYS` guard.
12. Add the six P0 tests above and the P1 middleware/agent/cache cases.

**P2 (next quarter)**

13. Idempotency keys for chat, `expose_headers`, gzip/ETag, `X-RateLimit-Reset`.
14. Async SDK, OpenAPI-generated models, fix MORENA/docs/deploy drift.
15. Pin images/actions, move key cooldowns to Redis when replicas > 1, structured request-scoped logs.

---

*Generated by ECC on 2026-10-23. Findings come from static analysis by the ECC review roles; the verification baseline above records the runtime gates. The P0 test list identifies failure paths that the current 95% line coverage does not exercise.*
