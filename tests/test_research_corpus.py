import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.research_agent import ResearchAgent
from app.agents.research_types import ResearchTask, ResearchTaskType
from app.core.config import Settings
from app.core.database import Base
from app.services.knowledge import KnowledgeService
from app.services.research_corpus import ResearchCorpusLoader
from app.services.vector_store import ChromaKnowledgeStore


class FakeCollection:
    def __init__(self):
        self.kwargs = None

    def query(self, **kwargs):
        self.kwargs = kwargs
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


class ResearchCorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source_dir = self.root / "react"
        source_dir.mkdir()
        (source_dir / "content.md").write_text(
            "ReAct interleaves reasoning and acting with action and observation from environment feedback.",
            encoding="utf-8",
        )
        (source_dir / "source.json").write_text(json.dumps({
            "source_id": "react", "title": "ReAct fixture", "source_type": "paper",
            "source_url": "https://arxiv.org/abs/2210.03629", "retrieved_at": "2026-10-01",
            "original_format": "pdf", "conversion_method": "fixture_copy", "verified": False,
        }), encoding="utf-8")
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.service = KnowledgeService(self.db, Settings(
            knowledge_vector_enabled=False, knowledge_chunk_size=60, knowledge_chunk_overlap=0,
        ))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_metadata_parsing_and_namespace(self):
        metadata, path = ResearchCorpusLoader(self.root).discover()[0]
        self.assertEqual(metadata.namespace, "research:react")
        self.assertFalse(metadata.verified)
        self.assertEqual(path.name, "content.md")

    def test_bootstrap_is_idempotent(self):
        loader = ResearchCorpusLoader(self.root)
        first = loader.bootstrap(self.service)
        count = self.service.count()
        second = loader.bootstrap(self.service)
        self.assertEqual(first[0][1], second[0][1])
        self.assertEqual(count, self.service.count())

    def test_research_filter_and_legacy_compatibility(self):
        ResearchCorpusLoader(self.root).bootstrap(self.service)
        self.service.ingest("psychology.md", "Reasoning observation environment feedback psychology")
        research = self.service.retrieve("reasoning observation", 8, corpus="research")
        legacy = self.service.retrieve("reasoning observation", 8)
        psychology = self.service.retrieve("reasoning observation", 8, corpus="psychology")
        self.assertTrue(research)
        self.assertTrue(all(item.source.startswith("research:") for item in research))
        self.assertIn("psychology.md", [item.source for item in legacy])
        self.assertTrue(all(not item.source.startswith("research:") for item in psychology))

    def test_research_agent_returns_research_only(self):
        ResearchCorpusLoader(self.root).bootstrap(self.service)
        self.service.ingest("psychology.md", "ReAct reasoning action observation")
        task = ResearchTask(task_id="x", query="ReAct reasoning action observation", task_type=ResearchTaskType.FACT_LOOKUP)
        pool = ResearchAgent(self.service).research(task)
        self.assertTrue(pool.items)
        self.assertTrue(all(item.source_id.startswith("research:") for item in pool.items))

    def test_vector_query_uses_corpus_metadata_filter(self):
        store = ChromaKnowledgeStore.__new__(ChromaKnowledgeStore)
        store.collection = FakeCollection()
        store.query([0.1], 4, corpus="research")
        self.assertEqual(store.collection.kwargs["where"], {"corpus": "research"})


if __name__ == "__main__":
    unittest.main()
