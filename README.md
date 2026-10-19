# Terngi AI — Translation & Conversation API

[![CI](https://github.com/Terngi-AI/tergniai-multilang/actions/workflows/ci.yml/badge.svg)](https://github.com/Terngi-AI/tergniai-multilang/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)

A FastAPI service that translates between **English, Yoruba, Hausa and Igbo** and holds
multilingual conversations with an LLM. Translation is powered by
[Azure Translator](https://learn.microsoft.com/azure/ai-services/translator/) and responses
by [Groq](https://groq.com/) (`openai/gpt-oss-120b` by default).

## Features

- **Translate** text between any two supported languages, one at a time or in batches
- **Auto-detect** the source language — pass `"from_language": "auto"` to any endpoint
- **Converse** in any supported language; the reply comes back in the target language,
  with optional multi-turn memory (`memory_context`)
- **Translation cache** (in-memory TTL/LRU) to save Azure quota on repeated phrases
- **API-key authentication** (`X-API-Key`) and **per-client rate limiting**
- **Request IDs** (`X-Request-ID`) and timing headers for tracing
- Input validation, upstream timeouts and consistent JSON error responses
- Liveness (`/health`) and readiness (`/health/ready`) probes
- Docker image with a health check, running as a non-root user

## Quick start

### Prerequisites

- Python 3.10+
- An Azure Translator key and a Groq API key

### Run locally

```bash
git clone https://github.com/Terngi-AI/tergniai-multilang.git
cd tergniai-multilang
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env   # then fill in your keys
uvicorn main:app --reload
```

Open http://localhost:8000/docs for the interactive API docs.

### Run with Docker

```bash
docker build -t terngi-ai .
docker run --rm -p 8000:8000 --env-file .env terngi-ai
```

## Configuration

All configuration comes from environment variables (see [`.env.example`](.env.example)).

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_TRANSLATOR_KEY` | yes | — | Azure Translator subscription key |
| `AZURE_TRANSLATOR_ENDPOINT` | no | `https://api.cognitive.microsofttranslator.com` | Translator endpoint |
| `AZURE_TRANSLATOR_LOCATION` | no | `global` | Azure resource region |
| `GROQ_API_KEY` | yes (for `/v1/converse`) | — | Groq API key |
| `GROQ_MODEL` | no | `openai/gpt-oss-120b` | Groq model ID |
| `REQUEST_TIMEOUT` | no | `30` | Upstream timeout in seconds |
| `MAX_CONTENT_LENGTH` | no | `5000` | Max characters per message |
| `MAX_MEMORY_MESSAGES` | no | `20` | Max turns in `memory_context` |
| `API_KEYS` | no | *(auth disabled)* | Comma-separated client keys accepted in `X-API-Key` |
| `RATE_LIMIT_PER_MINUTE` | no | `60` | Requests per minute per client; `0` disables |
| `CACHE_TTL_SECONDS` | no | `3600` | Translation cache lifetime; `0` disables |
| `CACHE_MAX_ITEMS` | no | `1000` | Max cached translations |
| `MAX_BATCH_SIZE` | no | `25` | Max texts per batch request |
| `MAX_BATCH_CHARACTERS` | no | `50000` | Max total characters per batch |
| `CORS_ORIGINS` | no | *(disabled)* | Comma-separated allowed origins |
| `LOG_LEVEL` | no | `INFO` | Python log level |

The app starts without keys; endpoints that need a missing key return `503`.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | API info and supported languages |
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (are upstream keys configured?) |
| `GET` | `/v1/languages` | Supported language codes |
| `POST` | `/v1/translate` | Translate text |
| `POST` | `/v1/translate/batch` | Translate up to 25 texts in one request |
| `POST` | `/v1/detect` | Detect the language of a text |
| `POST` | `/v1/converse` | Translate and get an LLM reply |

### Authentication & rate limits

When `API_KEYS` is set, every `/v1/*` endpoint except `/v1/languages` requires an
`X-API-Key` header. Each client (API key, or IP address when no key is sent) may make
`RATE_LIMIT_PER_MINUTE` requests per minute. Responses include `X-RateLimit-Limit` and
`X-RateLimit-Remaining`; when exceeded you get `429` with a `Retry-After` header.

> The cache and rate limiter are in-memory, so each server process keeps its own state.
> Run behind a shared limiter (e.g. your API gateway) if you scale out to many replicas.

### Translate

```bash
curl -X POST http://localhost:8000/v1/translate \
  -H 'Content-Type: application/json' \
  -d '{"content": "Good morning", "from_language": "en", "to_language": "yo"}'
```

### Batch translate

```bash
curl -X POST http://localhost:8000/v1/translate/batch \
  -H 'Content-Type: application/json' -H 'X-API-Key: <your-key>' \
  -d '{"texts": ["Good morning", "Thank you"], "from_language": "en", "to_language": "ig"}'
```

### Detect language

```bash
curl -X POST http://localhost:8000/v1/detect \
  -H 'Content-Type: application/json' \
  -d '{"content": "Ina kwana?"}'
# {"language": "ha", "language_name": "Hausa", "score": 1.0, "is_supported": true}
```

### Converse

```bash
curl -X POST http://localhost:8000/v1/converse \
  -H 'Content-Type: application/json' \
  -d '{
        "content": "Ina kwana?",
        "from_language": "auto",
        "to_language": "en",
        "memory_context": [
          {"role": "user", "content": "My name is Ada"},
          {"role": "assistant", "content": "Nice to meet you, Ada!"}
        ]
      }'
```

Errors use one shape:

```json
{"error": true, "message": "Target language 'fr' not supported. ...", "status_code": 400}
```

## Project layout

```
main.py              FastAPI app and error handlers
middleware.py        Request IDs, API-key auth and rate limiting
config.py            Settings loaded from environment variables
models.py            Pydantic request/response models
routes/              HTTP endpoints
services/            Azure Translator, Groq, cache and language helpers
tests/               Pytest suite (upstream services are mocked)
```

## Development

```bash
pytest --cov          # tests + coverage
ruff check . && ruff format .
mypy .
pre-commit install    # run checks automatically on every commit
```

CI runs lint, type checks, tests on Python 3.10–3.13, a Docker smoke test, secret scanning
and a dependency audit on every pull request.

## Contributing

Contributions are welcome — new languages, bug fixes, docs and tests. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md).
Report security issues privately as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
