from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.schemas.dtos import AiMessage
from app.services.research_pipeline import FinalResearchResult


class ConversationContext(BaseModel):
    original_query: str
    contextualized_query: str
    recent_messages: list[AiMessage] = Field(default_factory=list)
    session_summary: str = ""
    long_term_memories: list[str] = Field(default_factory=list)


class ResearchMemory(Protocol):
    def build_context(
        self,
        user_id: int | None,
        session_id: str,
        query: str,
    ) -> ConversationContext:
        ...

    def update(
        self,
        user_id: int | None,
        session_id: str,
        turn_id: str,
        query: str,
        result: FinalResearchResult,
    ) -> None:
        ...


class NullResearchMemory:
    """
    Default in-memory/no-persistence implementation.

    Used when Redis/MySQL research memory is not configured.
    """

    def build_context(
        self,
        user_id: int | None,
        session_id: str,
        query: str,
    ) -> ConversationContext:
        return ConversationContext(
            original_query=query,
            contextualized_query=query,
        )

    def update(
        self,
        user_id: int | None,
        session_id: str,
        turn_id: str,
        query: str,
        result: FinalResearchResult,
    ) -> None:
        return None