from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.agents.research_types import ResearchSourceType
from app.services.knowledge import KnowledgeService
from app.services.research_translation import load_translation_cache
from app.services.repository_evidence import load_repository_chunks


class RepositoryFileSource(BaseModel):
    file_path: str
    raw_file: str
    content_type: str = "source_code"
    language: str = "python"
    repository_url: HttpUrl
    commit: str
    source_url: HttpUrl


class ResearchCorpusSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=1)
    source_type: ResearchSourceType
    source_url: HttpUrl
    retrieved_at: date
    original_format: str = Field(min_length=1)
    conversion_method: str = Field(min_length=1)
    verified: bool = False
    repository_url: HttpUrl | None = None
    branch: str | None = None
    commit: str | None = None
    tag: str | None = None
    raw_file: str | None = None
    processed_file: str = "content.md"
    normalized_file: str | None = None
    normalization_method: str | None = None
    normalized_from: str | None = None
    references_excluded_from_retrieval: bool = False
    repository_files: list[RepositoryFileSource] = Field(default_factory=list)

    @property
    def namespace(self) -> str:
        return f"research:{self.source_id}"


class ResearchCorpusLoader:
    """Thin adapter from provenance-backed files to the existing KnowledgeService."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def discover(self) -> list[tuple[ResearchCorpusSource, Path]]:
        sources = []
        for metadata_path in sorted(self.root.glob("*/source.json")):
            metadata = ResearchCorpusSource.model_validate_json(metadata_path.read_text(encoding="utf-8"))
            if metadata.normalized_file:
                project_root = self.root.parents[1]
                content_path = project_root / metadata.normalized_file
            else:
                content_path = metadata_path.parent / metadata.processed_file
            if not content_path.is_file():
                raise FileNotFoundError(f"Missing processed corpus for {metadata.namespace}: {content_path}")
            sources.append((metadata, content_path))
        return sources

    def bootstrap(
        self, knowledge: KnowledgeService, *, include_translations: bool = True
    ) -> list[tuple[ResearchCorpusSource, int]]:
        results = []
        for metadata, content_path in self.discover():
            content = content_path.read_text(encoding="utf-8")
            if not content.strip():
                raise ValueError(f"Empty processed corpus for {metadata.namespace}")
            if metadata.normalized_file:
                chunks = section_aware_chunks(
                    content,
                    knowledge.settings.knowledge_chunk_size,
                )
                chunk_metadata = [{
                    "file_path": "README.md" if metadata.source_type == ResearchSourceType.REPOSITORY else metadata.normalized_file,
                    "symbol": markdown_chunk_section(chunk),
                    "content_type": "documentation" if metadata.source_type == ResearchSourceType.REPOSITORY else "paper",
                    "commit": metadata.commit,
                    "repository_url": str(metadata.repository_url) if metadata.repository_url else None,
                    "source_title": metadata.title,
                    "symbol_tokens": markdown_chunk_section(chunk),
                } for chunk in chunks]
                if metadata.repository_files:
                    repository_chunks = load_repository_chunks(self.root.parents[1], metadata)
                    chunks.extend(chunk.content for chunk in repository_chunks)
                    chunk_metadata.extend(chunk.metadata for chunk in repository_chunks)
                knowledge.register_research_chunk_metadata(metadata.namespace, chunks, chunk_metadata)
                if include_translations:
                    translation_path = self.root.parents[1] / "data" / "research_translations" / metadata.source_id / "chunks.json"
                    translations = load_translation_cache(translation_path)
                    knowledge.register_research_translations([entry.__dict__ for entry in translations])
                count = knowledge.ensure_chunks(metadata.namespace, chunks, metadata=chunk_metadata)
            else:
                count = knowledge.ensure_source(metadata.namespace, content)
            results.append((metadata, count))
        return results


def section_aware_chunks(document: str, size: int) -> list[str]:
    """Split Markdown within heading boundaries, preserving source text and section labels."""
    sections: list[tuple[str, list[str]]] = []
    heading = "Document"
    body: list[str] = []
    for line in document.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            if body:
                sections.append((heading, body))
            heading = match.group(2).strip()
            body = []
        else:
            body.append(line)
    if body:
        sections.append((heading, body))

    chunks: list[str] = []
    for section, lines in sections:
        text = "\n".join(lines).strip()
        if not text:
            continue
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
        units: list[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= size:
                units.append(paragraph)
                continue
            sentences = re.split(r"(?<=[.!?。！？])\s+", paragraph)
            current = ""
            for sentence in sentences:
                if current and len(current) + 1 + len(sentence) > size:
                    units.append(current)
                    current = sentence
                else:
                    current = f"{current} {sentence}".strip()
            if current:
                units.append(current)

        prefix = f"## {section}\n\n"
        current = ""
        for unit in units:
            candidate = f"{current}\n\n{unit}".strip() if current else unit
            if current and len(prefix) + len(candidate) > size:
                chunks.append(prefix + current)
                current = unit
            else:
                current = candidate
        if current:
            chunks.append(prefix + current)
    return chunks


def markdown_chunk_section(content: str) -> str | None:
    first = content.splitlines()[0].strip() if content else ""
    return first.lstrip("#").strip() if first.startswith("#") else None
