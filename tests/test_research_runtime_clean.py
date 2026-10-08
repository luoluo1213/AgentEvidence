import unittest

from app.agents.research_draft_generator import ResearchClaim, ResearchDraft
from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    EvidenceVerificationResult,
    ResearchSourceType,
    ResearchTask,
    ResearchTaskType,
)
from app.core.config import Settings
from app.services.research_runtime import ResearchEventDrivenRuntime


class FakeAnalyzer:
    def analyze(self, query: str):
        return ResearchTask(
            task_id="task-1",
            query=query,
            task_type=ResearchTaskType.FACT_LOOKUP,
            research_questions=[query],
        )


class FakeResearchAgent:
    def research(self, task):
        return EvidencePool(
            items=[
                EvidenceItem(
                    evidence_id="ev-1",
                    source_id="research:test",
                    source_title="Test Paper",
                    source_type=ResearchSourceType.PAPER,
                    content="ReAct interleaves reasoning and acting.",
                    canonical_content="ReAct interleaves reasoning and acting.",
                    query_used=task.query,
                )
            ]
        )


class FakeDraftAgent:
    def generate(self, task, evidence_pool):
        return ResearchDraft(
            answer="ReAct 通过交替执行推理和动作完成任务。",
            claims=[
                ResearchClaim(
                    claim_id="claim-1",
                    text="ReAct interleaves reasoning and acting.",
                    evidence_ids=["ev-1"],
                )
            ],
        )


class FakeVerifier:
    def verify(self, task, draft, evidence_pool):
        return EvidenceVerificationResult(
            sufficient=True,
            supported_points=["claim-1"],
            reason="supported",
        )


class ResearchRuntimeCleanTest(unittest.TestCase):

    def test_runtime_end_to_end(self):
        runtime = ResearchEventDrivenRuntime(
            FakeAnalyzer(),
            FakeResearchAgent(),
            FakeDraftAgent(),
            FakeVerifier(),
            Settings(),
        )

        run = runtime.run("How does ReAct work?")

        self.assertIsNotNone(run.final_result)
        self.assertEqual(
            run.final_result.answer,
            "ReAct 通过交替执行推理和动作完成任务。",
        )

        self.assertIsNotNone(
            run.board.latest_artifact("research_task")
        )
        self.assertIsNotNone(
            run.board.latest_artifact("evidence_pool")
        )
        self.assertIsNotNone(
            run.board.latest_artifact("research_draft")
        )
        self.assertIsNotNone(
            run.board.latest_artifact("evidence_verification")
        )
        self.assertIsNotNone(
            run.board.latest_artifact("final_research_result")
        )


if __name__ == "__main__":
    unittest.main()