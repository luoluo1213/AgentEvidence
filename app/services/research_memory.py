from __future__ import annotations

import uuid
import logging
from typing import Protocol

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.research_types import ResearchTask
from app.models.entities import ChatMessage, ChatSession, ResearchLongTermMemory
from app.schemas.dtos import AiMessage
from app.services.memory import RedisShortTermMemoryStore, summarize_history_for_memory
from app.services.privacy import PrivacySanitizer
from app.services.research_pipeline import FinalResearchResult


logger = logging.getLogger(__name__)


class ConversationContext(BaseModel):
    original_query: str
    contextualized_query: str
    recent_messages: list[AiMessage] = Field(default_factory=list)
    session_summary: str = ""
    long_term_memories: list[str] = Field(default_factory=list)


class ResearchMemory(Protocol):
    def build_context(self, user_id: int | None, session_id: str, query: str) -> ConversationContext: ...

    def update(
        self,
        user_id: int | None,
        session_id: str,
        turn_id: str,
        query: str,
        result: FinalResearchResult,
    ) -> None: ...


class NullResearchMemory:
    """In-process compatibility memory for callers that do not configure persistence."""

    def __init__(self):
        self._sessions: dict[str, list[AiMessage]] = {}

    def build_context(self, user_id: int | None, session_id: str, query: str) -> ConversationContext:
        recent = list(self._sessions.get(session_id, [])) if session_id else []
        summary = summarize_history_for_memory(recent, max_chars=500) if recent else ""
        return ConversationContext(
            original_query=query,
            contextualized_query=_contextualize(query, recent, summary, []),
            recent_messages=recent,
            session_summary=summary,
        )

    def update(
        self,
        user_id: int | None,
        session_id: str,
        turn_id: str,
        query: str,
        result: FinalResearchResult,
    ) -> None:
        if not session_id:
            return
        history = self._sessions.setdefault(session_id, [])
        history.extend((AiMessage(role="user", content=query), AiMessage(role="assistant", content=result.answer)))
        self._sessions[session_id] = history[-40:]


class ResearchMemoryService:
    """L1/L2 research memory using the application's Redis and SQL infrastructure."""

    def __init__(self, db: Session, settings, redis_store: RedisShortTermMemoryStore | None = None):
        self.db = db
        self.settings = settings
        self.redis = redis_store if redis_store is not None else RedisShortTermMemoryStore(settings)
        self.privacy = PrivacySanitizer()

    def build_context(self, user_id: int | None, session_id: str, query: str) -> ConversationContext:
        recent = self._load_session_messages(user_id, session_id)
        summary = self.redis.load_summary(session_id) if session_id else ""
        if not summary and recent:
            summary = summarize_history_for_memory(recent, max_chars=self.settings.memory_summary_max_chars)
        memories = self.load_long_term(user_id)
        return ConversationContext(
            original_query=query,
            contextualized_query=_contextualize(query, recent, summary, memories),
            recent_messages=recent,
            session_summary=summary,
            long_term_memories=memories,
        )

    def update(
        self,
        user_id: int | None,
        session_id: str,
        turn_id: str,
        query: str,
        result: FinalResearchResult,
    ) -> None:
        sanitized_query = self.privacy.sanitize(query)
        sanitized_answer = self.privacy.sanitize(result.answer)
        session = self._session(user_id, session_id)
        if session is not None:
            try:
                self.db.add_all([
                    ChatMessage(user_id=session.user_id, session_id=session.id, role="user", content=sanitized_query),
                    ChatMessage(user_id=session.user_id, session_id=session.id, role="assistant", content=sanitized_answer),
                ])
                session.touch()
                self.db.add(session)
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                logger.warning("SQL session memory write unavailable: %s", exc)
        if session_id:
            self.redis.append(session_id, "user", sanitized_query)
            self.redis.append(session_id, "assistant", sanitized_answer)
            recent = self._load_session_messages(user_id, session_id)
            summary = summarize_history_for_memory(recent, max_chars=self.settings.memory_summary_max_chars)
            self.redis.save_summary(session_id, summary)
        self._save_stable_memories(user_id, session_id, turn_id, result.task)

    def load_long_term(self, user_id: int | None, limit: int = 12) -> list[str]:
        if user_id is None:
            return []
        try:
            rows = (
                self.db.query(ResearchLongTermMemory)
                .filter(ResearchLongTermMemory.user_id == user_id)
                .order_by(ResearchLongTermMemory.updated_at.desc())
                .limit(limit)
                .all()
            )
        except Exception as exc:
            self.db.rollback()
            logger.warning("SQL long-term memory read unavailable: %s", exc)
            return []
        return [f"{row.kind}: {row.content}" for row in rows]

    def _load_session_messages(self, user_id: int | None, session_id: str) -> list[AiMessage]:
        if not session_id:
            return []
        cached = self.redis.load_recent(session_id)
        if cached:
            return cached[-self.settings.redis_memory_max_messages :]
        session = self._session(user_id, session_id)
        if session is None:
            return []
        try:
            rows = (
                self.db.query(ChatMessage)
                .filter(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(self.settings.redis_memory_max_messages)
                .all()
            )
        except Exception as exc:
            self.db.rollback()
            logger.warning("SQL session memory read unavailable: %s", exc)
            return []
        return self.redis.messages_from_rows(list(reversed(rows)))

    def _session(self, user_id: int | None, session_id: str) -> ChatSession | None:
        if not session_id:
            return None
        try:
            query = self.db.query(ChatSession).filter(ChatSession.public_id == session_id)
            if user_id is not None:
                query = query.filter(ChatSession.user_id == user_id)
            return query.first()
        except Exception as exc:
            self.db.rollback()
            logger.warning("SQL chat session lookup unavailable: %s", exc)
            return None

    def _save_stable_memories(
        self,
        user_id: int | None,
        session_id: str,
        turn_id: str,
        task: ResearchTask,
    ) -> None:
        if user_id is None:
            return
        candidates: list[tuple[str, str]] = []
        for entity in task.entities:
            value = self.privacy.sanitize(entity).strip()
            if _stable_value(value):
                candidates.append(("entity", value[:240]))
        if candidates and task.research_questions:
            topic = self.privacy.sanitize(task.research_questions[0]).strip()
            if _stable_value(topic):
                candidates.append(("research_topic", topic[:500]))
        changed = False
        try:
            for kind, content in candidates:
                exists = self.db.query(ResearchLongTermMemory).filter(
                    ResearchLongTermMemory.user_id == user_id,
                    ResearchLongTermMemory.kind == kind,
                    ResearchLongTermMemory.content == content,
                ).first()
                if exists:
                    continue
                self.db.add(ResearchLongTermMemory(
                    memory_id=uuid.uuid4().hex,
                    user_id=user_id,
                    kind=kind,
                    content=content,
                    source_session_id=session_id,
                    source_turn_id=turn_id,
                ))
                changed = True
            if changed:
                self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning("SQL long-term memory write unavailable: %s", exc)


def _contextualize(query: str, recent: list[AiMessage], summary: str, memories: list[str]) -> str:
    if not recent and not memories:
        return query
    parts = ["Use the supplied conversation memory only to resolve references in the current research question."]
    if summary:
        parts.append(f"Session summary:\n{summary}")
    if recent:
        transcript = "\n".join(f"{item.role}: {item.content}" for item in recent[-6:])
        parts.append(f"Recent conversation:\n{transcript}")
    if memories:
        parts.append("Stable research context:\n" + "\n".join(memories[-8:]))
    parts.append(f"Current research question:\n{query}")
    return "\n\n".join(parts)


def _stable_value(value: str) -> bool:
    normalized = " ".join((value or "").split())
    return 2 <= len(normalized) <= 500 and "[已脱敏]" not in normalized
