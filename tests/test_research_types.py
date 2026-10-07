import unittest

from app.agents.research_artifacts import ResearchArtifactKind
from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    EvidenceVerificationResult,
    ResearchSourceType,
    ResearchTask,
    ResearchTaskType,
)
from app.core.config import Settings, settings_for_research_llm


def evidence(evidence_id: str, source_id: str, retrieval_round: int = 1) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source_id,
        source_title=source_id.title(),
        source_type=ResearchSourceType.PAPER,
        content=f"Evidence from {source_id}",
        query_used="agent execution feedback",
        retrieval_round=retrieval_round,
    )


class ResearchTypesTests(unittest.TestCase):
    def test_research_task_round_trip(self):
        task = ResearchTask(
            task_id="compare-react-reflexion",
            query="Compare ReAct and Reflexion.",
            task_type=ResearchTaskType.CROSS_DOCUMENT_COMPARISON,
            entities=["ReAct", "Reflexion"],
            research_questions=["How does each method use execution feedback?"],
            expected_source_types=[ResearchSourceType.PAPER],
            requires_comparison=True,
            requires_multiple_sources=True,
        )

        restored = ResearchTask.model_validate(task.model_dump())

        self.assertEqual(restored.entities, ["ReAct", "Reflexion"])
        self.assertEqual(restored.research_questions, task.research_questions)
        self.assertTrue(restored.requires_comparison)
        self.assertEqual(restored.task_type, ResearchTaskType.CROSS_DOCUMENT_COMPARISON)

    def test_evidence_item_preserves_retrieval_fields(self):
        item = EvidenceItem(
            evidence_id="evidence-1",
            source_id="react",
            source_title="ReAct",
            source_type=ResearchSourceType.REPOSITORY,
            content="A reasoning and acting loop.",
            query_used="ReAct agent loop",
            retrieval_round=2,
        )

        self.assertEqual(item.source_type, ResearchSourceType.REPOSITORY)
        self.assertEqual(item.query_used, "ReAct agent loop")
        self.assertEqual(item.retrieval_round, 2)

    def test_evidence_pool_deduplicates_by_evidence_id(self):
        pool = EvidencePool()
        first = evidence("a", "react")

        pool.add(first)
        pool.add(first.model_copy())
        pool.add(evidence("b", "reflexion"))

        self.assertEqual(len(pool.items), 2)
        self.assertEqual(len(pool), 2)

    def test_evidence_pool_source_ids_are_unique_and_ordered(self):
        pool = EvidencePool()
        pool.extend([
            evidence("a", "react"),
            evidence("b", "react"),
            evidence("c", "reflexion", retrieval_round=2),
        ])

        self.assertEqual(pool.source_ids(), ["react", "reflexion"])
        self.assertEqual([item.evidence_id for item in pool.for_round(2)], ["c"])

    def test_evidence_verification_result_serializes(self):
        result = EvidenceVerificationResult(
            sufficient=False,
            missing_points=["Repository implementation details"],
            suggested_queries=["Reflexion repository implementation"],
            reason="Paper evidence alone is insufficient.",
        )

        restored = EvidenceVerificationResult.model_validate(result.model_dump())

        self.assertFalse(restored.sufficient)
        self.assertTrue(restored.missing_points)
        self.assertTrue(restored.suggested_queries)

    def test_research_artifact_kind_includes_response_draft(self):
        self.assertEqual(ResearchArtifactKind.RESPONSE_DRAFT.value, "research_response_draft")

    def test_research_settings_are_disabled_by_default(self):
        settings = Settings(_env_file=None)

        self.assertFalse(settings.research_mode_enabled)
        self.assertEqual(settings.research_max_retrieval_rounds, 2)
        self.assertEqual(settings.research_retrieval_top_k, 8)
        self.assertEqual(settings.research_max_evidence_items, 12)
        self.assertEqual(settings.research_ai_max_tokens, 8192)
        self.assertEqual(settings.ai_timeout_seconds, 120.0)
        research_settings = settings_for_research_llm(settings)
        self.assertEqual(research_settings.ai_max_tokens, 8192)


if __name__ == "__main__":
    unittest.main()
