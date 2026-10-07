from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import research_e2e_baseline as baseline


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "app" / "research_eval" / "research-e2e-baseline.json"


class ResearchE2EBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    def test_dataset_schema_and_distribution(self):
        baseline.validate_dataset(self.dataset)
        counts = {
            kind: sum(case["category"] == kind for case in self.dataset["cases"])
            for kind in ("single_document", "cross_document", "insufficient", "same_session", "cross_session")
        }
        self.assertEqual(counts, {
            "single_document": 9,
            "cross_document": 4,
            "insufficient": 3,
            "same_session": 2,
            "cross_session": 2,
        })
        self.assertEqual(len(self.dataset["cases"]), 20)

    def test_required_human_verified_queries_are_present(self):
        queries = {case["query"] for case in self.dataset["cases"]}
        self.assertIn("为什么 scaled dot-product attention 要除以 sqrt(d_k)？", queries)
        self.assertIn("ReAct 如何交错进行推理和行动，环境反馈起什么作用？", queries)
        self.assertIn("Reflexion 如何利用语言反馈和情景记忆，在多次 trial 之间改进行为？", queries)
        self.assertTrue(all(
            any("\u4e00" <= char <= "\u9fff" for char in case["query"])
            for case in self.dataset["cases"]
        ))

    def test_single_and_cross_source_hit(self):
        single = {
            "category": "single_document",
            "expected_sources": ["research:react_pdf"],
        }
        self.assertTrue(baseline.source_hit(single, ["research:react_pdf", "research:attention_pdf"]))
        self.assertFalse(baseline.source_hit(single, ["research:attention_pdf"]))
        cross = {
            "category": "cross_document",
            "expected_sources": ["research:react_pdf", "research:reflexion_pdf"],
        }
        self.assertTrue(baseline.source_hit(cross, ["research:reflexion_pdf", "research:react_pdf"]))
        self.assertFalse(baseline.source_hit(cross, ["research:react_pdf"]))
        self.assertIsNone(baseline.source_hit({"category": "insufficient", "expected_sources": []}, []))

    def test_memory_metrics(self):
        results = [
            {
                "category": "same_session",
                "memory_ablation": {"hierarchical_resolved": True, "stateless_resolved": False},
            },
            {
                "category": "same_session",
                "memory_ablation": {"hierarchical_resolved": True, "stateless_resolved": False},
            },
            {
                "category": "cross_session",
                "memory_ablation": {"hierarchical_resolved": True, "stateless_resolved": False},
            },
            {
                "category": "cross_session",
                "memory_ablation": {"hierarchical_resolved": False, "stateless_resolved": False},
            },
        ]
        metrics = baseline.memory_metrics(results)
        self.assertEqual(metrics["same_session"]["hierarchical"], {"hits": 2, "total": 2, "rate": 1.0})
        self.assertEqual(metrics["same_session"]["stateless"], {"hits": 0, "total": 2, "rate": 0.0})
        self.assertEqual(metrics["cross_session"]["hierarchical"]["hits"], 1)
        self.assertEqual(metrics["cross_session"]["hierarchical"]["total"], 2)

    def test_memory_resolved_uses_context_not_query_rewrite(self):
        case = {"memory_referent": "ReAct"}
        self.assertTrue(baseline.memory_resolved(case, {
            "contextualized_query": "Current research question:\n它的环境反馈具体起什么作用？",
            "session_summary": "",
            "long_term_memories": ["entity: ReAct"],
            "recent_messages": [],
        }))
        self.assertFalse(baseline.memory_resolved(case, {
            "contextualized_query": "它的环境反馈具体起什么作用？",
            "session_summary": "",
            "long_term_memories": [],
            "recent_messages": [],
        }))

    def test_human_annotation_summary_stays_pending_until_complete(self):
        annotation = {
            "cases": [
                {"id": "a", "correctness": None},
                {"id": "b", "correctness": "correct"},
            ]
        }
        pending = baseline.aggregate_human_annotations(annotation, answerable_total=2)
        self.assertEqual(pending["status"], "PENDING HUMAN REVIEW")
        self.assertIsNone(pending["strict_accuracy"])
        complete = {
            "cases": [
                {"id": "a", "correctness": "correct"},
                {"id": "b", "correctness": "partial"},
                {"id": "c", "correctness": "incorrect"},
            ]
        }
        done = baseline.aggregate_human_annotations(complete, answerable_total=3)
        self.assertEqual(done["status"], "COMPLETE")
        self.assertEqual(done["strict_accuracy"], round(1 / 3, 6))
        self.assertEqual(done["acceptable_rate"], round(2 / 3, 6))

    def test_latency_summary(self):
        summary = baseline.latency_summary([
            {"latency_ms": 1000},
            {"latency_ms": 2000},
            {"latency_ms": 3000},
        ])
        self.assertEqual(summary["avg_latency_ms"], 2000.0)
        self.assertEqual(summary["median_latency_ms"], 2000.0)

    def test_report_serialization_keeps_baseline_variant_and_pending_accuracy(self):
        class Settings:
            ai_provider = "openai"
            openai_model = "test-model"

        report = baseline.build_report(
            self.dataset,
            [
                {
                    "case_id": "single-attention-scaling",
                    "category": "single_document",
                    "answerable": True,
                    "source_hit": True,
                    "runtime_success": True,
                    "provider_failure": False,
                    "fallback_used": False,
                    "latency_ms": 1500,
                    "memory_ablation": None,
                }
            ],
            Settings(),
            started=__import__("time").perf_counter(),
            stateless_ablation=True,
        )
        self.assertEqual(report["run_variant"], "baseline")
        self.assertEqual(report["future_comparison_variant"], "retrieval_repair")
        self.assertIsNone(report["metrics"]["answer_correctness"]["strict_accuracy"])
        markdown = baseline.report_markdown(report)
        self.assertIn("Pending / 人工标注后计算", markdown)
        self.assertNotIn("Bearer", markdown)
        self.assertNotIn("reasoning_content", markdown)

    def test_human_annotation_only_includes_answerable_cases(self):
        results = [
            {"case_id": case["id"], "answer": "placeholder"}
            for case in self.dataset["cases"]
        ]
        annotation = baseline.build_human_annotation(self.dataset["cases"], results)
        self.assertTrue(all(case["correctness"] is None for case in annotation["cases"]))
        self.assertEqual(len(annotation["cases"]), 17)


if __name__ == "__main__":
    unittest.main()
