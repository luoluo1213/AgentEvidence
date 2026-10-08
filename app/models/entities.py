from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def now() -> datetime:
    return datetime.utcnow()


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    source: Mapped[str] = mapped_column(
        String(256),
        index=True,
    )

    source_index: Mapped[int] = mapped_column(
        Integer,
    )

    content: Mapped[str] = mapped_column(
        Text,
    )

    metadata_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
    )

    embedding_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now,
    )


class ResearchDocument(Base):
    """Registry for PDFs uploaded through the public API.

    Knowledge text remains in ``KnowledgeChunk`` and vectors remain in Chroma;
    this table records the safe server-side file and ingestion lifecycle only.
    """

    __tablename__ = "research_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    stored_filename: Mapped[str] = mapped_column(String(128), unique=True)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
