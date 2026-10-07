from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from typing import Any

from app.agents.coordinator import EventDrivenCoordinator
from app.agents.events import (
    AgentArtifact,
    AgentEvent,
    AgentEventType,
    AgentTask,
    AgentTurnResult,
    CollaborationBlackboard,
    TaskPriority,
    TaskStatus,
)
from app.agents.registry import AgentDecision, AgentProfile, AgentRegistry
from app.agents.research_draft_generator import ResearchDraft
from app.agents.research_types import EvidencePool, EvidenceVerificationResult, ResearchTask
from app.services.research_pipeline import FinalResearchResult, build_final_research_result
from app.services.research_memory import ConversationContext, NullResearchMemory


RESEARCH_TASKS = (
    ("task:research:memory_context", "MemoryAgent", "memory_context", "conversation_context", ()),
    (
        "task:research:analysis",
        "TaskAnalyzer",
        "task_analysis",
        "research_task",
        ("task:research:memory_context",),
    ),
    ("task:research:evidence", "ResearchAgent", "research", "evidence_pool", ("task:research:analysis",)),
    ("task:research:draft", "DraftAgent", "draft", "research_draft", ("task:research:evidence",)),
    (
        "task:research:verification",
        "EvidenceVerifier",
        "verification",
        "evidence_verification",
        ("task:research:draft",),
    ),
    (
        "task:research:memory_update",
        "MemoryAgent",
        "memory_update",
        "memory_update",
        ("task:research:verification",),
    ),
)


@dataclass(frozen=True)
class ResearchRuntimeRun:
    board: CollaborationBlackboard
    final_result: FinalResearchResult | None


@dataclass(frozen=True)
class ResearchCollaborationBlackboard(CollaborationBlackboard):
    """Preserve the claimed task snapshot when the shared protocol closes it."""

    def apply_turn_result(self, task: AgentTask, agent_name: str, result: AgentTurnResult) -> CollaborationBlackboard:
        claimed_task = self.tasks.get(task.id, task)
        return super().apply_turn_result(claimed_task, agent_name, result)


class ResearchWorker:
    task_kind: str
    artifact_kind: str

    def __init__(self, name: str, task_kind: str, artifact_kind: str):
        self.profile = AgentProfile(name=name)
        self.task_kind = task_kind
        self.artifact_kind = artifact_kind

    def decide(self, task: AgentTask, board: CollaborationBlackboard) -> AgentDecision:
        if task.metadata.get("kind") != self.task_kind:
            return AgentDecision(False, reason="task belongs to another research worker")
        if board.latest_artifact(self.artifact_kind) is not None:
            return AgentDecision(False, reason=f"{self.artifact_kind} artifact already exists")
        return AgentDecision(True, 1.0, f"{self.profile.name} claims {self.task_kind}")

    def act(self, task: AgentTask, board: CollaborationBlackboard) -> AgentTurnResult:
        from app.research_harness.errors import ProviderError

        try:
            value = self.execute(board)
            return AgentTurnResult(artifacts=(AgentArtifact(
                id=f"artifact:{self.artifact_kind}:{uuid.uuid4().hex[:12]}",
                owner=self.profile.name,
                kind=self.artifact_kind,
                payload={"value": value},
                task_id=task.id,
                metadata={"pythonType": type(value).__name__},
            ),))
        except ProviderError:
            raise
        except Exception as exc:
            return AgentTurnResult(
                close_task=False,
                events=(AgentEvent(
                    type=AgentEventType.REVISION_REQUESTED,
                    actor=self.profile.name,
                    task_id=task.id,
                    message="research worker failed without publishing an artifact",
                    metadata={"errorType": type(exc).__name__},
                ),),
            )

    def execute(self, board: CollaborationBlackboard) -> Any:
        raise NotImplementedError


class TaskAnalyzerWorker(ResearchWorker):
    def __init__(self, analyzer):
        super().__init__("TaskAnalyzer", "task_analysis", "research_task")
        self.analyzer = analyzer

    def execute(self, board: CollaborationBlackboard) -> ResearchTask:
        context = _artifact_value(board, "conversation_context", ConversationContext)
        return self.analyzer.analyze(query_for_analysis(context))


class MemoryContextWorker(ResearchWorker):
    def __init__(self, memory):
        super().__init__("MemoryAgent", "memory_context", "conversation_context")
        self.memory = memory

    def execute(self, board: CollaborationBlackboard) -> ConversationContext:
        return self.memory.build_context(board.user_id, board.session_id, board.user_input)


class ResearchAgentWorker(ResearchWorker):
    def __init__(self, research_agent):
        super().__init__("ResearchAgent", "research", "evidence_pool")
        self.research_agent = research_agent

    def execute(self, board: CollaborationBlackboard) -> EvidencePool:
        task = _artifact_value(board, "research_task", ResearchTask)
        return self.research_agent.research(task)


class DraftAgentWorker(ResearchWorker):
    def __init__(self, draft_generator):
        super().__init__("DraftAgent", "draft", "research_draft")
        self.draft_generator = draft_generator

    def execute(self, board: CollaborationBlackboard) -> ResearchDraft:
        task = _artifact_value(board, "research_task", ResearchTask)
        evidence_pool = _artifact_value(board, "evidence_pool", EvidencePool)
        return self.draft_generator.generate(task, evidence_pool)


class EvidenceVerifierWorker(ResearchWorker):
    def __init__(self, verifier):
        super().__init__("EvidenceVerifier", "verification", "evidence_verification")
        self.verifier = verifier

    def execute(self, board: CollaborationBlackboard) -> EvidenceVerificationResult:
        task = _artifact_value(board, "research_task", ResearchTask)
        evidence_pool = _artifact_value(board, "evidence_pool", EvidencePool)
        draft = _artifact_value(board, "research_draft", ResearchDraft)
        return self.verifier.verify(task, draft, evidence_pool)


class MemoryUpdateWorker(ResearchWorker):
    def __init__(self, memory):
        super().__init__("MemoryAgent", "memory_update", "memory_update")
        self.memory = memory

    def execute(self, board: CollaborationBlackboard) -> dict[str, bool]:
        result = _artifact_value(board, "final_research_result", FinalResearchResult)
        self.memory.update(board.user_id, board.session_id, board.turn_id, board.user_input, result)
        return {"updated": True}


class ResearchCoordinatorAgent:
    name = "ResearchCoordinator"

    def root_task(self, board: CollaborationBlackboard) -> AgentTask:
        return _research_task(RESEARCH_TASKS[0])

    def remember_acceptance(self, artifact_id: str, reason: str) -> None:
        return None


class ResearchEventDrivenCoordinator(EventDrivenCoordinator):
    def _ensure_root_task(self, board: CollaborationBlackboard) -> CollaborationBlackboard:
        if board.tasks:
            return board
        for specification in RESEARCH_TASKS:
            task = _research_task(specification)
            board = board.add_task(task).append_event(AgentEvent(
                type=AgentEventType.TASK_CREATED,
                actor=self.coordinator_agent.name,
                task_id=task.id,
                message=task.title,
                metadata={"status": task.status.value, "dependsOn": list(task.depends_on)},
            ))
        return board

    def _derive_missing_work(self, board: CollaborationBlackboard, force_response: bool = False) -> CollaborationBlackboard:
        for task in list(board.tasks.values()):
            if task.status != TaskStatus.BLOCKED:
                continue
            if all(board.tasks.get(dependency) and board.tasks[dependency].status == TaskStatus.CLOSED for dependency in task.depends_on):
                released = replace(task, status=TaskStatus.OPEN)
                board = board.update_task(released).append_event(AgentEvent(
                    type=AgentEventType.TASK_RELEASED,
                    actor=self.coordinator_agent.name,
                    task_id=task.id,
                    message=f"dependencies satisfied: {', '.join(task.depends_on)}",
                ))
        return board

    def _try_accept_final(self, board: CollaborationBlackboard) -> CollaborationBlackboard:
        if board.final_artifact_id:
            return board
        verification_artifact = board.latest_artifact("evidence_verification")
        if verification_artifact is None:
            return board
        artifact = board.latest_artifact("final_research_result")
        if artifact is None:
            task = _artifact_value(board, "research_task", ResearchTask)
            evidence_pool = _artifact_value(board, "evidence_pool", EvidencePool)
            draft = _artifact_value(board, "research_draft", ResearchDraft)
            verification = _artifact_value(board, "evidence_verification", EvidenceVerificationResult)
            context = _artifact_value(board, "conversation_context", ConversationContext)
            final_result = build_final_research_result(
                context.original_query, task, evidence_pool, draft, verification
            )
            artifact = AgentArtifact(
                id=f"artifact:final_research_result:{uuid.uuid4().hex[:12]}",
                owner=self.coordinator_agent.name,
                kind="final_research_result",
                payload={"value": final_result},
                confidence=1.0 if verification.sufficient else 0.5,
                task_id="task:research:verification",
                metadata={"verificationSufficient": verification.sufficient},
            )
            board = board.add_artifact(artifact)
        if board.latest_artifact("memory_update") is None:
            return board
        return board.accept_final(artifact.id, self.coordinator_agent.name, "research draft verified and finalized")


class ResearchEventDrivenRuntime:
    def __init__(self, analyzer, research_agent, draft_generator, verifier, settings, memory=None):
        memory = memory or NullResearchMemory()
        coordinator_agent = ResearchCoordinatorAgent()
        registry = AgentRegistry([
            MemoryContextWorker(memory),
            TaskAnalyzerWorker(analyzer),
            ResearchAgentWorker(research_agent),
            DraftAgentWorker(draft_generator),
            EvidenceVerifierWorker(verifier),
            MemoryUpdateWorker(memory),
        ])
        self.coordinator = ResearchEventDrivenCoordinator(registry, coordinator_agent, settings)

    def run(self, query: str, *, user_id: int | None = None, session_id: str = "") -> ResearchRuntimeRun:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        board = ResearchCollaborationBlackboard(
            turn_id=uuid.uuid4().hex,
            user_id=user_id,
            session_id=session_id,
            user_input=normalized_query,
            model_input=normalized_query,
        ).append_event(AgentEvent(
            type=AgentEventType.TURN_STARTED,
            actor="ResearchCoordinator",
            message="research query published to shared blackboard",
        ))
        final_board = self.coordinator.run(board)
        artifact = final_board.latest_artifact("final_research_result")
        final_result = artifact.payload.get("value") if artifact else None
        return ResearchRuntimeRun(final_board, final_result if isinstance(final_result, FinalResearchResult) else None)


def _research_task(specification) -> AgentTask:
    task_id, agent_name, kind, artifact_kind, dependencies = specification
    return AgentTask(
        id=task_id,
        title=agent_name,
        description=f"Produce {artifact_kind}",
        priority=TaskPriority.HIGH,
        status=TaskStatus.OPEN if not dependencies else TaskStatus.BLOCKED,
        depends_on=dependencies,
        created_by="ResearchCoordinator",
        metadata={"kind": kind, "artifactKind": artifact_kind},
    )


def _artifact_value(board: CollaborationBlackboard, kind: str, expected_type):
    artifact = board.latest_artifact(kind)
    if artifact is None:
        raise ValueError(f"required artifact is missing: {kind}")
    value = artifact.payload.get("value")
    if not isinstance(value, expected_type):
        raise TypeError(f"artifact {kind} does not contain {expected_type.__name__}")
    return value


CURRENT_QUESTION_MARKER = "Current research question:"
_ANAPHORA = re.compile(
    r"(?i)\b(it|this|that|they|them|these|those|the above|previous|former|latter)\b|^(它|这个|那个|这样|那样|为什么[？?]?|那)",
)


def query_for_analysis(context: ConversationContext) -> str:
    original = (context.original_query or "").strip()
    wrapped = (context.contextualized_query or original).strip()
    current = original
    if CURRENT_QUESTION_MARKER in wrapped:
        current = wrapped.split(CURRENT_QUESTION_MARKER, 1)[-1].strip() or original
    if wrapped != current and _needs_conversation_context(current):
        return wrapped
    return current or wrapped


def _needs_conversation_context(query: str) -> bool:
    normalized = " ".join((query or "").split())
    if len(normalized) < 24:
        return True
    return bool(_ANAPHORA.search(normalized))
