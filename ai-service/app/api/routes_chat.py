"""POST /api/v1/chat -- the VaidyaAI chatbot (owner, 2026-10-09).

Thin HTTP wrapper; all logic lives in `app.services.chatbot`.

AUTH: the service-key dependency, like every other /api/v1 route --
`tests/test_auth.py` walks the route tree and fails on any route without it.
The only caller is the Node backend, which does the user's sign-in, the
ownership check on a report, and the per-user rate limit.

THE MODEL IS A DEPENDENCY: `get_chat_llm` returns the OpenRouter client, or
None when no OpenRouter key is configured (the chat then answers
"unavailable"). It never returns the Gemini client -- see the service header.
Overridden in tests.
"""

from __future__ import annotations

import functools
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.core.auth import require_service_key
from app.services.chatbot import (
    MAX_QUESTION_CHARS,
    ChatAnswer,
    ReportContext,
    answer_question,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["chat"],
    dependencies=[Depends(require_service_key)],
)


def get_chat_llm(settings: Settings = Depends(get_settings)) -> Any:
    """OpenRouter's text client, or None. Never Gemini's."""
    if not settings.openrouter_available:
        return None
    from app.services.openrouter_text import build_openrouter_client

    return build_openrouter_client(settings)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    report: Optional[ReportContext] = Field(
        default=None,
        description="One report's results, sent only from that report's dashboard.",
    )


class ChatResponse(BaseModel):
    success: bool = True
    data: ChatAnswer


@router.post("/chat", response_model=ChatResponse, summary="Answer one chat question")
async def chat(payload: ChatRequest, llm: Any = Depends(get_chat_llm)) -> ChatResponse:
    result = await run_in_threadpool(
        functools.partial(answer_question, payload.question, report=payload.report, llm=llm)
    )
    return ChatResponse(success=True, data=result)


__all__ = ["router", "get_chat_llm"]
