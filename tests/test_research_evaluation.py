from __future__ import annotations

import json
import unittest

from app.agents.research_types import EvidenceItem, ResearchSourceType
from app.research_eval.runner import (
    DEFAULT_DATASET,
    StatelessEvaluationMemory,
    _concept_hits,
    _validate_cases,
    summarize_results,
)


class ResearchEvaluationTests(unittest.TestCase):
    def test_dataset_has_required_twenty_case_distribution(self):
        cases = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))["cases"]
        _validate_cases(cases)
        self.assertEqual(len(cases), 20)

    def test_stateless_ablation_never_supplies_prior_context(self):
        memory = StatelessEvaluationMemory()
        context = memory.build_context(1, "session", "current question")
        self.assertEqual(context.contextualized_query, "current question")
        self.assertEqual(context.recent_messages, [])
        self.assertEqual(context.long_term_memories, [])

    def test_metric_aggregation_uses_case_level_rates(self):
        results = [
            {
                "category": "same_session_multi_turn",
                "runtime_completed": True,
                "source_hit": True,
                "expected_concepts_hit": True,
                "grounded": True,
                "insufficient_behavior_pass": None,
                "ablation": {
                    "stateless": {"resolved": False},
                    "hierarchical_memory": {"resolved": True},
                },
            },
            {
                "category": "cross_session_memory",
                "runtime_completed": True,
                "source_hit": False,
                "expected_concepts_hit": False,
                "grounded": False,
                "insufficient_behavior_pass": None,
                "ablation": {
                    "stateless": {"resolved": False},
                    "hierarchical_memory": {"resolved": True},
                },
            },
            {
                "category": "insufficient_evidence",
                "runtime_completed": True,
                "source_hit": None,
                "expected_concepts_hit": None,
                "grounded": False,
                "insufficient_behavior_pass": True,
            },
        ]
        metrics = summarize_results(results)
        self.assertEqual(metrics["runtime_completion_rate"], 1.0)
        self.assertEqual(metrics["source_hit_rate"], 0.5)
        self.assertEqual(metrics["grounded_answer_rate"], 0.333333)
        self.assertEqual(metrics["same_session_context_resolution_accuracy"], 1.0)
        self.assertEqual(metrics["cross_session_memory_recall_accuracy"], 1.0)
        self.assertEqual(metrics["ablation"]["same_session"]["stateless"], 0.0)

    def test_concept_checker_reads_safe_provenance_without_fuzzy_matching(self):
        item = EvidenceItem(
            evidence_id="ev-1",
            source_id="research:example",
            source_title="Example",
            source_type=ResearchSourceType.REPOSITORY,
            content="def execute(self, action): pass",
            query_used="query",
            section="Execution",
            metadata={
                "symbol": "LocalEnvironment.execute",
                "file_path": "src/environments/local.py",
            },
        )
        hits = _concept_hits(
            ["LocalEnvironment.execute", "src/environments/local.py", "LocalEnvironment.run"],
            [item],
        )
        self.assertTrue(hits["LocalEnvironment.execute"])
        self.assertTrue(hits["src/environments/local.py"])
        self.assertFalse(hits["LocalEnvironment.run"])


if __name__ == "__main__":
    unittest.main()
