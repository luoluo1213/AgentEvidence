from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_research_document_service
from app.core.config import Settings
from app.core.database import Base
from app.main import create_app
from app.models.entities import KnowledgeChunk, ResearchDocument
from app.services.document_service import ResearchDocumentService


def _pdf_bytes() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "AgentEvidence PDF ingestion test with page provenance.")
    data = document.tobytes()
    document.close()
    return data


class DocumentApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = Settings(
            database_url=f"sqlite:///{root / 'test.db'}",
            research_upload_dir=str(root / "uploads"),
            research_pdf_max_bytes=10_000,
            knowledge_vector_enabled=False,
        )
        self.engine = create_engine(self.settings.database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.sessions = []
        self.app = create_app(self.settings, init_database=False)

        def service_override():
            session = self.Session()
            self.sessions.append(session)
            try:
                yield ResearchDocumentService(session, self.settings)
            finally:
                session.close()

        self.app.dependency_overrides[get_research_document_service] = service_override
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def upload(self, data=None, filename="paper.pdf", content_type="application/pdf"):
        return self.client.post(
            "/api/v1/documents/upload",
            files={"file": (filename, data or _pdf_bytes(), content_type)},
        )

    def test_valid_upload_list_detail_duplicate_and_delete_consistency(self):
        data = _pdf_bytes()
        uploaded = self.upload(data)
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        body = uploaded.json()
        self.assertEqual(body["status"], "completed")
        self.assertGreater(body["chunk_count"], 0)
        document_id = body["document_id"]
        source_id = body["source_id"]

        listed = self.client.get("/api/v1/documents")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        detail = self.client.get(f"/api/v1/documents/{document_id}")
        self.assertEqual(detail.json()["source_id"], source_id)

        duplicate = self.upload(data)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json()["duplicate"])
        self.assertEqual(duplicate.json()["document_id"], document_id)

        with self.Session() as session:
            self.assertEqual(session.query(ResearchDocument).count(), 1)
            chunks = session.query(KnowledgeChunk).filter(KnowledgeChunk.source == source_id).all()
            self.assertGreater(len(chunks), 0)
            provenance = json.loads(chunks[0].metadata_json)
            self.assertEqual(provenance["source_id"], source_id)
            self.assertEqual(provenance["page"], 1)

        deleted = self.client.delete(f"/api/v1/documents/{document_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertGreater(deleted.json()["removed_chunks"], 0)
        with self.Session() as session:
            self.assertEqual(session.query(ResearchDocument).count(), 0)
            self.assertEqual(session.query(KnowledgeChunk).filter(KnowledgeChunk.source == source_id).count(), 0)
        self.assertEqual(list((Path(self.settings.research_upload_dir)).glob("*.pdf")), [])

    def test_invalid_file_type_is_rejected(self):
        response = self.upload(b"not a pdf", filename="notes.txt", content_type="text/plain")
        self.assertEqual(response.status_code, 422)

    def test_oversized_file_is_rejected(self):
        data = b"%PDF-" + b"x" * self.settings.research_pdf_max_bytes
        response = self.upload(data)
        self.assertEqual(response.status_code, 422)
        self.assertIn("size limit", response.json()["error"]["message"])

    def test_missing_document_is_404(self):
        response = self.client.get("/api/v1/documents/doc_missing")
        self.assertEqual(response.status_code, 404)

    def test_delete_calls_vector_aware_source_removal_when_enabled(self):
        upload_dir = Path(self.settings.research_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored = upload_dir / "doc_vector.pdf"
        stored.write_bytes(_pdf_bytes())
        with self.Session() as session:
            session.add(ResearchDocument(
                id="doc_vector",
                source_id="research:upload_vector",
                original_filename="vector.pdf",
                stored_filename=stored.name,
                content_sha256="a" * 64,
                content_type="application/pdf",
                size_bytes=stored.stat().st_size,
                status="completed",
                chunk_count=1,
            ))
            session.add(KnowledgeChunk(
                source="research:upload_vector", source_index=0, content="content"
            ))
            session.commit()

        calls = []

        class FakeVectorAwareKnowledge:
            def __init__(self, db, settings):
                self.db = db
                self.vector_store = SimpleNamespace(can_embed=True)

            def delete_source(self, source, *, commit=True):
                calls.append((source, commit))
                return self.db.query(KnowledgeChunk).filter(KnowledgeChunk.source == source).delete()

            def rebuild_vector_index(self):
                calls.append(("rebuild", True))

        with patch("app.services.document_service.KnowledgeService", FakeVectorAwareKnowledge):
            response = self.client.delete("/api/v1/documents/doc_vector")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(calls, [("research:upload_vector", False)])
        self.assertFalse(stored.exists())


if __name__ == "__main__":
    unittest.main()
