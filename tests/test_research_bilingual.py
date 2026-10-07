import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.research_agent import ResearchAgent
from app.agents.research_types import ResearchTask, ResearchTaskType
from app.core.config import Settings
from app.core.database import Base
from app.models.entities import KnowledgeChunk
from app.services.knowledge import KnowledgeService
from app.services.research_translation import load_translation_cache, translate_chunks


class FakeTranslator:
    def __init__(self, translations=None, failure=False):
        self.translations = translations or {}
        self.failure = failure
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        if self.failure:
            raise RuntimeError("translation unavailable")
        source = messages[-1].content
        return self.translations.get(source, f"忠实翻译：{source}")


class ResearchBilingualTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.service = KnowledgeService(self.db, Settings(knowledge_vector_enabled=False))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_translation_preserves_canonical_and_attaches_to_same_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            content = "## Method\n\nObservation guides subsequent reasoning and action."
            entries, stats = translate_chunks(
                "react", [content], FakeTranslator({content: "## 方法\n\n环境观察指导后续推理和行动。"}),
                Path(directory) / "chunks.json", method="fake", provider="test", model="fake-model",
            )
            entry = entries[0]
            self.assertEqual(entry.content_en, content)
            self.assertEqual(entry.content_zh, "## 方法\n\n环境观察指导后续推理和行动。")
            self.assertEqual(entry.translation_status, "success")
            self.assertFalse(entry.translation_verified)
            self.assertEqual(stats["translated"], 1)
            self.assertIn(entry.content_hash[:16], entry.logical_chunk_id)

    def test_translation_failure_preserves_english(self):
        with tempfile.TemporaryDirectory() as directory:
            content = "canonical English"
            entries, stats = translate_chunks(
                "react", [content], FakeTranslator(failure=True), Path(directory) / "chunks.json", method="fake",
            )
            self.assertEqual(entries[0].content_en, content)
            self.assertIsNone(entries[0].content_zh)
            self.assertEqual(entries[0].translation_status, "failed")
            self.assertEqual(stats["failed"], 1)

    def test_translation_cache_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunks.json"
            translator = FakeTranslator()
            translate_chunks("react", ["same English"], translator, path, method="fake")
            entries, stats = translate_chunks("react", ["same English"], translator, path, method="fake")
            self.assertEqual(translator.calls, 1)
            self.assertEqual(stats["cached"], 1)
            self.assertEqual(len(entries), 1)
            self.assertEqual(len(load_translation_cache(path)), 1)

    def test_chinese_and_english_retrieval_share_one_logical_chunk(self):
        content = "## Method\n\nObservation guides subsequent reasoning and action."
        self.service.ensure_chunks("research:react", [content])
        self.service.register_research_translations([{
            "source_id": "research:react", "content_en": content,
            "content_zh": "## 方法\n\n环境观察指导后续推理和行动。",
            "translation_status": "success", "translation_method": "fake",
            "translation_verified": False,
        }])
        chinese = self.service.retrieve("环境观察 后续推理 行动", 4, corpus="research")
        english = self.service.retrieve("Observation subsequent reasoning action", 4, corpus="research")
        self.assertEqual(len(chinese), 1)
        self.assertEqual(len(english), 1)
        self.assertEqual(chinese[0].chunk_id, english[0].chunk_id)
        self.assertEqual(chinese[0].content, content)
        self.assertEqual(chinese[0].content_en, content)
        self.assertIsNotNone(chinese[0].content_zh)

        task = ResearchTask(task_id="bilingual", query="环境观察 后续推理 行动", task_type=ResearchTaskType.FACT_LOOKUP)
        pool = ResearchAgent(self.service).research(task)
        self.assertEqual(len(pool), 1)
        self.assertEqual(len({item.chunk_id for item in pool.items}), 1)
        self.assertEqual(pool.items[0].content, content)
        self.assertEqual(pool.items[0].canonical_content, content)
        self.assertEqual(pool.items[0].display_content, chinese[0].content_zh)
        self.assertFalse(pool.items[0].metadata["translation_verified"])

    def test_psychology_corpus_ignores_research_translation(self):
        self.service.ingest("psychology.md", "环境观察 心理支持")
        self.service.register_research_translations([{
            "source_id": "research:react", "content_en": "unrelated",
            "content_zh": "心理支持", "translation_status": "success",
        }])
        results = self.service.retrieve("心理支持", 4, corpus="psychology")
        self.assertEqual([item.source for item in results], ["psychology.md"])
        self.assertIsNone(results[0].content_en)
        self.assertEqual(results[0].translation_status, "not_applicable")


if __name__ == "__main__":
    unittest.main()
