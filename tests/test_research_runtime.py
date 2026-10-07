from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.agents.event_driven_runtime import EventDrivenAgentRuntimeService
from app.agents.events import AgentEventType, TaskStatus
from app.agents.research_draft_generator import ResearchClaim, ResearchDraft
from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    EvidenceVerificationResult,
    ResearchSourceType,
    ResearchTask,
    ResearchTaskType,
)
from app.services.research_memory import ConversationContext
from app.services.research_runtime import ResearchEventDrivenRuntime, query_for_analysis


def settings():
    return SimpleNamespace(
        agent_max_rounds=8,
        agent_max_claims_per_round=4,
        agent_max_claims_per_agent=8,
        agent_final_acceptance_min_confidence=0.6,
    )


def evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="ev-1",
        source_id="research:source",
        source_title="Source",
        source_type=ResearchSourceType.PAPER,
        content="Canonical evidence.",
        canonical_content="Canonical evidence.",
        query_used="query",
        metadata={"source_title": "Source"},
    )


class RecordingAnalyzer:
    def __init__(self, calls):
        self.calls = calls

    def analyze(self, query):
        self.calls.append(("analysis", query))
        return ResearchTask(
            task_id="research-task",
            query=query,
            task_type=ResearchTaskType.FACT_LOOKUP,
            research_questions=[query],
        )


class RecordingResearcher:
    def __init__(self, calls, *, fail=False):
        self.calls = calls
        self.fail = fail
        self.task = None

    def research(self, task):
        self.calls.append(("research", task))
        self.task = task
        if self.fail:
            raise RuntimeError("retrieval failed")
        return EvidencePool(items=[evidence()])


class RecordingDrafter:
    def __init__(self, calls):
        self.calls = calls
        self.task = None
        self.pool = None

    def generate(self, task, evidence_pool):
        self.calls.append(("draft", task, evidence_pool))
        self.task = task
        self.pool = evidence_pool
        return ResearchDraft(
            answer="Grounded final answer with explanation.",
            claims=[ResearchClaim(claim_id="claim-1", text="Grounded claim.", evidence_ids=["ev-1"])],
        )


class RecordingVerifier:
    def __init__(self, calls):
        self.calls = calls
        self.task = None
        self.draft = None
        self.pool = None

    def verify(self, task, draft, evidence_pool):
        self.calls.append(("verification", task, draft, evidence_pool))
        self.task = task
        self.draft = draft
        self.pool = evidence_pool
        return EvidenceVerificationResult(
            sufficient=True,
            supported_points=["Grounded claim."],
            reason="supported",
        )


class ResearchRuntimeTests(unittest.TestCase):
    def build_runtime(self, *, research_fail=False):
        calls = []
        analyzer = RecordingAnalyzer(calls)
        researcher = RecordingResearcher(calls, fail=research_fail)
        drafter = RecordingDrafter(calls)
        verifier = RecordingVerifier(calls)
        runtime = ResearchEventDrivenRuntime(analyzer, researcher, drafter, verifier, settings())
        return runtime, calls, analyzer, researcher, drafter, verifier

    def test_task_dependencies_release_in_order(self):
        runtime, *_ = self.build_runtime()
        run = runtime.run("research query")
        self.assertTrue(all(task.status == TaskStatus.CLOSED for task in run.board.tasks.values()))
        released = [event.task_id for event in run.board.events if event.type == AgentEventType.TASK_RELEASED]
        self.assertEqual(released, [
            "task:research:analysis",
            "task:research:evidence",
            "task:research:draft",
            "task:research:verification",
            "task:research:memory_update",
        ])

    def test_artifact_handoff_uses_typed_values(self):
        runtime, _, _, researcher, drafter, verifier = self.build_runtime()
        run = runtime.run("research query")
        task_value = run.board.latest_artifact("research_task").payload["value"]
        pool_value = run.board.latest_artifact("evidence_pool").payload["value"]
        draft_value = run.board.latest_artifact("research_draft").payload["value"]
        self.assertIs(researcher.task, task_value)
        self.assertIs(drafter.task, task_value)
        self.assertIs(drafter.pool, pool_value)
        self.assertIs(verifier.draft, draft_value)
        self.assertIs(verifier.pool, pool_value)

    def test_correct_agent_claims_each_task(self):
        runtime, *_ = self.build_runtime()
        run = runtime.run("research query")
        claims = {
            event.task_id: event.actor
            for event in run.board.events
            if event.type == AgentEventType.TASK_CLAIMED
        }
        self.assertEqual(claims, {
            "task:research:memory_context": "MemoryAgent",
            "task:research:analysis": "TaskAnalyzer",
            "task:research:evidence": "ResearchAgent",
            "task:research:draft": "DraftAgent",
            "task:research:verification": "EvidenceVerifier",
            "task:research:memory_update": "MemoryAgent",
        })
        self.assertEqual(run.board.tasks["task:research:memory_context"].claimed_by, ("MemoryAgent",))
        self.assertEqual(run.board.tasks["task:research:analysis"].claimed_by, ("TaskAnalyzer",))
        self.assertEqual(run.board.tasks["task:research:evidence"].claimed_by, ("ResearchAgent",))
        self.assertEqual(run.board.tasks["task:research:draft"].claimed_by, ("DraftAgent",))
        self.assertEqual(run.board.tasks["task:research:verification"].claimed_by, ("EvidenceVerifier",))
        self.assertEqual(run.board.tasks["task:research:memory_update"].claimed_by, ("MemoryAgent",))

    def test_final_result_is_generated_and_published(self):
        runtime, calls, *_ = self.build_runtime()
        run = runtime.run("research query")
        self.assertEqual([call[0] for call in calls], ["analysis", "research", "draft", "verification"])
        self.assertIsNotNone(run.final_result)
        self.assertEqual(run.final_result.answer, "Grounded final answer with explanation.")
        self.assertTrue(run.final_result.verification.sufficient)
        self.assertIs(run.board.latest_artifact("final_research_result").payload["value"], run.final_result)
        self.assertTrue(any(event.type == AgentEventType.FINAL_ACCEPTED for event in run.board.events))

    def test_worker_failure_does_not_corrupt_blackboard(self):
        runtime, _, *_ = self.build_runtime(research_fail=True)
        run = runtime.run("research query")
        self.assertIsNotNone(run.board.latest_artifact("research_task"))
        self.assertIsNone(run.board.latest_artifact("evidence_pool"))
        self.assertIsNone(run.board.latest_artifact("research_draft"))
        self.assertIsNone(run.board.latest_artifact("final_research_result"))
        self.assertIsNone(run.final_result)
        self.assertEqual(run.board.tasks["task:research:analysis"].status, TaskStatus.CLOSED)
        self.assertEqual(run.board.tasks["task:research:evidence"].status, TaskStatus.OPEN)
        self.assertTrue(any(event.type == AgentEventType.BUDGET_EXHAUSTED for event in run.board.events))

    def test_legacy_mindbridge_runtime_is_unchanged_and_separate(self):
        self.assertEqual(EventDrivenAgentRuntimeService.framework_name, "event_driven_multi_agent")
        runtime, *_ = self.build_runtime()
        self.assertNotIsInstance(runtime, EventDrivenAgentRuntimeService)

    def test_standalone_question_is_analyzed_without_memory_wrapper(self):

        calls = []
        runtime = ResearchEventDrivenRuntime(
            RecordingAnalyzer(calls),
            RecordingResearcher(calls),
            RecordingDrafter(calls),
            RecordingVerifier(calls),
            settings(),
            _StickyMemory(),
        )
        query = "How does ReAct interleave reasoning and acting, and what role does environmental feedback play?"
        runtime.run(query, user_id=1, session_id="session-a")
        analyzed = next(value for name, value in calls if name == "analysis")
        self.assertEqual(analyzed, query)
        self.assertNotIn("scaled dot-product", analyzed)

    def test_followup_still_uses_memory_wrapper(self):
        context = ConversationContext(
            original_query="How does it affect the next turn?",
            contextualized_query=(
                "Use the supplied conversation memory only to resolve references in the current research question.\n\n"
                "Stable research context:\nentity: Example Agent\n\n"
                "Current research question:\nHow does it affect the next turn?"
            ),
        )
        self.assertIn("Example Agent", query_for_analysis(context))


class _StickyMemory:
    def build_context(self, user_id, session_id, query):
        wrapped = (
            "Use the supplied conversation memory only to resolve references in the current research question.\n\n"
            "Stable research context:\nentity: scaled dot-product attention\n"
            f"Current research question:\n{query}"
        )
        return ConversationContext(original_query=query, contextualized_query=wrapped)

    def update(self, *args, **kwargs):
        return None
