from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import research_e2e_benchmark as benchmark


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "app" / "research_eval" / "research-e2e-benchmark.json"


class ResearchE2EBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    def test_schema_and_distribution(self):
        benchmark.validate_dataset(self.dataset)
        counts = {kind: sum(case["case_type"] == kind for case in self.dataset["cases"])
                  for kind in ("single_turn", "cross_document", "same_session", "cross_session", "insufficient")}
        self.assertEqual(counts, {"single_turn": 8, "cross_document": 4, "same_session": 4,
                                  "cross_session": 2, "insufficient": 2})

    def test_reference_points_and_document_digests_exist(self):
        self.assertTrue(all(case["reference_answer_points"] for case in self.dataset["cases"]))
        for document in self.dataset["documents"]:
            path = ROOT / document["location"]
            self.assertTrue(path.is_file())
            self.assertEqual(__import__("hashlib").sha256(path.read_bytes()).hexdigest(), document["sha256"])

    def test_real_path_has_no_demo_grounded_client(self):
        source = (ROOT / "scripts" / "research_e2e_benchmark.py").read_text(encoding="utf-8")
        forbidden = "Demo" + "GroundedDraftClient"
        self.assertNotIn(forbidden, source)
        self.assertIn("AiClient(settings)", source)

    def test_context_groups_and_fresh_cross_session_contract(self):
        same = [case for case in self.dataset["cases"] if case["case_type"] == "same_session"]
        cross = [case for case in self.dataset["cases"] if case["case_type"] == "cross_session"]
        self.assertTrue(all(case.get("session_group") and case.get("prior_turns") for case in same))
        self.assertTrue(all(case["source_session"] != case["target_session"] for case in cross))
        self.assertTrue(all(case.get("expected_memory_fact") for case in cross))

    def test_insufficient_cases_have_no_expected_sources_or_anchors(self):
        cases = [case for case in self.dataset["cases"] if case["case_type"] == "insufficient"]
        self.assertEqual(len(cases), 2)
        self.assertTrue(all(case["expected_insufficient"] for case in cases))
        self.assertTrue(all(not case["expected_source_ids"] and not case["expected_evidence_anchors"] for case in cases))

    def test_claim_annotation_structure_and_nulls(self):
        result = {"case_id": self.dataset["cases"][0]["case_id"], "claims": [
            {"claim_id": "c1", "text": "fact", "evidence_ids": ["e1"]}
        ], "final_answer": "answer", "retrieved_evidence": [], "verification": {"sufficient": True}}
        annotation = benchmark.build_annotation(self.dataset, [result])
        claim = annotation["cases"][0]["claims"][0]
        self.assertEqual(set(claim), {"claim_id", "text", "evidence_ids", "human_supported", "human_note"})
        self.assertIsNone(claim["human_supported"])
        self.assertIsNone(annotation["cases"][0]["answer_correctness"])

    def test_pending_human_labels_are_not_failures(self):
        annotation = {"cases": [{"case_type": "single_turn", "answer_correctness": None, "claims": [
            {"human_supported": None}
        ]}]}
        aggregate = benchmark.aggregate_human_annotations(annotation)
        self.assertEqual(aggregate["annotation_status"], "PENDING")
        self.assertIsNone(aggregate["supported_claim_rate"])
        self.assertEqual(aggregate["pending_answers"], 1)

    def test_human_aggregation_and_verifier_confusion(self):
        annotation = {"cases": [
            {"case_type": "single_turn", "answer_correctness": "FULL", "claims": [{"human_supported": True}],
             "evidence_verifier": {"sufficient": True}},
            {"case_type": "single_turn", "answer_correctness": "PARTIAL", "claims": [{"human_supported": False}],
             "evidence_verifier": {"sufficient": False}},
            {"case_type": "single_turn", "answer_correctness": "INCORRECT", "claims": [],
             "evidence_verifier": {"sufficient": True}},
        ]}
        aggregate = benchmark.aggregate_human_annotations(annotation)
        self.assertEqual(aggregate["answer_correctness"]["FULL"]["count"], 1)
        self.assertEqual(aggregate["answer_correctness"]["PARTIAL"]["count"], 1)
        self.assertEqual(aggregate["answer_correctness"]["INCORRECT"]["count"], 1)
        self.assertEqual(aggregate["supported_claim_rate"], 0.5)
        self.assertEqual(aggregate["verifier_confusion"]["verifier_sufficient__human_unsupported"], 1)

    def test_memory_ablation_metrics(self):
        rows = [
            {"case_type": "same_session", "stateless": {"resolved": False}, "hierarchical_memory": {"resolved": True}},
            {"case_type": "cross_session", "stateless": {"resolved": False}, "hierarchical_memory": {"resolved": True}},
        ]
        metrics = benchmark.ablation_metrics(rows)
        self.assertEqual(metrics["same_session"], {"stateless": 0.0, "hierarchical_memory": 1.0})
        self.assertEqual(metrics["cross_session"], {"stateless": 0.0, "hierarchical_memory": 1.0})

    def test_secret_and_reasoning_sanitization(self):
        raw = "Authorization: Bearer super-secret api_key=also-secret reasoning_content: hidden thought"
        value = benchmark.sanitize(raw)
        self.assertNotIn("super-secret", value)
        self.assertNotIn("also-secret", value)
        self.assertNotIn("hidden thought", value)

    def test_annotation_markdown_contains_manual_controls(self):
        annotation = {"cases": [{"case_id": "x", "query": "q", "reference_answer_points": ["p"],
                                  "final_answer": "a", "retrieved_evidence": [], "claims": [
                                      {"text": "fact", "evidence_ids": ["e1"]}
                                  ]}]}
        rendered = benchmark.annotation_markdown(annotation)
        self.assertIn("[ ] FULL", rendered)
        self.assertIn("[ ] Supported", rendered)
        self.assertNotIn("reasoning_content", rendered)


if __name__ == "__main__":
    unittest.main()
