"""
Append-only storage for opt-in translation feedback

Records are written either to Redis (when REDIS_URL is set) or to a JSONL file. Feedback is
never updated or deleted by the API. API keys and client identifiers are not part of a
record; callers must explicitly consent before anything is stored.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

import config
from services.store import get_redis, using_redis

_file_lock = asyncio.Lock()


class FeedbackError(Exception):
    """Feedback storage could not be reached"""


def _redis_key() -> str:
    return f"{config.REDIS_PREFIX}feedback"


def _append_file(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.write("\n")


def _read_file(path: Path) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return handle.read().splitlines()


async def append(record: Dict[str, Any]) -> str:
    """Store one feedback record and return its generated id"""
    feedback_id = uuid.uuid4().hex
    stored = {
        "id": feedback_id,
        "created_at": datetime.now(UTC).isoformat(),
        **record,
    }
    line = json.dumps(stored, ensure_ascii=False)

    if using_redis():
        try:
            await get_redis().rpush(_redis_key(), line)
        except Exception as e:
            raise FeedbackError(str(e)) from e
        return feedback_id

    path = Path(config.FEEDBACK_FILE)
    try:
        async with _file_lock:
            await asyncio.to_thread(_append_file, path, line)
    except OSError as e:
        raise FeedbackError(str(e)) from e
    return feedback_id


async def load_records() -> List[Dict[str, Any]]:
    """Read every stored record, oldest first (used by the evaluation export script)"""
    if using_redis():
        try:
            lines = await get_redis().lrange(_redis_key(), 0, -1)
        except Exception as e:
            raise FeedbackError(str(e)) from e
    else:
        try:
            lines = await asyncio.to_thread(_read_file, Path(config.FEEDBACK_FILE))
        except OSError as e:
            raise FeedbackError(str(e)) from e

    records: List[Dict[str, Any]] = []
    for line in lines:
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def clear() -> None:
    """Remove the local file (tests only; Redis data is left untouched)"""
    if using_redis():
        return
    Path(config.FEEDBACK_FILE).unlink(missing_ok=True)
