"""
Groq language model service for the Terngi Translation API
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from groq import AsyncGroq

import config
import metrics

logger = logging.getLogger(__name__)

_groq_client: Optional[AsyncGroq] = None


def get_client() -> AsyncGroq:
    """Create the Groq client lazily so the app can start without a key"""
    global _groq_client
    if _groq_client is None:
        if not config.GROQ_API_KEY:
            raise HTTPException(status_code=503, detail="Language model service is not configured")
        # The SDK retries 408/409/429/5xx and connection errors itself, with
        # exponential backoff, jitter and Retry-After support.
        _groq_client = AsyncGroq(
            api_key=config.GROQ_API_KEY,
            timeout=config.REQUEST_TIMEOUT,
            max_retries=config.UPSTREAM_MAX_RETRIES,
        )
    return _groq_client


async def get_response(content: str, memory_context: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Get response from Groq LLM (always in English)

    Args:
        content: User message content (in English)
        memory_context: Optional conversation history for context

    Returns:
        LLM response in English
    """
    # Format conversation history
    messages: List[Dict[str, Any]] = []

    # Add system prompt with instructions
    messages.append({"role": "system", "content": config.GROQ_SYSTEM_PROMPT})

    # Add memory context if provided (only user/assistant turns are allowed)
    if memory_context:
        for message in memory_context:
            if message.get("role") in ("user", "assistant") and "content" in message:
                messages.append({"role": message["role"], "content": message["content"]})

    # Add the current user message
    messages.append({"role": "user", "content": content})

    client = get_client()

    # Call Groq API
    try:
        with metrics.track_upstream("groq"):
            completion = await client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.7,
                max_tokens=1024,
            )
    except Exception as e:
        logger.exception("Error calling Groq")
        raise HTTPException(
            status_code=502, detail="Error connecting to language model service"
        ) from e

    # Extract and return the response
    return completion.choices[0].message.content or ""
