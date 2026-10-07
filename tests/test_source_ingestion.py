from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.services.knowledge import KnowledgeService
from app.services.source_ingestion import ResearchSourceIngestionService, SourceIngestionRequest


class FixtureRepositoryIngestion(ResearchSourceIngestionService):
    commit = "0123456789abcdef0123456789abcdef01234567"

    def _clone(self, repository_url, checkout, revision):
        checkout.mkdir(parents=True)
        (checkout / "README.md").write_text(
            "# Example\n\nThe widget parser reads tokens and returns a parsed result.", encoding="utf-8",
        )
        package = checkout / "src" / "widget"
        package.mkdir(parents=True)
        (package / "parser.py").write_text(
            "class Parser:\n    def parse(self, tokens):\n        return list(tokens)\n", encoding="utf-8",
        )
        (checkout / "asset.bin").write_bytes(b"\x00\x01")
        (checkout / "node_modules").mkdir()
        (checkout / "node_modules" / "ignored.py").write_text("x = 1", encoding="utf-8")
        return self.commit

    @staticmethod
    def _git(cwd, *arguments):
        return FixtureRepositoryIngestion.commit


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class FakePdfReader:
    def __init__(self, _path):
        self.pages = [
            FakePage("Shared Header\n1\nIntroduction\nDynamic evidence supports reproducible retrieval.\nShared Footer"),
            FakePage("Shared Header\n2\nMethod\nPage-aware chunks retain provenance metadata.\nShared Footer"),
        ]
        self.metadata = SimpleNamespace(title="Unseen Paper")


class SourceIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.settings = Settings(
            knowledge_vector_enabled=False,
            knowledge_chunk_size=180,
            knowledge_chunk_overlap=0,
        )
        self.knowledge = KnowledgeService(self.db, self.settings)
        self.service = FixtureRepositoryIngestion(self.knowledge, Path(self.temp.name) / "cache")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_repository_ingestion_records_commit_docs_code_and_symbols(self):
        result = self.service.ingest(SourceIngestionRequest(
            source_type="repository",
            source_id="research:unseen_repo",
            location="https://github.com/example/unseen-repo",
        ))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.revision, FixtureRepositoryIngestion.commit)
        self.assertGreaterEqual(result.files_processed, 2)
        self.assertGreater(result.chunks_created, 1)
        hits = self.knowledge.retrieve("Parser parse tokens", 8, corpus="research")
        hit = next(item for item in hits if item.metadata.get("symbol") == "Parser.parse")
        self.assertEqual(hit.metadata["file_path"], "src/widget/parser.py")
        self.assertEqual(hit.metadata["commit"], FixtureRepositoryIngestion.commit)
        self.assertEqual(hit.metadata["qualified_symbol"], "Parser.parse")
        self.assertEqual(hit.metadata["source_type"], "repository")
        self.assertTrue(hit.metadata["chunk_id"].startswith("repo:"))

    def test_repository_reingestion_is_idempotent(self):
        request = SourceIngestionRequest(
            source_type="repository", source_id="research:unseen_repo",
            location="https://github.com/example/unseen-repo",
        )
        first = self.service.ingest(request)
        count = self.knowledge.count()
        second = self.service.ingest(request)
        self.assertEqual(first.chunks_total, second.chunks_total)
        self.assertEqual(second.status, "unchanged")
        self.assertEqual(second.chunks_created, 0)
        self.assertEqual(self.knowledge.count(), count)

    def test_metadata_survives_new_knowledge_service_instance(self):
        self.service.ingest(SourceIngestionRequest(
            source_type="repository", source_id="research:unseen_repo",
            location="https://github.com/example/unseen-repo",
        ))
        fresh = KnowledgeService(self.db, self.settings)
        hit = next(item for item in fresh.retrieve("Parser parse tokens", 8, corpus="research") if item.source == "research:unseen_repo")
        self.assertEqual(hit.metadata["commit"], FixtureRepositoryIngestion.commit)
        self.assertEqual(hit.metadata["symbol"], "Parser.parse")

    @patch("app.services.source_ingestion.PdfReader", FakePdfReader)
    def test_pdf_ingestion_preserves_page_and_removes_repeated_edges(self):
        pdf = Path(self.temp.name) / "unseen.pdf"
        pdf.write_bytes(b"%PDF fixture")
        result = self.service.ingest(SourceIngestionRequest(
            source_type="paper", source_id="research:unseen_paper", location=str(pdf),
        ))
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.documents_processed, 1)
        fresh = KnowledgeService(self.db, self.settings)
        hits = fresh.retrieve("page-aware provenance metadata", 8, corpus="research")
        hit = next(item for item in hits if item.source == "research:unseen_paper")
        self.assertIn(hit.metadata["page"], {1, 2})
        self.assertEqual(hit.metadata["title"], "Unseen Paper")
        self.assertEqual(hit.metadata["source_type"], "paper")
        self.assertNotIn("Shared Header", hit.content)

    @patch("app.services.source_ingestion.PdfReader", FakePdfReader)
    def test_pdf_reingestion_is_idempotent(self):
        pdf = Path(self.temp.name) / "unseen.pdf"
        pdf.write_bytes(b"%PDF fixture")
        request = SourceIngestionRequest(source_type="paper", source_id="research:unseen_paper", location=str(pdf))
        self.service.ingest(request)
        count = self.knowledge.count()
        second = self.service.ingest(request)
        self.assertEqual(second.status, "unchanged")
        self.assertEqual(second.chunks_created, 0)
        self.assertEqual(self.knowledge.count(), count)

    def test_invalid_repository_url_returns_controlled_failure(self):
        result = self.service.ingest(SourceIngestionRequest(
            source_type="repository", source_id="research:bad", location="https://example.com/repo",
        ))
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.errors)

    def test_invalid_pdf_path_returns_controlled_failure(self):
        result = self.service.ingest(SourceIngestionRequest(
            source_type="paper", source_id="research:bad_pdf", location=str(Path(self.temp.name) / "missing.pdf"),
        ))
        self.assertEqual(result.status, "failed")
        self.assertIn("does not exist", result.errors[0])


if __name__ == "__main__":
    unittest.main()
