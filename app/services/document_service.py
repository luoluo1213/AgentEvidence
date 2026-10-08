from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import ResearchDocument
from app.services.knowledge import KnowledgeService
from app.services.source_ingestion import (
    IngestionSourceType,
    ResearchSourceIngestionService,
    SourceIngestionRequest,
)


class DocumentNotFoundError(LookupError):
    pass


class DocumentValidationError(ValueError):
    pass


class DocumentConsistencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DocumentUploadResult:
    document: ResearchDocument
    duplicate: bool


@dataclass(frozen=True)
class DocumentDeleteResult:
    document_id: str
    source_id: str
    removed_chunks: int


class ResearchDocumentService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        upload_dir = Path(settings.research_upload_dir)
        self.upload_dir = upload_dir if upload_dir.is_absolute() else settings.project_root / upload_dir

    def upload(self, filename: str, content_type: str | None, data: bytes) -> DocumentUploadResult:
        self._validate(filename, content_type, data)
        checksum = hashlib.sha256(data).hexdigest()
        existing = self.db.query(ResearchDocument).filter(
            ResearchDocument.content_sha256 == checksum
        ).one_or_none()
        if existing is not None:
            return DocumentUploadResult(existing, duplicate=True)

        document_id = f"doc_{uuid.uuid4().hex}"
        source_id = f"research:upload_{uuid.uuid4().hex[:24]}"
        stored_filename = f"{document_id}.pdf"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        destination = (self.upload_dir / stored_filename).resolve()
        if destination.parent != self.upload_dir.resolve():
            raise DocumentValidationError("unsafe upload path")
        temporary = destination.with_suffix(".uploading")
        temporary.write_bytes(data)
        os.replace(temporary, destination)

        document = ResearchDocument(
            id=document_id,
            source_id=source_id,
            original_filename=Path(filename).name[:512] or "document.pdf",
            stored_filename=stored_filename,
            content_sha256=checksum,
            content_type="application/pdf",
            size_bytes=len(data),
            status="processing",
            chunk_count=0,
        )
        self.db.add(document)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            destination.unlink(missing_ok=True)
            existing = self.db.query(ResearchDocument).filter(
                ResearchDocument.content_sha256 == checksum
            ).one_or_none()
            if existing is not None:
                return DocumentUploadResult(existing, duplicate=True)
            raise
        except Exception:
            self.db.rollback()
            destination.unlink(missing_ok=True)
            raise
        self.db.refresh(document)

        ingestion = ResearchSourceIngestionService(KnowledgeService(self.db, self.settings))
        result = ingestion.ingest(SourceIngestionRequest(
            source_type=IngestionSourceType.PAPER,
            source_id=source_id,
            location=str(destination),
        ))
        if result.status == "failed":
            document.status = "failed"
            document.ingestion_error = "PDF ingestion failed."
            self.db.commit()
            self.db.refresh(document)
            return DocumentUploadResult(document, duplicate=False)

        document.status = "completed"
        document.chunk_count = result.chunks_total
        document.ingestion_error = None
        self.db.commit()
        self.db.refresh(document)
        return DocumentUploadResult(document, duplicate=False)

    def list_documents(self) -> list[ResearchDocument]:
        return (
            self.db.query(ResearchDocument)
            .order_by(ResearchDocument.created_at.desc())
            .all()
        )

    def get(self, document_id: str) -> ResearchDocument:
        document = self.db.get(ResearchDocument, document_id)
        if document is None:
            raise DocumentNotFoundError("document was not found")
        return document

    def delete(self, document_id: str) -> DocumentDeleteResult:
        document = self.get(document_id)
        source_id = document.source_id
        stored_path = (self.upload_dir / document.stored_filename).resolve()
        if stored_path.parent != self.upload_dir.resolve():
            raise DocumentConsistencyError("stored document path is invalid")
        tombstone = stored_path.with_suffix(".deleting")
        if stored_path.exists():
            os.replace(stored_path, tombstone)

        knowledge = KnowledgeService(self.db, self.settings)
        vector_changed = bool(knowledge.vector_store.can_embed)
        try:
            removed = knowledge.delete_source(source_id, commit=False)
            self.db.delete(document)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            if tombstone.exists():
                os.replace(tombstone, stored_path)
            if vector_changed and knowledge.vector_store.can_embed:
                try:
                    knowledge.rebuild_vector_index()
                except Exception as repair_exc:
                    raise DocumentConsistencyError(
                        "document deletion failed and vector repair also failed"
                    ) from repair_exc
            raise DocumentConsistencyError("document deletion failed; changes were rolled back") from exc

        try:
            tombstone.unlink(missing_ok=True)
        except OSError as exc:
            raise DocumentConsistencyError(
                "indexed data was deleted, but the quarantined upload could not be removed"
            ) from exc
        return DocumentDeleteResult(document_id, source_id, removed)

    def _validate(self, filename: str, content_type: str | None, data: bytes) -> None:
        if not filename or Path(filename).suffix.lower() != ".pdf":
            raise DocumentValidationError("only PDF files are supported")
        if content_type and content_type.lower() not in {
            "application/pdf",
            "application/octet-stream",
        }:
            raise DocumentValidationError("only PDF files are supported")
        if not data:
            raise DocumentValidationError("uploaded PDF is empty")
        if len(data) > self.settings.research_pdf_max_bytes:
            raise DocumentValidationError("uploaded PDF exceeds the configured size limit")
        if not data.lstrip().startswith(b"%PDF-"):
            raise DocumentValidationError("uploaded content is not a valid PDF")
