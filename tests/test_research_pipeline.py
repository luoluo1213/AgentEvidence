from __future__ import annotations

import unittest

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_draft_generator import FALLBACK_ANSWER, ResearchClaim, ResearchDraft, ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    EvidenceVerificationResult,
    ResearchSourceType,
    ResearchTask,
    ResearchTaskType,
)
from app.services.research_pipeline import ResearchPipeline


def research_task(query: str = "query") -> ResearchTask:
    return ResearchTask(task_id="task-pipeline", query=query, task_type=ResearchTaskType.FACT_LOOKUP)


def evidence(evidence_id: str, source_id: str = "research:react") -> EvidenceItem:
    source_title = "ReAct: Synergizing Reasoning and Acting" if source_id.endswith("react") else "Reflexion: Verbal Reinforcement"
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source_id,
        source_title=source_id,
        source_type=ResearchSourceType.PAPER,
        content=f"canonical evidence {evidence_id}",
        canonical_content=f"canonical evidence {evidence_id}",
        query_used="query",
        metadata={"source_title": source_title, "file_path": f"{evidence_id}.md"},
    )


def grounded_draft(answer: str = "evidence-grounded answer") -> ResearchDraft:
    return ResearchDraft(
        answer=answer,
        claims=[ResearchClaim(claim_id="claim-1", text="grounded claim", evidence_ids=["ev-1"])],
    )


def verification(*, sufficient: bool = True) -> EvidenceVerificationResult:
    return EvidenceVerificationResult(
        sufficient=sufficient,
        supported_points=["grounded claim"] if sufficient else [],
        missing_points=[] if sufficient else ["more implementation evidence is required"],
        suggested_queries=[] if sufficient else ["implementation evidence for grounded claim"],
        reason="verified" if sufficient else "insufficient evidence",
    )


class RecordingAnalyzer:
    def __init__(self, calls):
        self.calls = calls

    def analyze(self, query):
        self.calls.append(("analyze", query))
        return research_task(query)


class RecordingResearcher:
    def __init__(self, calls, pool):
        self.calls = calls
        self.pool = pool

    def research(self, task):
        self.calls.append(("research", task))
        return self.pool


class RecordingDraftGenerator:
    def __init__(self, calls, result):
        self.calls = calls
        self.result = result
        self.received_pool = None

    def generate(self, task, evidence_pool):
        self.calls.append(("draft", task, evidence_pool))
        self.received_pool = evidence_pool
        return self.result


class RecordingVerifier:
    def __init__(self, calls, result):
        self.calls = calls
        self.result = result
        self.received_draft = None
        self.received_pool = None

    def verify(self, task, draft, evidence_pool):
        self.calls.append(("verify", task, draft, evidence_pool))
        self.received_draft = draft
        self.received_pool = evidence_pool
        return self.result


class FailingAiClient:
    def complete(self, messages):
        raise RuntimeError("provider unavailable")


class StaticKnowledge:
    def retrieve(self, query, top_k=None, corpus=None):
        class Result:
            chunk_id = 1
            source = "research:react"
            content = "canonical evidence"
            content_en = "canonical evidence"
            content_zh = None
            score = 1.0
            section = "Method"
            metadata = {"source_title": "ReAct"}
            canonical_language = "en"
            translation_status = "missing"
            translation_method = None
            translation_verified = False
        return [Result()]


class ResearchPipelineTests(unittest.TestCase):
    def build_pipeline(self, *, verify_result=None):
        calls = []
        pool = EvidencePool(items=[evidence("ev-1"), evidence("ev-2", "research:reflexion")])
        draft_result = grounded_draft()
        draft_generator = RecordingDraftGenerator(calls, draft_result)
        verifier = RecordingVerifier(calls, verify_result or verification())
        pipeline = ResearchPipeline(
            RecordingAnalyzer(calls),
            RecordingResearcher(calls, pool),
            draft_generator,
            verifier,
        )
        return pipeline, calls, pool, draft_result, draft_generator, verifier

    def test_complete_pipeline_call_order_is_correct(self):
        pipeline, calls, *_ = self.build_pipeline()
        pipeline.run("  query  ")
        self.assertEqual([entry[0] for entry in calls], ["analyze", "research", "draft", "verify"])
        self.assertEqual(calls[0][1], "query")

    def test_full_evidence_pool_is_passed_to_draft_generator(self):
        pipeline, _, pool, _, draft_generator, _ = self.build_pipeline()
        result = pipeline.run("query")
        self.assertIs(draft_generator.received_pool, pool)
        self.assertIs(result.evidence_pool, pool)
        self.assertEqual(len(draft_generator.received_pool.items), 2)

    def test_actual_draft_and_same_pool_are_passed_to_verifier(self):
        pipeline, _, pool, draft_result, _, verifier = self.build_pipeline()
        pipeline.run("query")
        self.assertIs(verifier.received_draft, draft_result)
        self.assertIs(verifier.received_pool, pool)

    def test_final_answer_comes_from_evidence_grounded_draft(self):
        pipeline, *_ = self.build_pipeline()
        result = pipeline.run("query")
        self.assertEqual(result.answer, "evidence-grounded answer")
        self.assertEqual(result.answer, result.draft.answer)
        self.assertEqual(result.sources, ["ReAct", "Reflexion"])

    def test_insufficient_verification_retains_answer_and_repair_fields(self):
        pipeline, *_ = self.build_pipeline(verify_result=verification(sufficient=False))
        result = pipeline.run("query")
        self.assertEqual(result.answer, "evidence-grounded answer")
        self.assertFalse(result.verification.sufficient)
        self.assertEqual(result.verification.missing_points, ["more implementation evidence is required"])
        self.assertEqual(result.verification.suggested_queries, ["implementation evidence for grounded claim"])

    def test_provider_failures_are_handled_safely_by_pipeline_components(self):
        from app.agents.research_agent import ResearchAgent

        pipeline = ResearchPipeline(
            TaskAnalyzerAgent(FailingAiClient()),
            ResearchAgent(StaticKnowledge()),
            ResearchDraftGenerator(FailingAiClient()),
            EvidenceVerifier(FailingAiClient()),
        )
        result = pipeline.run("How does it work?")
        self.assertEqual(result.answer, FALLBACK_ANSWER)
        self.assertFalse(result.verification.sufficient)
        self.assertTrue(result.verification.missing_points)

    def test_legacy_runtime_is_not_a_pipeline_dependency(self):
        pipeline, *_ = self.build_pipeline()
        dependency_modules = {value.__class__.__module__ for value in pipeline.__dict__.values()}
        self.assertNotIn("app.agents.event_driven_runtime", dependency_modules)
        self.assertNotIn("app.services.chat", dependency_modules)


if __name__ == "__main__":
    unittest.main()
