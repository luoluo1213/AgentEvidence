from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.services.knowledge import KnowledgeService
from app.services.source_ingestion import ResearchSourceIngestionService, SourceIngestionRequest
from scripts.document_retrieval_benchmark import ROOT, _metrics, _require_live_vector, _resolve_labels


DATASET_PATH = ROOT / "app" / "research_eval" / "document-retrieval-benchmark.json"
RESULTS = ROOT / "artifacts" / "results"


class DocumentRetrievalBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    def test_benchmark_labels_resolve_to_real_pdf_chunks(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        with tempfile.TemporaryDirectory() as directory:
            knowledge = KnowledgeService(db, Settings(knowledge_vector_enabled=False))
            ingestion = ResearchSourceIngestionService(knowledge, Path(directory) / "cache")
            for source in self.dataset["sources"]:
                result = ingestion.ingest(SourceIngestionRequest(
                    source_type="paper",
                    source_id=source["source_id"],
                    location=str(ROOT / source["location"]),
                ))
                self.assertEqual(result.status, "completed")
            resolved = _resolve_labels(db, self.dataset["cases"])
        self.assertEqual(set(resolved), {case["case_id"] for case in self.dataset["cases"]})
        self.assertTrue(all(chunk_ids for chunk_ids in resolved.values()))
        db.close()
        engine.dispose()

    def test_saved_modes_use_the_required_backends(self):
        bm25 = json.loads((RESULTS / "document-retrieval-bm25.json").read_text(encoding="utf-8"))
        vector = json.loads((RESULTS / "document-retrieval-vector.json").read_text(encoding="utf-8"))
        hybrid = json.loads((RESULTS / "document-retrieval-hybrid.json").read_text(encoding="utf-8"))
        self.assertTrue(all(not row["backend"]["vector_enabled"] for row in bm25["cases"]))
        self.assertTrue(all(set(item["retrieved_by"]) == {"bm25"} for row in bm25["cases"] for item in row["top_5"]))
        self.assertTrue(all(row["backend"]["chroma_query_used"] and not row["backend"]["bm25_used"] for row in vector["cases"]))
        self.assertTrue(all(set(item["retrieved_by"]) == {"vector"} for row in vector["cases"] for item in row["top_5"]))
        self.assertTrue(all(row["backend"]["chroma_query_used"] and row["backend"]["bm25_used"] for row in hybrid["cases"]))
        self.assertTrue(any(set(item["retrieved_by"]) == {"bm25", "vector"} for row in hybrid["cases"] for item in row["top_5"]))

    def test_vector_fallback_invalidates_run_without_leaking_reason(self):
        report = {"cases": [{
            "case_id": "case-1",
            "backend": {
                "fallback_used": True,
                "chroma_query_used": False,
                "fallback_reason": "Bearer secret-token sk-secret-value",
            },
        }]}
        with self.assertRaises(RuntimeError) as context:
            _require_live_vector("vector", report)
        self.assertIn("case-1", str(context.exception))
        self.assertNotIn("secret-token", str(context.exception))
        self.assertNotIn("sk-secret", str(context.exception))

    def test_evidence_hit_mrr_and_source_hit_are_distinct(self):
        rows = [
            {"first_expected_rank": 1, "source_hit_at_5": True},
            {"first_expected_rank": 3, "source_hit_at_5": True},
            {"first_expected_rank": None, "source_hit_at_5": True},
            {"first_expected_rank": None, "source_hit_at_5": False},
        ]
        metrics = _metrics(rows)
        self.assertEqual(metrics["evidence_hit_at_1"], 0.25)
        self.assertEqual(metrics["evidence_hit_at_3"], 0.5)
        self.assertEqual(metrics["evidence_hit_at_5"], 0.5)
        self.assertAlmostEqual(metrics["mrr"], (1 + 1 / 3) / 4)
        self.assertEqual(metrics["source_hit_at_5"], 0.75)


if __name__ == "__main__":
    unittest.main()
