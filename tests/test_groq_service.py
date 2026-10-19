"""
Tests for the Groq service
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import config
from services import groq_service


def fake_client(reply="Hello!", error=None):
    create = AsyncMock(
        side_effect=error,
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]
        ),
    )
    client = MagicMock()
    client.chat.completions.create = create
    return client, create


@pytest.mark.asyncio
async def test_get_response_builds_messages(monkeypatch):
    client, create = fake_client()
    monkeypatch.setattr(groq_service, "get_client", lambda: client)

    reply = await groq_service.get_response(
        "Hi",
        [
            {"role": "user", "content": "earlier"},
            {"role": "system", "content": "should be dropped"},
        ],
    )

    assert reply == "Hello!"
    messages = create.await_args.kwargs["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "user"]
    assert messages[0]["content"] == config.GROQ_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_get_response_wraps_errors(monkeypatch):
    client, _ = fake_client(error=RuntimeError("boom"))
    monkeypatch.setattr(groq_service, "get_client", lambda: client)

    with pytest.raises(HTTPException) as exc_info:
        await groq_service.get_response("Hi")

    assert exc_info.value.status_code == 502


def test_get_client_without_key(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(groq_service, "_groq_client", None)

    with pytest.raises(HTTPException) as exc_info:
        groq_service.get_client()

    assert exc_info.value.status_code == 503
