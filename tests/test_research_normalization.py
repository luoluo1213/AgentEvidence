import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.models.entities import KnowledgeChunk
from app.services.knowledge import KnowledgeService, chunk_text
from app.services.research_corpus import ResearchCorpusLoader, section_aware_chunks
from scripts.normalize_research_sources import normalize_paper, normalize_readme


class ResearchNormalizationTests(unittest.TestCase):
    def test_paper_preserves_headings_and_removes_references_and_page_markers(self):
        source = """[Page 1]\nABSTRACT\nSource-derived abstract.\n1 I NTRODUCTION\nFirst paragraph.\nREFERENCES\nReference noise.\nA A DDITIONAL RESULTS\nA.1 GPT-3 E XPERIMENTS\nUseful appendix detail.\n"""
        normalized, sections = normalize_paper("react", source)
        self.assertIn("## Abstract", normalized)
        self.assertIn("## 1 Introduction", normalized)
        self.assertIn("Useful appendix detail.", normalized)
        self.assertNotIn("[Page 1]", normalized)
        self.assertNotIn("Reference noise", normalized)
        self.assertIn("A.1 GPT-3 Experiments", sections)

    def test_readme_removes_badges_images_and_installation_section(self):
        source = """# Project\n[![Badge](badge.svg)](url)\n<summary>Core design</summary>\nLinear history and bash actions.\n![demo](demo.gif)\n## Let's get started!\npip install package\n"""
        normalized, sections = normalize_readme(source)
        self.assertIn("## Core design", normalized)
        self.assertIn("Linear history and bash actions.", normalized)
        self.assertNotIn("Badge", normalized)
        self.assertNotIn("pip install", normalized)
        self.assertIn("Core design", sections)

    def test_section_chunks_have_metadata_and_do_not_cross_boundaries(self):
        chunks = section_aware_chunks("# Title\n\nIntro.\n\n## Method\n\nMethod text.\n\n## Results\n\nResult text.", 80)
        self.assertTrue(all(chunk.startswith("## ") for chunk in chunks))
        self.assertFalse(any("Method text" in chunk and "Result text" in chunk for chunk in chunks))

    def test_normalized_provenance_and_research_only_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            corpus = project / "data" / "research_corpus" / "demo"
            normalized = project / "data" / "research_normalized" / "demo"
            corpus.mkdir(parents=True)
            normalized.mkdir(parents=True)
            (corpus / "content.md").write_text("legacy raw extraction", encoding="utf-8")
            (normalized / "document.md").write_text("## Method\n\nresearch-only normalized evidence", encoding="utf-8")
            (corpus / "source.json").write_text(json.dumps({
                "source_id": "demo", "title": "Demo", "source_type": "paper",
                "source_url": "https://example.com/paper", "retrieved_at": "2026-10-01",
                "original_format": "pdf", "conversion_method": "fixture", "verified": False,
                "processed_file": "content.md",
                "normalized_file": "data/research_normalized/demo/document.md",
                "normalization_method": "structure_preserving_cleanup",
                "normalized_from": "data/research_corpus/demo/content.md",
                "references_excluded_from_retrieval": True,
            }), encoding="utf-8")
            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            db = sessionmaker(bind=engine)()
            try:
                service = KnowledgeService(db, Settings(knowledge_vector_enabled=False))
                metadata, path = ResearchCorpusLoader(project / "data" / "research_corpus").discover()[0]
                self.assertEqual(path, normalized / "document.md")
                self.assertEqual(metadata.normalized_from, "data/research_corpus/demo/content.md")
                ResearchCorpusLoader(project / "data" / "research_corpus").bootstrap(service)
                service.ingest("psychology.md", "psychology evidence")
                results = service.retrieve("normalized evidence", 4, corpus="research")
                self.assertTrue(results)
                self.assertEqual(results[0].section, "Method")
                self.assertTrue(all(item.source.startswith("research:") for item in results))
                self.assertEqual(service.retrieve("psychology", 4, corpus="psychology")[0].source, "psychology.md")
            finally:
                db.close()
                engine.dispose()

    def test_legacy_ingest_keeps_fixed_window_chunking(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            settings = Settings(knowledge_vector_enabled=False, knowledge_chunk_size=12, knowledge_chunk_overlap=2)
            service = KnowledgeService(db, settings)
            content = "legacy psychology corpus remains on its original fixed window path"
            service.ingest("psychology.md", content)
            stored = [row.content for row in db.query(KnowledgeChunk).order_by(KnowledgeChunk.source_index).all()]
            self.assertEqual(stored, chunk_text(content, 12, 2))
        finally:
            db.close()
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
