from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from app.agents.research_draft_generator import FALLBACK_ANSWER, RESEARCH_DRAFT_SYSTEM_PROMPT, ResearchDraftGenerator
from app.agents.research_types import EvidenceItem, EvidencePool, ResearchSourceType, ResearchTask, ResearchTaskType


class FakeAiClient:
    def __init__(self, response: str = "", error: Exception | None = None, responses: list[str] | None = None):
        self.responses = list(responses) if responses is not None else [response]
        self.error = error
        self.messages = None
        self.calls = 0

    def complete(self, messages):
        self.messages = messages
        self.calls += 1
        if self.error:
            raise self.error
        if not self.responses:
            raise RuntimeError("no response")
        return self.responses.pop(0)


def evidence(evidence_id: str, source_id: str, content: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_id=source_id,
        source_title=source_id,
        source_type=ResearchSourceType.PAPER,
        content=content,
        canonical_content=content,
        query_used="query",
    )


def task(
    *,
    comparison: bool = False,
    query: str = "研究问题",
    entities: list[str] | None = None,
    research_questions: list[str] | None = None,
) -> ResearchTask:
    return ResearchTask(
        task_id="task-1",
        query=query,
        task_type=ResearchTaskType.CROSS_DOCUMENT_COMPARISON if comparison else ResearchTaskType.FACT_LOOKUP,
        entities=entities or [],
        research_questions=research_questions or [],
        requires_comparison=comparison,
        requires_multiple_sources=comparison,
    )


def response(answer: str, claims: list[dict]) -> str:
    return json.dumps({"answer": answer, "claims": claims}, ensure_ascii=False)


class ResearchDraftGeneratorTests(unittest.TestCase):
    def test_valid_draft_and_chinese_output(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:react", "canonical English evidence")])
        before = pool.model_dump()
        client = FakeAiClient(response("这是中文回答", [{"claim_id": "c1", "text": "这是中文事实", "evidence_ids": ["ev-1"]}]))
        draft = ResearchDraftGenerator(client).generate(task(query="这个机制如何工作？"), pool)
        self.assertEqual(draft.answer, "这是中文回答")
        self.assertEqual(draft.claims[0].evidence_ids, ["ev-1"])
        self.assertIn("canonical English evidence", client.messages[-1].content)
        self.assertEqual(pool.model_dump(), before)

    def test_prompt_requires_complete_research_question_coverage(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:source", "Evidence for both questions")])
        client = FakeAiClient(response(
            "第一部分解释机制。第二部分解释实现，并给出综合说明。",
            [{"claim_id": "c1", "text": "证据支持机制与实现。", "evidence_ids": ["ev-1"]}],
        ))
        questions = ["机制如何工作？", "实现过程是什么？"]
        generated = ResearchDraftGenerator(client).generate(task(research_questions=questions), pool)
        self.assertTrue(generated.claims)
        payload = json.loads(client.messages[-1].content)
        self.assertEqual(payload["task"]["research_questions"], questions)
        self.assertIn("Address every research question", client.messages[0].content)

    def test_answer_must_not_be_claim_concatenation(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:source", "Evidence A")])
        raw = response("Fact A.", [{"claim_id": "c1", "text": "Fact A.", "evidence_ids": ["ev-1"]}])
        generated = ResearchDraftGenerator(FakeAiClient(raw)).generate(task(query="Explain A"), pool)
        self.assertEqual(generated.answer, FALLBACK_ANSWER)

    def test_multi_evidence_synthesis_is_supported(self):
        pool = EvidencePool(items=[
            evidence("ev-1", "research:source_a", "The process begins with input."),
            evidence("ev-2", "research:source_b", "The process ends with validation."),
        ])
        raw = response(
            "该过程先接收输入，再完成验证；两份证据共同说明了首尾步骤之间的整体流程。",
            [{"claim_id": "c1", "text": "过程包含输入与验证两个阶段。", "evidence_ids": ["ev-1", "ev-2"]}],
        )
        generated = ResearchDraftGenerator(FakeAiClient(raw)).generate(task(), pool)
        self.assertEqual(generated.claims[0].evidence_ids, ["ev-1", "ev-2"])

    def test_chinese_query_rejects_english_only_output(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:react", "canonical English evidence")])
        raw = response("English answer", [{"claim_id": "c1", "text": "English claim", "evidence_ids": ["ev-1"]}])
        self.assertEqual(ResearchDraftGenerator(FakeAiClient(raw)).generate(task(query="如何工作？"), pool).claims, [])

    def test_uncited_non_insufficiency_answer_is_rejected(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:react", "evidence")])
        draft = ResearchDraftGenerator(FakeAiClient(response("A factual answer", []))).generate(
            task(query="How does it work?"), pool
        )
        self.assertEqual(draft.answer, FALLBACK_ANSWER)

    def test_claim_id_must_be_unique(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:react", "evidence")])
        raw = response("answer", [
            {"claim_id": "same", "text": "one", "evidence_ids": ["ev-1"]},
            {"claim_id": "same", "text": "two", "evidence_ids": ["ev-1"]},
        ])
        self.assertEqual(ResearchDraftGenerator(FakeAiClient(raw)).generate(task(), pool).claims, [])

    def test_evidence_ids_must_exist_and_hallucinated_id_is_rejected(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:react", "evidence")])
        raw = response("answer", [{"claim_id": "c1", "text": "claim", "evidence_ids": ["invented"]}])
        draft = ResearchDraftGenerator(FakeAiClient(raw)).generate(task(), pool)
        self.assertEqual(draft.answer, FALLBACK_ANSWER)
        self.assertEqual(draft.claims, [])

    def test_empty_evidence_does_not_call_provider(self):
        client = FakeAiClient(error=AssertionError("must not be called"))
        draft = ResearchDraftGenerator(client).generate(task(), EvidencePool())
        self.assertEqual(draft.answer, FALLBACK_ANSWER)
        self.assertIsNone(client.messages)

    def test_provider_failure_returns_fallback(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:react", "evidence")])
        draft = ResearchDraftGenerator(FakeAiClient(error=RuntimeError("offline"))).generate(task(), pool)
        self.assertEqual(draft.model_dump(), {"answer": FALLBACK_ANSWER, "claims": []})

    def test_truncated_json_is_retried_with_compact_prompt(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:source", "canonical English evidence")])
        truncated = '{\n  "answer": "根据所给证据，该机制把推理与行动交错执行'
        complete = response(
            "该机制把推理与行动交错，环境反馈只在行动之后进入下一轮上下文。",
            [{"claim_id": "c1", "text": "推理与行动交错，反馈来自环境观察。", "evidence_ids": ["ev-1"]}],
        )
        client = FakeAiClient(responses=[truncated, complete])
        draft = ResearchDraftGenerator(client).generate(task(query="How does it work?"), pool)
        self.assertEqual(client.calls, 2)
        self.assertIn("incomplete or truncated", client.messages[-1].content)
        self.assertEqual(draft.claims[0].evidence_ids, ["ev-1"])

    def test_fenced_json(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:react", "evidence")])
        raw = "```json\n" + response("回答", [{"claim_id": "c1", "text": "事实主张", "evidence_ids": ["ev-1"]}]) + "\n```"
        self.assertEqual(len(ResearchDraftGenerator(FakeAiClient(raw)).generate(task(), pool).claims), 1)

    def test_comparison_requires_correct_multi_source_evidence(self):
        pool = EvidencePool(items=[
            evidence("react-1", "research:react", "ReAct uses observations."),
            evidence("reflexion-1", "research:reflexion", "Reflexion uses verbal reflection."),
        ])
        valid = response("比较", [
            {"claim_id": "c1", "text": "ReAct 使用 observation。", "evidence_ids": ["react-1"]},
            {"claim_id": "c2", "text": "Reflexion 使用反思。", "evidence_ids": ["reflexion-1"]},
        ])
        draft = ResearchDraftGenerator(FakeAiClient(valid)).generate(task(comparison=True), pool)
        self.assertEqual(len(draft.claims), 2)

        invalid = response("比较", [
            {"claim_id": "c1", "text": "ReAct 使用 observation。", "evidence_ids": ["reflexion-1"]},
            {"claim_id": "c2", "text": "Reflexion 使用反思。", "evidence_ids": ["reflexion-1"]},
        ])
        self.assertEqual(ResearchDraftGenerator(FakeAiClient(invalid)).generate(task(comparison=True, entities=["ReAct", "Reflexion"]), pool).claims, [])

        recovered = response("比较", [
            {"claim_id": "c1", "text": "ReAct 使用 observation。", "evidence_ids": ["react-1"]},
            {"claim_id": "c2", "text": "Reflexion 使用反思。", "evidence_ids": ["reflexion-1"]},
        ])
        client = FakeAiClient(responses=[invalid, recovered])
        draft = ResearchDraftGenerator(client).generate(task(comparison=True, entities=["ReAct", "Reflexion"]), pool)
        self.assertEqual(client.calls, 2)
        self.assertIn("failed evidence grounding", client.messages[-1].content)
        self.assertEqual(len(draft.claims), 2)

    def test_generic_entity_a_entity_b_comparison_grounding(self):
        pool = EvidencePool(items=[
            evidence("a-1", "research:entity_a", "Entity A uses process alpha."),
            evidence("b-1", "research:entity_b", "Entity B uses process beta."),
        ])
        valid = response("Entity A 采用 alpha，Entity B 采用 beta；两者过程不同，并可据此进行比较。", [
            {"claim_id": "a", "text": "Entity A 采用 alpha。", "evidence_ids": ["a-1"]},
            {"claim_id": "b", "text": "Entity B 采用 beta。", "evidence_ids": ["b-1"]},
            {"claim_id": "compare", "text": "Entity A 与 Entity B 的过程不同。", "evidence_ids": ["a-1", "b-1"]},
        ])
        generic_task = task(comparison=True, query="比较 Entity A 和 Entity B", entities=["Entity A", "Entity B"])
        self.assertEqual(len(ResearchDraftGenerator(FakeAiClient(valid)).generate(generic_task, pool).claims), 3)

        wrong = response("Entity A 与 Entity B 不同，但引用不匹配。", [
            {"claim_id": "a", "text": "Entity A 采用 alpha。", "evidence_ids": ["b-1"]},
            {"claim_id": "b", "text": "Entity B 采用 beta。", "evidence_ids": ["a-1"]},
        ])
        self.assertEqual(ResearchDraftGenerator(FakeAiClient(wrong)).generate(generic_task, pool).claims, [])

    def test_conflicting_evidence_prompt_requires_both_sides(self):
        pool = EvidencePool(items=[
            evidence("readme", "research:mini_swe_agent", "README says subprocess.run executes actions."),
            evidence("source", "research:mini_swe_agent", "process = subprocess.Popen(command); process.communicate()"),
        ])
        valid = response("两份证据的描述存在差异。", [
            {"claim_id": "c1", "text": "README 描述 subprocess.run。", "evidence_ids": ["readme"]},
            {"claim_id": "c2", "text": "固定源码使用 Popen 和 communicate。", "evidence_ids": ["source"]},
        ])
        self.assertEqual(len(ResearchDraftGenerator(FakeAiClient(valid)).generate(task(), pool).claims), 2)
        self.assertIn("Preserve disagreements between sources", RESEARCH_DRAFT_SYSTEM_PROMPT)

    def test_prompt_forbids_unsupported_external_facts(self):
        pool = EvidencePool(items=[evidence("ev-1", "research:source", "Only supplied fact")])
        client = FakeAiClient(response(
            "回答仅说明当前证据中的事实，并解释证据不足之处。",
            [{"claim_id": "c1", "text": "当前证据只包含一个事实。", "evidence_ids": ["ev-1"]}],
        ))
        ResearchDraftGenerator(client).generate(task(), pool)
        self.assertIn("Never add external facts", client.messages[0].content)
        self.assertNotIn("outside fact", client.messages[-1].content)

    def test_production_code_has_no_demo_entity_hardcoding(self):
        app_root = Path(__file__).resolve().parents[1] / "app"
        forbidden = re.compile(r"react|reflexion|mini[-_ ]?swe[-_ ]?agent", re.IGNORECASE)
        matches = []
        for path in app_root.rglob("*.py"):
            if forbidden.search(path.read_text(encoding="utf-8")):
                matches.append(str(path.relative_to(app_root)))
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
