from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

import httpx

from app.agents.research_draft_generator import FALLBACK_ANSWER, ResearchDraft, ResearchDraftGenerator
from app.agents.research_types import EvidenceItem, EvidencePool, ResearchSourceType, ResearchTask, ResearchTaskType
from app.research_harness.checkpoint import CheckpointStore
from app.research_harness.draft_validator import (
    REASON_EMPTY_OUTPUT,
    REASON_INVALID_EVIDENCE_REFERENCE,
    REASON_PLACEHOLDER_OUTPUT,
    REASON_TOO_SHORT,
    validate_draft,
)
from app.research_harness.errors import ProviderError, classify_provider_error
from app.research_harness.harness import HarnessDraftGenerator, ResearchHarness
from app.research_harness.policy import ExecutionPolicy
from scripts.research_e2e_baseline import build_report, error_record, result_record


def http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
    response = httpx.Response(status, request=request, text=f"status {status}")
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


def evidence(evidence_id: str = "ev-1", source_id: str = "research:source") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source_id,
        source_title=source_id,
        source_type=ResearchSourceType.PAPER,
        content="canonical evidence",
        canonical_content="canonical evidence",
        query_used="query",
    )


def task(query: str = "机制如何工作？", *, comparison: bool = False, entities=None) -> ResearchTask:
    return ResearchTask(
        task_id="task-1",
        query=query,
        task_type=ResearchTaskType.CROSS_DOCUMENT_COMPARISON if comparison else ResearchTaskType.FACT_LOOKUP,
        entities=entities or [],
        research_questions=[query],
        requires_comparison=comparison,
        requires_multiple_sources=comparison,
    )


def valid_json(answer: str = "该机制由所给证据支持，并完整说明了处理流程与依据。", evidence_id: str = "ev-1") -> str:
    return json.dumps({
        "answer": answer,
        "claims": [{"claim_id": "c1", "text": "证据支持该机制的核心步骤。", "evidence_ids": [evidence_id]}],
    }, ensure_ascii=False)


class ScriptedClient:
    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.last_usage = {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}
        self.settings = SimpleNamespace(ai_provider="openai", openai_model="deepseek-chat")

    def complete(self, messages):
        self.calls += 1
        if not self.outcomes:
            raise RuntimeError("no scripted outcome")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ResearchHarnessTests(unittest.TestCase):
    def test_403_is_not_retried(self):
        harness = ResearchHarness(ExecutionPolicy(max_provider_retries=2, retry_backoff_seconds=0), sleep=lambda _: None)
        client = ScriptedClient([http_status_error(403), valid_json()])
        with self.assertRaises(ProviderError) as caught:
            harness.invoke(client, [], stage="draft", agent="DraftAgent")
        self.assertEqual(caught.exception.error_type, "auth_quota")
        self.assertEqual(client.calls, 1)
        self.assertTrue(harness.diagnostics.provider_failure)
        self.assertEqual(harness.diagnostics.failure_stage, "draft")

    def test_429_timeout_and_5xx_retry_then_succeed(self):
        for first in (http_status_error(429), TimeoutError("read timed out"), http_status_error(503)):
            harness = ResearchHarness(ExecutionPolicy(max_provider_retries=2, retry_backoff_seconds=0), sleep=lambda _: None)
            client = ScriptedClient([first, valid_json()])
            text = harness.invoke(client, [], stage="draft", agent="DraftAgent")
            self.assertEqual(client.calls, 2)
            self.assertIn("claims", text)
            self.assertFalse(harness.diagnostics.provider_failure)

    def test_5xx_gives_up_after_two_retries(self):
        harness = ResearchHarness(ExecutionPolicy(max_provider_retries=2, retry_backoff_seconds=0), sleep=lambda _: None)
        client = ScriptedClient([http_status_error(502), http_status_error(502), http_status_error(502), valid_json()])
        with self.assertRaises(ProviderError) as caught:
            harness.invoke(client, [], stage="draft", agent="DraftAgent")
        self.assertEqual(caught.exception.error_type, "server_error")
        self.assertEqual(client.calls, 3)

    def test_empty_and_placeholder_drafts(self):
        pool = EvidencePool(items=[evidence()])
        research_task = task()
        empty = ResearchDraft(answer="  ", claims=[])
        self.assertEqual(validate_draft(research_task, pool, empty).reason, REASON_EMPTY_OUTPUT)
        self.assertEqual(validate_draft(research_task, pool, None).reason, REASON_EMPTY_OUTPUT)
        ellipsis = ResearchDraft(answer="...", claims=[])
        self.assertEqual(validate_draft(research_task, pool, ellipsis).reason, REASON_PLACEHOLDER_OUTPUT)
        placeholder = ResearchDraft(answer="GeoSearcher 的...。RSGround-R1 的...。比较...", claims=[])
        self.assertEqual(validate_draft(research_task, pool, placeholder).reason, REASON_PLACEHOLDER_OUTPUT)
        short = ResearchDraft(answer="太短", claims=[])
        self.assertEqual(validate_draft(research_task, pool, short).reason, REASON_TOO_SHORT)

    def test_invalid_evidence_id(self):
        pool = EvidencePool(items=[evidence("ev-1")])
        draft = ResearchDraft.model_validate({
            "answer": "该机制由所给证据支持，并完整说明了处理流程与依据。",
            "claims": [{"claim_id": "c1", "text": "证据支持该机制的核心步骤。", "evidence_ids": ["missing"]}],
        })
        result = validate_draft(task(), pool, draft)
        self.assertEqual(result.reason, REASON_INVALID_EVIDENCE_REFERENCE)
        self.assertFalse(result.valid)
        self.assertIn("missing", result.message)

    def test_evidence_refusal_is_valid_not_generic_fallback(self):
        pool = EvidencePool(items=[evidence()])
        draft = ResearchDraft(answer=FALLBACK_ANSWER, claims=[])
        result = validate_draft(task(), pool, draft)
        self.assertTrue(result.valid)

    def test_repair_success_and_failure(self):
        pool = EvidencePool(items=[evidence()])
        research_task = task()
        policy = ExecutionPolicy(max_draft_repairs=1, max_provider_retries=0, retry_backoff_seconds=0)

        ok_client = ScriptedClient(["not json", valid_json()])
        harness = ResearchHarness(policy, sleep=lambda _: None)
        draft = HarnessDraftGenerator(ResearchDraftGenerator(ok_client), harness).generate(research_task, pool)
        self.assertNotEqual(draft.answer, FALLBACK_ANSWER)
        self.assertTrue(harness.diagnostics.draft_repair_success)
        self.assertEqual(harness.diagnostics.draft_repair_attempts, 1)
        self.assertEqual(harness.diagnostics.original_validation_reason, "schema_error")
        self.assertIsNotNone(harness.diagnostics.original_validation_message)
        self.assertFalse(harness.diagnostics.fallback_used)
        self.assertEqual(ok_client.calls, 2)

        fail_client = ScriptedClient(["not json", "still not json"])
        fail_harness = ResearchHarness(policy, sleep=lambda _: None)
        failed = HarnessDraftGenerator(ResearchDraftGenerator(fail_client), fail_harness).generate(research_task, pool)
        self.assertEqual(failed.answer, FALLBACK_ANSWER)
        self.assertTrue(fail_harness.diagnostics.draft_validation_failure)
        self.assertFalse(fail_harness.diagnostics.draft_repair_success)
        self.assertTrue(fail_harness.diagnostics.fallback_used)
        self.assertTrue(fail_harness.diagnostics.agent_stage_failure)
        self.assertEqual(fail_harness.diagnostics.result_status, "draft_fallback")
        self.assertEqual(fail_harness.diagnostics.draft_validation_reason, "schema_error")
        self.assertIsNotNone(fail_harness.diagnostics.draft_validation_message)

    def test_comparison_grounding_failure_records_invalid_evidence_reference(self):
        pool = EvidencePool(items=[
            evidence("react-1", "research:react"),
            evidence("reflexion-1", "research:reflexion"),
        ])
        bad = json.dumps({
            "answer": "ReAct 使用观察，Reflexion 使用反思，两者不同。",
            "claims": [
                {"claim_id": "c1", "text": "ReAct 使用观察。", "evidence_ids": ["reflexion-1"]},
                {"claim_id": "c2", "text": "Reflexion 使用反思。", "evidence_ids": ["reflexion-1"]},
            ],
        }, ensure_ascii=False)
        still_bad = bad
        harness = ResearchHarness(ExecutionPolicy(max_draft_repairs=1, retry_backoff_seconds=0), sleep=lambda _: None)
        draft = HarnessDraftGenerator(ResearchDraftGenerator(ScriptedClient([bad, still_bad])), harness).generate(
            task(query="比较 ReAct 和 Reflexion", comparison=True, entities=["ReAct", "Reflexion"]),
            pool,
        )
        self.assertEqual(draft.answer, FALLBACK_ANSWER)
        self.assertEqual(harness.diagnostics.draft_validation_reason, REASON_INVALID_EVIDENCE_REFERENCE)
        self.assertIn("lacks matching evidence", harness.diagnostics.draft_validation_message or "")
        self.assertTrue(harness.diagnostics.fallback_used)
        self.assertFalse(harness.diagnostics.draft_repair_success)

    def test_provider_403_is_not_converted_to_draft_fallback(self):
        pool = EvidencePool(items=[evidence()])
        harness = ResearchHarness(ExecutionPolicy(max_provider_retries=2, retry_backoff_seconds=0), sleep=lambda _: None)
        generator = HarnessDraftGenerator(ResearchDraftGenerator(ScriptedClient([http_status_error(403)])), harness)
        with self.assertRaises(ProviderError) as caught:
            generator.generate(task(), pool)
        self.assertEqual(caught.exception.error_type, "auth_quota")
        self.assertTrue(harness.diagnostics.provider_failure)
        self.assertFalse(harness.diagnostics.fallback_used)

    def test_evidence_insufficient_is_not_system_failure(self):
        harness = ResearchHarness(ExecutionPolicy(retry_backoff_seconds=0), sleep=lambda _: None)
        client = ScriptedClient([valid_json()])
        draft = HarnessDraftGenerator(ResearchDraftGenerator(client), harness).generate(task(), EvidencePool())
        self.assertEqual(draft.answer, FALLBACK_ANSWER)
        self.assertTrue(harness.diagnostics.evidence_insufficient)
        self.assertFalse(harness.diagnostics.provider_failure)
        self.assertFalse(harness.diagnostics.fallback_used)
        self.assertEqual(client.calls, 0)
        record = result_record(
            {"id": "insufficient-1", "category": "insufficient", "query": "q", "expected_sources": [], "expected_concepts": [], "answerable": False},
            {"run": SimpleNamespace(final_result=SimpleNamespace(
                answer=FALLBACK_ANSWER,
                evidence_pool=EvidencePool(),
                verification=SimpleNamespace(sufficient=False),
                draft=draft,
            )), "context": None},
            "",
            harness,
        )
        self.assertFalse(record["provider_failure"])
        self.assertTrue(record["evidence_insufficient"])
        self.assertFalse(record["fallback_used"])
        self.assertEqual(record["result_status"], "evidence_insufficient")
        self.assertTrue(record["runtime_success"])

    def test_natural_refusal_marks_evidence_insufficient(self):
        pool = EvidencePool(items=[evidence()])
        refusal = json.dumps({"answer": FALLBACK_ANSWER, "claims": []}, ensure_ascii=False)
        harness = ResearchHarness(ExecutionPolicy(retry_backoff_seconds=0), sleep=lambda _: None)
        draft = HarnessDraftGenerator(ResearchDraftGenerator(ScriptedClient([refusal])), harness).generate(task(), pool)
        self.assertEqual(draft.answer, FALLBACK_ANSWER)
        self.assertTrue(harness.diagnostics.evidence_insufficient)
        self.assertFalse(harness.diagnostics.draft_validation_failure)
        self.assertFalse(harness.diagnostics.fallback_used)
        self.assertEqual(harness.diagnostics.result_status, "evidence_insufficient")

    def test_illegal_state_is_closed_after_failed_repair(self):
        pool = EvidencePool(items=[evidence()])
        harness = ResearchHarness(ExecutionPolicy(max_draft_repairs=1, retry_backoff_seconds=0), sleep=lambda _: None)
        draft = HarnessDraftGenerator(ResearchDraftGenerator(ScriptedClient(["bad", "bad"])), harness).generate(task(), pool)
        self.assertEqual(draft.answer, FALLBACK_ANSWER)
        self.assertTrue(harness.diagnostics.draft_validation_failure)
        self.assertFalse(harness.diagnostics.draft_repair_success)
        self.assertTrue(harness.diagnostics.fallback_used)
        self.assertTrue(harness.diagnostics.agent_stage_failure)

    def test_error_record_keeps_provider_failure_for_403(self):
        harness = ResearchHarness(ExecutionPolicy(retry_backoff_seconds=0), sleep=lambda _: None)
        harness.begin_case("case-403")
        exc = ProviderError("auth_quota", "403 Forbidden", status_code=403, stage="draft")
        harness.record_provider_failure(exc, stage="draft")
        record = error_record(
            {"id": "case-403", "category": "single_document", "query": "q", "expected_sources": [], "expected_concepts": [], "answerable": True},
            exc,
            0.0,
            harness,
        )
        self.assertTrue(record["provider_failure"])
        self.assertFalse(record["fallback_used"])
        self.assertEqual(record["error_type"], "auth_quota")
        self.assertEqual(record["failure_stage"], "draft")

    def test_report_keeps_old_fields_and_adds_harness_metrics(self):
        settings = SimpleNamespace(ai_provider="openai", openai_model="deepseek-chat")
        results = [{
            "case_id": "a",
            "category": "single_document",
            "answerable": True,
            "source_hit": True,
            "runtime_success": True,
            "provider_failure": False,
            "fallback_used": False,
            "latency_ms": 10,
            "draft_validation_failure": True,
            "draft_validation_reason": "schema_error",
            "draft_repair_attempts": 1,
            "draft_repair_success": True,
            "evidence_insufficient": False,
            "agent_stage_failure": False,
            "prompt_tokens": 4,
            "completion_tokens": 6,
            "total_tokens": 10,
            "estimated_cost": 0.01,
            "llm_traces": [{
                "run_id": "r",
                "case_id": "a",
                "stage": "draft",
                "agent": "DraftAgent",
                "attempt": 1,
                "latency_ms": 5.0,
                "status": "ok",
                "error_type": None,
                "prompt_tokens": 4,
                "completion_tokens": 6,
                "total_tokens": 10,
                "provider": "openai",
                "model": "deepseek-chat",
                "estimated_cost": 0.01,
            }],
            "memory_ablation": None,
        }]
        report = build_report({"cases": [{"category": "single_document"}]}, results, settings, __import__("time").perf_counter(), True)
        self.assertEqual(report["run_variant"], "baseline")
        self.assertIn("fallback_count", report["diagnostics"])
        self.assertEqual(report["diagnostics"]["draft_repair_success_count"], 1)
        self.assertEqual(report["diagnostics"]["total_tokens"], 10)
        self.assertIn("draft", report["diagnostics"]["latency_by_stage"])

    def test_classify_provider_errors(self):
        self.assertEqual(classify_provider_error(http_status_error(401)).error_type, "auth_quota")
        self.assertFalse(classify_provider_error(http_status_error(401)).retryable)
        self.assertTrue(classify_provider_error(http_status_error(429)).retryable)
        self.assertTrue(classify_provider_error(TimeoutError("x")).retryable)

    def test_checkpoint_roundtrip(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            store = CheckpointStore(Path(directory) / "checkpoint.json")
            store.save([{"case_id": "a", "answer": "ok"}], [])
            self.assertEqual(store.completed_records()["a"]["answer"], "ok")


if __name__ == "__main__":
    unittest.main()
