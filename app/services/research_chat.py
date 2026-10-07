from __future__ import annotations

import logging
from collections.abc import Callable, Iterator

from sqlalchemy.orm import Session

from app.agents.events import AgentEventType
from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.harness import resolve_chat_session
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings, settings_for_research_llm
from app.models.entities import UserAccount
from app.schemas.dtos import ResearchChatRequest
from app.services.ai import AiClient
from app.services.chat import sse
from app.services.knowledge import KnowledgeService
from app.services.research_memory import ResearchMemoryService
from app.services.research_runtime import ResearchEventDrivenRuntime, ResearchRuntimeRun


logger = logging.getLogger(__name__)
RuntimeFactory = Callable[[Session, Settings], ResearchEventDrivenRuntime]


class ResearchChatService:
    def __init__(self, db: Session, settings: Settings, runtime_factory: RuntimeFactory | None = None):
        self.db = db
        self.settings = settings
        self.runtime_factory = runtime_factory or build_research_runtime

    def stream_chat(self, user: UserAccount, request: ResearchChatRequest) -> Iterator[str]:
        session_id = request.session_id or ""
        try:
            session = resolve_chat_session(self.db, user, request.session_id, request.message.strip())
            session_id = session.public_id
            yield sse("session", {"session_id": session_id})
            runtime = self.runtime_factory(self.db, self.settings)
            run = runtime.run(
                request.message,
                user_id=user.id,
                session_id=session_id,
            )
            if run.final_result is None:
                raise RuntimeError("research runtime completed without a final result")
            yield from _agent_events(run)
            result = run.final_result
            yield sse("final", {
                "session_id": session_id,
                "answer": result.answer,
                "verification": result.verification.model_dump(),
                "sources": result.sources,
            })
        except Exception as exc:
            logger.exception("Research SSE turn failed for session=%s", session_id or "unresolved")
            yield sse("error", {
                "session_id": session_id or None,
                "error": "research_runtime_failed",
                "error_type": type(exc).__name__,
            })
        finally:
            yield sse("done", {"session_id": session_id or None})


def build_research_runtime(db: Session, settings: Settings) -> ResearchEventDrivenRuntime:
    from app.research_harness.harness import ResearchHarness

    client = AiClient(settings_for_research_llm(settings))
    harness = ResearchHarness.from_settings(settings)
    return ResearchEventDrivenRuntime(
        TaskAnalyzerAgent(harness.wrap_client(client, stage="analysis", agent="TaskAnalyzer")),
        ResearchAgent(
            KnowledgeService(db, settings),
            top_k=settings.research_retrieval_top_k,
            max_evidence_items=settings.research_max_evidence_items,
        ),
        harness.wrap_draft_generator(ResearchDraftGenerator(harness.wrap_client(client, stage="draft", agent="DraftAgent"))),
        EvidenceVerifier(harness.wrap_client(client, stage="verification", agent="EvidenceVerifier")),
        settings,
        ResearchMemoryService(db, settings),
    )


def _agent_events(run: ResearchRuntimeRun) -> Iterator[str]:
    for event in run.board.events:
        if event.type != AgentEventType.TASK_CLOSED:
            continue
        yield sse("agent_event", {
            "agent": event.actor,
            "task_id": event.task_id,
            "status": "completed",
        })
