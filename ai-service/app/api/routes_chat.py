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
