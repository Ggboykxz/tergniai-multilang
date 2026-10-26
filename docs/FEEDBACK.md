# Translation feedback

Terngi AI can collect optional 👍/👎 ratings so that native speakers and users can help
build the open evaluation set described in issue #14.

## Privacy and consent

Feedback is **only stored when the request explicitly sets `"consent": true`**. Without that
flag the API returns `400` and writes nothing.

When consent is given, the following values are stored:

- the source text and the translation (or chat reply) being rated
- source and target language codes
- the provider name supplied by the client
- the rating (`good` or `bad`) and an optional correction
- a random feedback id, a UTC timestamp and the consent flag

API keys, IP addresses and other client identifiers are **not** stored in feedback. Do not
submit personal, confidential or sensitive text: accepted feedback may be published as part
of the open evaluation set. Users should only opt in after seeing this notice.

Before anything is published, the maintainers review the records and remove personal data.
Publication is never automatic: a stored record is a candidate for review, not a promise
that its text will appear in the evaluation set.

## Storage

Feedback is append-only. Records are never updated or deleted by the API.

- With `REDIS_URL` set, records are appended to the Redis list
  `<REDIS_PREFIX>feedback` and are shared by every replica. **Use Redis in production**:
  a JSONL file lives inside the container and is lost on the next deploy.
- Without Redis, records are appended as JSON Lines to `FEEDBACK_FILE` (default
  `feedback.jsonl`). Mount a persistent volume for this file in production and keep it out of
  version control.

`FEEDBACK_MAX_RECORDS` (default `10000`) bounds the store. With Redis, the oldest records
are dropped when the list reaches the cap. With a JSONL file, new records are refused with
`507` until the operator rotates or removes the file. `0` disables the cap, which is not
recommended for a public deployment.

The endpoint is under `/v1`, so it uses the same API-key authentication and per-client rate
limit as the other API routes.

## API

```bash
curl -X POST http://localhost:8000/v1/feedback \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: <your-key>' \
  -d '{
    "source_text": "Welcome to Terngi",
    "translated_text": "Ẹ káàbọ̀ sí Terngi",
    "from_language": "en",
    "to_language": "yo",
    "provider": "chat",
    "rating": "good",
    "consent": true
  }'
```

A request may also include `"correction": "a better translation"`. The response is
`{"status": "stored"}`.

## Exporting the evaluation set

`scripts/export_feedback.py` reads the same storage and writes JSON Lines with the fields
used by the evaluation set: `source`, `reference`, `from_language` and `to_language`.

```bash
python scripts/export_feedback.py --output eval/feedback.jsonl
```

By default it exports good ratings and bad ratings that include a correction. Bad ratings
without a correction are skipped because they do not contain a usable reference. Pass
`--all` to export every consented record with its `rating` and `correction` fields; the
default is safer for building a reference set.
