from __future__ import annotations
import pymupdf

import hashlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from enum import Enum
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from app.models.entities import KnowledgeChunk
from app.services.knowledge import KnowledgeService
from app.services.repository_evidence import code_aware_chunks
from app.services.research_corpus import markdown_chunk_section, section_aware_chunks


class IngestionSourceType(str, Enum):
    REPOSITORY = "repository"
    PAPER = "paper"


class SourceIngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: IngestionSourceType
    source_id: str = Field(pattern=r"^research:[a-z0-9][a-z0-9_-]*$")
    location: str = Field(min_length=1)
    revision: str | None = None


class SourceIngestionResult(BaseModel):
    source_id: str
    source_type: IngestionSourceType
    status: str
    documents_processed: int = 0
    files_processed: int = 0
    chunks_created: int = 0
    chunks_total: int = 0
    skipped_files: int = 0
    skipped_chunks: int = 0
    errors: list[str] = Field(default_factory=list)
    revision: str | None = None


class ResearchSourceIngestionService:
    """Normalize repositories/PDFs into the existing research KnowledgeService."""

    _SKIP_DIRECTORIES = {
        ".git", ".hg", ".svn", ".tox", ".venv", "venv", "env", "node_modules",
        "build", "dist", "vendor", "vendors", "site-packages", "__pycache__", ".mypy_cache",
        ".pytest_cache", "coverage", "htmlcov",
    }
    _DOC_SUFFIXES = {".md", ".markdown", ".rst", ".txt"}
    _MAX_FILE_BYTES = 1_000_000

    def __init__(self, knowledge: KnowledgeService, cache_root: Path | None = None):
        self.knowledge = knowledge
        self.cache_root = Path(cache_root or knowledge.settings.project_root / "data" / "research_ingestion_cache")

    def ingest(self, request: SourceIngestionRequest) -> SourceIngestionResult:
        try:
            if request.source_type == IngestionSourceType.REPOSITORY:
                return self._ingest_repository(request)
            return self._ingest_pdf(request)
        except Exception as exc:
            self.knowledge.db.rollback()
            return SourceIngestionResult(
                source_id=request.source_id,
                source_type=request.source_type,
                status="failed",
                errors=[f"{type(exc).__name__}: {exc}"],
                revision=request.revision,
            )

    def _ingest_repository(self, request: SourceIngestionRequest) -> SourceIngestionResult:
        repository_url = _validated_github_url(request.location)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="repository-", dir=self.cache_root) as directory:
            checkout = Path(directory) / "checkout"
            commit = self._clone(repository_url, checkout, request.revision)
            title = urlparse(repository_url).path.rstrip("/").split("/")[-1]
            chunks: list[str] = []
            metadata: list[dict] = []
            files_processed = 0
            skipped_files = 0
            skipped_chunks = 0
            for path in sorted(checkout.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                relative = path.relative_to(checkout)
                if self._skip_path(relative) or path.stat().st_size > self._MAX_FILE_BYTES:
                    skipped_files += 1
                    continue
                suffix = path.suffix.lower()
                if suffix not in self._DOC_SUFFIXES and suffix != ".py":
                    skipped_files += 1
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    skipped_files += 1
                    continue
                if not content.strip():
                    skipped_files += 1
                    continue
                file_path = relative.as_posix()
                if suffix == ".py":
                    try:
                        code_chunks = code_aware_chunks(
                            content,
                            file_path=file_path,
                            commit=commit,
                            repository_url=repository_url,
                            source_title=title,
                        )
                    except SyntaxError:
                        skipped_files += 1
                        continue
                    chunks.extend(item.content for item in code_chunks)
                    for item in code_chunks:
                        values = item.metadata
                        values.update({"source_id": request.source_id, "revision": commit})
                        metadata.append(values)
                    skipped_chunks += int(not code_chunks)
                else:
                    document_chunks = section_aware_chunks(content, self.knowledge.settings.knowledge_chunk_size)
                    for chunk in document_chunks:
                        section = markdown_chunk_section(chunk)
                        chunks.append(chunk)
                        metadata.append(_metadata(
                            request.source_id,
                            commit,
                            file_path,
                            section or "Document",
                            chunk,
                            source_type="repository",
                            content_type="documentation",
                            language=_document_language(suffix),
                            source_title=title,
                            repository_url=repository_url,
                        ))
                    skipped_chunks += int(not document_chunks)
                files_processed += 1

            chunks, metadata, duplicate_count = _deduplicate(chunks, metadata)
            skipped_chunks += duplicate_count
            if not chunks:
                raise ValueError("repository contained no supported non-empty documentation or Python chunks")
            unchanged = self._is_unchanged(request.source_id, chunks, commit)
            self.knowledge.register_research_chunk_metadata(request.source_id, chunks, metadata)
            total = self.knowledge.ensure_chunks(request.source_id, chunks, metadata=metadata)
            return SourceIngestionResult(
                source_id=request.source_id,
                source_type=request.source_type,
                status="unchanged" if unchanged else "completed",
                documents_processed=files_processed,
                files_processed=files_processed,
                chunks_created=0 if unchanged else total,
                chunks_total=total,
                skipped_files=skipped_files,
                skipped_chunks=skipped_chunks,
                revision=commit,
            )

    def _ingest_pdf(self, request: SourceIngestionRequest) -> SourceIngestionResult:
        path = Path(request.location).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ValueError(f"local PDF does not exist: {path}")
        document = pymupdf.open(str(path))
        raw_pages = []

        for page in document:
            kept_blocks = []

            for block in page.get_text("blocks"):
                text = str(block[4] or "").strip()

                if not text:
                    continue

                if _is_corrupted_pdf_block(text):
                    continue

                kept_blocks.append(text)

            raw_pages.append("\n\n".join(kept_blocks))
        # raw_pages = [page.get_text("text") or ""for page in document]
        pages = _clean_pdf_pages(raw_pages)
        metadata = document.metadata or {}
        title = str(metadata.get("title") or path.stem).strip()
        document.close()

        # reader = PdfReader(str(path))
        # raw_pages = [(page.extract_text() or "") for page in reader.pages]
        # pages = _clean_pdf_pages(raw_pages)
        # title = str((reader.metadata.title if reader.metadata else "") or path.stem).strip()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        chunks: list[str] = []
        metadata: list[dict] = []
        skipped_chunks = 0
        for page_number, content in enumerate(pages, start=1):
            if not content:
                skipped_chunks += 1
                continue
            page_document = f"## Page {page_number}\n\n{content}"
            page_chunks = section_aware_chunks(page_document, self.knowledge.settings.knowledge_chunk_size)
            for chunk in page_chunks:
                chunks.append(chunk)
                values = _metadata(
                    request.source_id,
                    digest,
                    path.name,
                    markdown_chunk_section(chunk) or f"Page {page_number}",
                    chunk,
                    source_type="paper",
                    content_type="paper",
                    language="text",
                    source_title=title,
                )
                values.update({"page": page_number, "page_range": str(page_number), "title": title})
                metadata.append(values)
            skipped_chunks += int(not page_chunks)
        chunks, metadata, duplicate_count = _deduplicate(chunks, metadata)
        skipped_chunks += duplicate_count
        if not chunks:
            raise ValueError("PDF contained no extractable text")
        revision = request.revision or digest
        unchanged = self._is_unchanged(request.source_id, chunks, revision)
        for values in metadata:
            values["revision"] = revision
        self.knowledge.register_research_chunk_metadata(request.source_id, chunks, metadata)
        total = self.knowledge.ensure_chunks(request.source_id, chunks, metadata=metadata)
        return SourceIngestionResult(
            source_id=request.source_id,
            source_type=request.source_type,
            status="unchanged" if unchanged else "completed",
            documents_processed=1,
            files_processed=1,
            chunks_created=0 if unchanged else total,
            chunks_total=total,
            skipped_chunks=skipped_chunks,
            revision=revision,
        )

    def _is_unchanged(self, source_id: str, chunks: list[str], revision: str) -> bool:
        rows = (
            self.knowledge.db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.source == source_id)
            .order_by(KnowledgeChunk.source_index.asc())
            .all()
        )
        if [row.content for row in rows] != chunks or not rows:
            return False
        return all(self.knowledge._metadata_for(row).get("revision", self.knowledge._metadata_for(row).get("commit")) == revision for row in rows)

    def _clone(self, repository_url: str, checkout: Path, revision: str | None) -> str:
        if revision:
            if (
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", revision)
                or ".." in revision
                or "@{" in revision
                or revision.endswith(".lock")
            ):
                raise ValueError("revision contains unsupported characters")
        try:
            if revision:
                self._git(None, "clone", "--filter=blob:none", "--no-checkout", repository_url, str(checkout))
                self._git(checkout, "fetch", "--depth", "1", "origin", revision)
                self._git(checkout, "checkout", "--detach", "FETCH_HEAD")
            else:
                self._git(None, "clone", "--depth", "1", repository_url, str(checkout))
            return self._git(checkout, "rev-parse", "HEAD")
        except RuntimeError as git_error:
            try:
                return self._fetch_github_archive(repository_url, checkout, revision)
            except Exception as archive_error:
                raise RuntimeError(f"git fetch failed ({git_error}); GitHub archive fetch failed ({archive_error})") from archive_error

    @staticmethod
    def _fetch_github_archive(repository_url: str, checkout: Path, revision: str | None) -> str:
        parts = urlparse(repository_url).path.strip("/").split("/")
        owner, repository = parts[0], parts[1]
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "AgentEvidence-Ingestion"}
        with httpx.Client(timeout=60, follow_redirects=True, headers=headers) as client:
            if revision:
                reference = revision
            else:
                repository_response = client.get(f"https://api.github.com/repos/{owner}/{repository}")
                repository_response.raise_for_status()
                reference = repository_response.json()["default_branch"]
            commit_response = client.get(f"https://api.github.com/repos/{owner}/{repository}/commits/{reference}")
            commit_response.raise_for_status()
            commit = str(commit_response.json()["sha"])
            archive_response = client.get(f"https://api.github.com/repos/{owner}/{repository}/zipball/{commit}")
            archive_response.raise_for_status()
        if len(archive_response.content) > 50_000_000:
            raise ValueError("repository archive exceeds the 50 MB MVP limit")
        checkout.mkdir(parents=True, exist_ok=False)
        checkout_root = checkout.resolve()
        with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
            names = [Path(item.filename) for item in archive.infolist() if item.filename]
            roots = {name.parts[0] for name in names if name.parts}
            if len(roots) != 1:
                raise ValueError("GitHub archive has an unexpected root layout")
            root = next(iter(roots))
            for item in archive.infolist():
                path = Path(item.filename)
                if not path.parts or path.parts[0] != root or len(path.parts) == 1:
                    continue
                relative = Path(*path.parts[1:])
                target = (checkout / relative).resolve()
                if not target.is_relative_to(checkout_root):
                    raise ValueError("GitHub archive contains an unsafe path")
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        return commit

    @staticmethod
    def _git(cwd: Path | None, *arguments: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "git command failed").strip().splitlines()[-1]
            raise RuntimeError(detail) from exc
        return completed.stdout.strip()

    def _skip_path(self, path: Path) -> bool:
        lowered = {part.lower() for part in path.parts}
        return bool(lowered & self._SKIP_DIRECTORIES) or any(
            part.lower().endswith((".egg-info", ".min.js")) for part in path.parts
        )


def _validated_github_url(location: str) -> str:
    parsed = urlparse(location.strip())
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValueError("repository location must be a public HTTPS GitHub URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or len(path_parts) != 2:
        raise ValueError("repository URL must have the form https://github.com/owner/repository")
    repository = path_parts[1][:-4] if path_parts[1].endswith(".git") else path_parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", path_parts[0]) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository URL contains unsupported owner or repository characters")
    return f"https://github.com/{path_parts[0]}/{repository}"


def _metadata(
    source_id: str,
    revision: str,
    file_path: str,
    symbol: str,
    content: str,
    *,
    source_type: str,
    content_type: str,
    language: str,
    source_title: str,
    repository_url: str | None = None,
) -> dict:
    digest = hashlib.sha256(f"{source_id}\0{revision}\0{file_path}\0{symbol}\0{content}".encode("utf-8")).hexdigest()[:20]
    return {
        "chunk_id": f"dynamic:{digest}",
        "source_id": source_id,
        "source_type": source_type,
        "source_title": source_title,
        "revision": revision,
        "commit": revision if source_type == "repository" else None,
        "repository_url": repository_url,
        "file_path": file_path,
        "symbol": symbol,
        "qualified_symbol": symbol,
        "section": symbol,
        "content_type": content_type,
        "language": language,
        "symbol_tokens": symbol.replace(".", " ").replace("_", " "),
    }


def _deduplicate(chunks: list[str], metadata: list[dict]) -> tuple[list[str], list[dict], int]:
    unique_chunks: list[str] = []
    unique_metadata: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk, values in zip(chunks, metadata):
        key = (str(values.get("file_path")), str(values.get("symbol")), hashlib.sha256(chunk.encode("utf-8")).hexdigest())
        if key in seen:
            continue
        seen.add(key)
        unique_chunks.append(chunk)
        unique_metadata.append(values)
    return unique_chunks, unique_metadata, len(chunks) - len(unique_chunks)

def _is_corrupted_pdf_block(text: str) -> bool:
    """
    Conservatively detect obviously corrupted PDF text blocks.

    Detects:
    1. Invalid C0 control characters produced by broken PDF font mappings.
    2. Cipher-like alphanumeric tokens such as 7KLQN, 2EV, 5HPRWH.
    """
    if not text:
        return False

    # PDF 正常文本不应该包含大量 C0 控制字符。
    # \n, \r, \t 属于合法排版字符，不计入。
    control_chars = [
        char
        for char in text
        if ord(char) < 32 and char not in "\n\r\t"
    ]

    if len(control_chars) >= 2:
        return True

    normalized = re.sub(r"\s+", " ", text).strip()

    if len(normalized) < 20:
        return False

    tokens = re.findall(r"[A-Za-z0-9]+", normalized)

    if not tokens:
        return False

    # 类似 7KLQN / 2EV / 5HPRWH 这种字母数字异常混合 token
    mixed_tokens = [
        token
        for token in tokens
        if len(token) >= 3
        and re.search(r"[A-Za-z]", token)
        and re.search(r"\d", token)
    ]

    mixed_char_count = sum(len(token) for token in mixed_tokens)
    token_char_count = sum(len(token) for token in tokens)

    mixed_char_ratio = (
        mixed_char_count / token_char_count
        if token_char_count
        else 0.0
    )

    return mixed_char_ratio >= 0.20

def _clean_pdf_pages(pages: list[str]) -> list[str]:
    split_pages = [[line.strip() for line in text.splitlines() if line.strip()] for text in pages]
    edge_counts = Counter()
    for lines in split_pages:
        if lines:
            edge_counts.update(set(lines[:2] + lines[-2:]))
    threshold = max(2, (len(split_pages) + 1) // 2)
    repeated = {line for line, count in edge_counts.items() if count >= threshold and len(line) <= 160}
    page_number = re.compile(r"^(?:page\s+)?\d+(?:\s+(?:of|/|／)\s*\d+)?$", re.IGNORECASE)
    cleaned = []
    for lines in split_pages:
        kept = [line for line in lines if line not in repeated and not page_number.fullmatch(line)]
        cleaned.append(re.sub(r"[ \t]+", " ", "\n".join(kept)).strip())
    return cleaned


def _document_language(suffix: str) -> str:
    return "markdown" if suffix in {".md", ".markdown"} else suffix.lstrip(".") or "text"
