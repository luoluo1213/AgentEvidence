from __future__ import annotations

import json
import unittest

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_draft_generator import ResearchClaim, ResearchDraft
from app.agents.research_types import EvidenceItem, EvidencePool, ResearchSourceType, ResearchTask, ResearchTaskType


class FakeAiClient:
    def __init__(self, payload: dict | None = None, *, raw: str | None = None, error: Exception | None = None):
        self.payload = payload
        self.raw = raw
        self.error = error
        self.messages = None

    def complete(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        if self.raw is not None:
            return self.raw
        return json.dumps(self.payload, ensure_ascii=False)


def item(evidence_id: str, content: str, source_id: str = "research:source") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source_id,
        source_title=source_id,
        source_type=ResearchSourceType.PAPER,
        content=content,
        canonical_content=content,
        query_used="question",
    )


def task(*questions: str) -> ResearchTask:
    questions = questions or ("How does the mechanism work?",)
    return ResearchTask(
        task_id="task-verify",
        query=questions[0],
        task_type=ResearchTaskType.GENERAL_RESEARCH,
        research_questions=list(questions),
    )


def draft(*claims: ResearchClaim) -> ResearchDraft:
    return ResearchDraft(answer="Grounded answer", claims=list(claims))


def claim(claim_id: str = "c1", text: str = "Supported fact", ids: list[str] | None = None) -> ResearchClaim:
    return ResearchClaim(claim_id=claim_id, text=text, evidence_ids=ids or ["ev-1"])


def verification(*, sufficient: bool, supported=None, missing=None, weak=None, queries=None, reason="checked") -> dict:
    return {
        "sufficient": sufficient,
        "supported_points": supported or [],
        "missing_points": missing or [],
        "weak_evidence_ids": weak or [],
        "suggested_queries": queries or [],
        "reason": reason,
    }


class EvidenceVerifierTests(unittest.TestCase):
    def test_fully_supported_actual_draft_is_sufficient(self):
        pool = EvidencePool(items=[item("ev-1", "The mechanism performs step A.")])
        research_draft = draft(claim(text="The mechanism performs step A."))
        before_draft = research_draft.model_dump()
        before_pool = pool.model_dump()
        client = FakeAiClient(verification(sufficient=True, supported=["c1 is directly supported"] ))
        result = EvidenceVerifier(client).verify(task(), research_draft, pool)
        self.assertTrue(result.sufficient)
        self.assertIn('"draft"', client.messages[-1].content)
        self.assertIn("Grounded answer", client.messages[-1].content)
        self.assertEqual(research_draft.model_dump(), before_draft)
        self.assertEqual(pool.model_dump(), before_pool)

    def test_unsupported_claim_is_insufficient(self):
        pool = EvidencePool(items=[item("ev-1", "Evidence states A only.")])
        client = FakeAiClient(verification(
            sufficient=False,
            missing=["Claim c1 asserts B, which the cited evidence does not support."],
            weak=["ev-1"],
            queries=["mechanism evidence for B"],
        ))
        result = EvidenceVerifier(client).verify(task(), draft(claim(text="The mechanism does B.")), pool)
        self.assertFalse(result.sufficient)
        self.assertEqual(result.weak_evidence_ids, ["ev-1"])

    def test_partial_support_is_insufficient(self):
        pool = EvidencePool(items=[item("ev-1", "A happens, but no timing is given.")])
        client = FakeAiClient(verification(
            sufficient=False,
            supported=["A happens"],
            missing=["The claimed timing is not established."],
            weak=["ev-1"],
            queries=["when does A happen primary source"],
        ))
        result = EvidenceVerifier(client).verify(task(), draft(claim(text="A always happens before B.")), pool)
        self.assertFalse(result.sufficient)
        self.assertIn("The claimed timing is not established.", result.missing_points)

    def test_missing_research_question_coverage(self):
        pool = EvidencePool(items=[item("ev-1", "Evidence answers the first question.")])
        client = FakeAiClient(verification(
            sufficient=False,
            supported=["first question"],
            missing=["The second research question is not covered."],
            queries=["How does the second mechanism differ?"],
        ))
        result = EvidenceVerifier(client).verify(
            task("What is the first mechanism?", "How does the second mechanism differ?"),
            draft(claim()),
            pool,
        )
        self.assertFalse(result.sufficient)
        self.assertEqual(result.suggested_queries, ["How does the second mechanism differ?"])

    def test_hallucinated_evidence_id_is_rejected_before_provider(self):
        pool = EvidencePool(items=[item("ev-1", "Evidence")])
        client = FakeAiClient(error=AssertionError("provider must not be called"))
        result = EvidenceVerifier(client).verify(task(), draft(claim(ids=["invented-id"])), pool)
        self.assertFalse(result.sufficient)
        self.assertIn("invented-id", result.weak_evidence_ids)
        self.assertIsNone(client.messages)

    def test_conflicting_sources_preserved_correctly(self):
        pool = EvidencePool(items=[
            item("ev-a", "Source A reports one behavior.", "research:source_a"),
            item("ev-b", "Source B reports a different behavior.", "research:source_b"),
        ])
        research_draft = draft(
            claim("c-a", "Source A reports one behavior.", ["ev-a"]),
            claim("c-b", "Source B instead reports a different behavior.", ["ev-b"]),
        )
        client = FakeAiClient(verification(
            sufficient=True,
            supported=["Both conflicting source positions are separately stated and cited."],
        ))
        self.assertTrue(EvidenceVerifier(client).verify(task(), research_draft, pool).sufficient)

    def test_targeted_suggested_queries_are_retained_and_deduplicated(self):
        pool = EvidencePool(items=[item("ev-1", "Partial evidence")])
        client = FakeAiClient(verification(
            sufficient=False,
            missing=["Implementation detail is missing."],
            queries=["implementation command execution source", "implementation command execution source"],
        ))
        result = EvidenceVerifier(client).verify(task(), draft(claim()), pool)
        self.assertEqual(result.suggested_queries, ["implementation command execution source"])

    def test_provider_failure_is_insufficient(self):
        pool = EvidencePool(items=[item("ev-1", "Evidence")])
        result = EvidenceVerifier(FakeAiClient(error=RuntimeError("offline"))).verify(task(), draft(claim()), pool)
        self.assertFalse(result.sufficient)
        self.assertTrue(result.missing_points)
        self.assertTrue(result.suggested_queries)

    def test_invalid_json_is_insufficient(self):
        pool = EvidencePool(items=[item("ev-1", "Evidence")])
        result = EvidenceVerifier(FakeAiClient(raw="not json")).verify(task(), draft(claim()), pool)
        self.assertFalse(result.sufficient)
        self.assertIn("validation failed", result.reason)


if __name__ == "__main__":
    unittest.main()
