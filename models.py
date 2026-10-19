"""
Pydantic models for the Terngi Translation API
"""

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from config import MAX_BATCH_SIZE, MAX_CONTENT_LENGTH, MAX_MEMORY_MESSAGES

Text = Annotated[str, Field(min_length=1, max_length=MAX_CONTENT_LENGTH)]


class TranslationRequest(BaseModel):
    """Request model for translation endpoints"""

    content: Text
    from_language: str = Field(..., description='Language code, or "auto" to detect it')
    to_language: str


class TranslationResponse(BaseModel):
    """Response model for translation endpoints"""

    translated_text: str
    from_language: str
    to_language: str
    original_text: str


class MemoryMessage(BaseModel):
    """A previous turn in the conversation (system messages are not allowed)"""

    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=MAX_CONTENT_LENGTH)


class ConversationRequest(BaseModel):
    """Request model for conversation endpoints"""

    content: Text
    from_language: str = Field(..., description='Language code, or "auto" to detect it')
    to_language: str
    memory_context: Optional[List[MemoryMessage]] = Field(
        default=None, max_length=MAX_MEMORY_MESSAGES
    )


class ConversationResponse(BaseModel):
    """Response model for conversation endpoints"""

    translated_text: str
    from_language: str
    to_language: str
    original_text: str
    response: Optional[str] = None


class BatchTranslationRequest(BaseModel):
    """Request model for translating several texts at once"""

    texts: List[Text] = Field(..., min_length=1, max_length=MAX_BATCH_SIZE)
    from_language: str = Field(..., description='Language code, or "auto" to detect it')
    to_language: str


class BatchTranslationResponse(BaseModel):
    """Response model for batch translation"""

    translations: List[str]
    from_language: str
    to_language: str


class DetectionRequest(BaseModel):
    """Request model for language detection"""

    content: Text


class DetectionResponse(BaseModel):
    """Response model for language detection"""

    language: str
    language_name: Optional[str] = None
    score: float
    is_supported: bool
