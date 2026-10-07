from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.code_retrieval_benchmark import _metrics


ROOT = Path(__file__).resolve().parents[1]


class CodeRetrievalBenchmarkTests(unittest.TestCase):
    def test_dataset_contains_exact_diagnosed_cases_and_explicit_symbols(self):
        dataset = json.loads((
            ROOT / "app" / "research_eval" / "mini-swe-code-retrieval-benchmark.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(len(dataset["cases"]), 7)
        self.assertEqual({case["case_id"] for case in dataset["cases"]}, {
            "single-mini-architecture",
            "session-mini-action",
            "session-mini-environment",
            "cross-mini-agent-loop",
            "cross-mini-actions",
            "cross-mini-history",
            "cross-mini-environment",
        })
        self.assertTrue(all(case["expected_symbols"] for case in dataset["cases"]))
        self.assertTrue(all(case["expected_source_id"] == "research:mini_swe_agent" for case in dataset["cases"]))

    def test_metrics_distinguish_symbol_micro_recall_from_case_hits(self):
        rows = [
            {
                "symbol_ranks": {"one": 1, "two": None},
                "first_expected_rank": 1,
                "any_expected_symbol_hit_at_5": True,
                "all_expected_symbols_hit_at_5": False,
            },
            {
                "symbol_ranks": {"three": 3},
                "first_expected_rank": 3,
                "any_expected_symbol_hit_at_5": True,
                "all_expected_symbols_hit_at_5": True,
            },
        ]
        metrics = _metrics(rows)
        self.assertEqual(metrics["symbol_hit_at_1"], 1 / 3)
        self.assertEqual(metrics["symbol_hit_at_3"], 2 / 3)
        self.assertEqual(metrics["any_expected_symbol_hit_at_5"], 1.0)
        self.assertEqual(metrics["all_expected_symbols_hit_at_5"], 0.5)
        self.assertAlmostEqual(metrics["mrr"], (1 + 1 / 3) / 2)


if __name__ == "__main__":
    unittest.main()
