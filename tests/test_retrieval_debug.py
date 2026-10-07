from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.models.entities import KnowledgeChunk
from app.services.knowledge import KnowledgeService, SearchResult
from app.services.vector_store import VectorSearchHit


class FakeVectorStore:
    can_embed = True
    error = ""

    def __init__(self, rows, *, failure=False):
        self.rows = rows
        self.failure = failure

    def count(self):
        return len(self.rows)

    def has_exact_chunk_ids(self, rows):
        return True

    def embed_texts(self, texts):
        if self.failure:
            raise RuntimeError("Bearer secret-token sk-secret-value")
        return [[0.1, 0.2] for _ in texts]

    def query(self, query_embedding, top_k, corpus=None):
        row = self.rows[0]
        return [VectorSearchHit(row.id, row.source, row.source_index, row.content, 0.82)]


class RetrievalDebugTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.settings = Settings(
            knowledge_vector_enabled=False,
            knowledge_rerank_enabled=True,
            knowledge_candidate_k=8,
        )
        self.service = KnowledgeService(self.db, self.settings)
        self.service.ensure_chunks("research:debug", [
            "alpha function increases a number by one",
            "beta function decreases a number",
        ], metadata=[
            {"file_path": "alpha.py", "symbol": "add_one", "qualified_symbol": "add_one", "content_type": "source_code"},
            {"file_path": "beta.py", "symbol": "subtract_one", "qualified_symbol": "subtract_one", "content_type": "source_code"},
        ])
        self.rows = self.db.query(KnowledgeChunk).order_by(KnowledgeChunk.id).all()
        for row in self.rows:
            row.embedding_json = "[0.1,0.2]"
        self.db.commit()
        self.settings.knowledge_vector_enabled = True

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_vector_and_bm25_contributions_are_separate(self):
        self.service.vector_store = FakeVectorStore(self.rows)
        debug = self.service.retrieve_debug("alpha function number", 2, corpus="research")
        top = debug.diagnostics[0]
        self.assertEqual(top.retrieved_by, ["bm25", "vector"])
        self.assertIsNotNone(top.bm25_score)
        self.assertIsNotNone(top.vector_score)
        self.assertIsNotNone(top.fusion_score)
        self.assertIsNotNone(top.rerank_score)
        self.assertEqual(top.qualified_symbol, "add_one")
        self.assertEqual(top.final_rank, 1)
        self.assertTrue(debug.backend.chroma_query_used)
        self.assertFalse(debug.backend.fallback_used)

    def test_vector_failure_reports_sanitized_bm25_fallback(self):
        self.service.vector_store = FakeVectorStore(self.rows, failure=True)
        debug = self.service.retrieve_debug("alpha function number", 2, corpus="research")
        self.assertTrue(debug.results)
        self.assertTrue(debug.backend.fallback_used)
        self.assertFalse(debug.backend.chroma_query_used)
        self.assertEqual(debug.backend.fallback_reason, "RuntimeError")
        self.assertNotIn("secret", str(debug.backend))
        self.assertTrue(all(item.retrieved_by == ["bm25"] for item in debug.diagnostics))
        self.assertTrue(all(item.vector_score is None for item in debug.diagnostics))

    def test_debug_mode_does_not_alter_ranking(self):
        self.service.vector_store = FakeVectorStore(self.rows)
        normal = self.service.retrieve("alpha function number", 2, corpus="research")
        debug = self.service.retrieve_debug("alpha function number", 2, corpus="research")
        self.assertEqual([item.chunk_id for item in normal], [item.chunk_id for item in debug.results])
        self.assertEqual([item.score for item in normal], [item.score for item in debug.results])

    def test_normal_return_type_remains_compatible(self):
        self.service.vector_store = FakeVectorStore(self.rows)
        results = self.service.retrieve("alpha function number", 2, corpus="research")
        self.assertIsInstance(results, list)
        self.assertTrue(all(isinstance(item, SearchResult) for item in results))
        self.assertFalse(hasattr(results[0], "retrieved_by"))


if __name__ == "__main__":
    unittest.main()
