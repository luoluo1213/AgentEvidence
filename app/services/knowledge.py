from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Hashable

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import KnowledgeChunk
from app.services.vector_store import FALLBACK_RETRIEVAL_LABEL, PRIMARY_RETRIEVAL_LABEL, ChromaKnowledgeStore
from app.services.knowledge_sections import markdown_section


logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    chunk_id: int | None
    source: str
    content: str
    score: float
    section: str | None = None
    content_en: str | None = None
    content_zh: str | None = None
    canonical_language: str = "en"
    translation_status: str = "not_applicable"
    translation_method: str | None = None
    translation_verified: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievalCandidate:
    result: SearchResult
    vector_score: float = 0.0
    bm25_score: float = 0.0


@dataclass(frozen=True)
class RetrievalBackendStatus:
    vector_enabled: bool
    embedding_backend: str | None
    embedding_model: str | None
    chroma_query_used: bool
    bm25_used: bool
    fallback_used: bool
    fallback_reason: str | None


@dataclass(frozen=True)
class RetrievalResultDiagnostic:
    chunk_id: int | None
    source_id: str
    file_path: str | None
    section: str | None
    symbol: str | None
    qualified_symbol: str | None
    final_rank: int
    final_score: float
    bm25_score: float | None
    vector_score: float | None
    fusion_score: float | None
    rerank_score: float | None
    retrieved_by: list[str]


@dataclass(frozen=True)
class RetrievalDebugResult:
    results: list[SearchResult]
    backend: RetrievalBackendStatus
    diagnostics: list[RetrievalResultDiagnostic]


@dataclass(frozen=True)
class _RetrievalRun:
    results: list[SearchResult]
    ranked: list[SearchResult]
    vector_results: list[SearchResult]
    bm25_results: list[SearchResult]
    vector_query_used: bool
    vector_failure_reason: str | None


@dataclass
class Bm25Document:
    id: int | None
    content: str


class KnowledgeService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.vector_store = ChromaKnowledgeStore(settings)
        self._research_translations: dict[tuple[str, str], dict] = {}
        self._research_chunk_metadata: dict[tuple[str, str], dict] = {}

    def register_research_translations(self, entries: list[dict]) -> None:
        for entry in entries:
            content_en = entry.get("content_en")
            source = entry.get("source_id")
            if source and content_en:
                self._research_translations[(source, content_en)] = entry

    def register_research_chunk_metadata(
        self, source: str, chunks: list[str], metadata: list[dict]
    ) -> None:
        if len(chunks) != len(metadata):
            raise ValueError("Research chunk metadata count must match chunk count")
        for content, values in zip(chunks, metadata):
            self._research_chunk_metadata[(source, content)] = values

    def count(self) -> int:
        return self.db.query(KnowledgeChunk).count()

    def ensure_source(self, source: str, content: str) -> int:
        chunks = chunk_text(content, self.settings.knowledge_chunk_size, self.settings.knowledge_chunk_overlap)
        return self.ensure_chunks(source, chunks)

    def ensure_chunks(self, source: str, chunks: list[str], metadata: list[dict] | None = None) -> int:
        if metadata is not None and len(chunks) != len(metadata):
            raise ValueError("Research chunk metadata count must match chunk count")
        existing_rows = (
            self.db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.source == source)
            .order_by(KnowledgeChunk.source_index.asc())
            .all()
        )
        existing = [chunk.content for chunk in existing_rows]
        if existing == chunks:
            changed = False
            for index, chunk in enumerate(existing_rows):
                values = metadata[index] if metadata is not None else self._research_chunk_metadata.get((source, chunk.content))
                if values is not None:
                    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True)
                    if chunk.metadata_json != encoded:
                        chunk.metadata_json = encoded
                        changed = True
            if changed:
                self.db.commit()
            return len(existing)
        return self.ingest_chunks(source, chunks, metadata=metadata)

    def status(self) -> dict:
        vector_chunks = None
        vector_error = getattr(self.vector_store, "error", "")
        if self.vector_store.can_embed:
            try:
                vector_chunks = self.vector_store.count()
            except Exception as exc:
                vector_error = f"{type(exc).__name__}: {exc}"
        return {
            "retrievalOrder": [
                PRIMARY_RETRIEVAL_LABEL,
                f"{FALLBACK_RETRIEVAL_LABEL} when OPENAI_API_KEY/chromadb/vector call is unavailable",
            ],
            "primaryRetrieval": PRIMARY_RETRIEVAL_LABEL,
            "fallbackRetrieval": FALLBACK_RETRIEVAL_LABEL,
            "databaseChunks": self.count(),
            "vectorEnabled": self.settings.knowledge_vector_enabled,
            "vectorAvailable": self.vector_store.can_embed,
            "vectorRequired": self.settings.knowledge_vector_required,
            "embeddingModel": self.settings.openai_embedding_model,
            "vectorChunks": vector_chunks,
            "chromaPersistDir": self.settings.chroma_persist_dir,
            "chromaCollectionName": self.settings.chroma_collection_name,
            "chromaSnapshotDir": self.settings.chroma_snapshot_dir,
            "candidateK": self.settings.knowledge_candidate_k,
            "hybridVectorWeight": self.settings.knowledge_hybrid_vector_weight,
            "hybridBm25Weight": self.settings.knowledge_hybrid_bm25_weight,
            "rerankEnabled": self.settings.knowledge_rerank_enabled,
            "vectorError": vector_error,
        }

    def rebuild_vector_index(self) -> int:
        if not self.vector_store.can_embed:
            raise RuntimeError(getattr(self.vector_store, "error", "") or "Chroma 向量库不可用")
        rows = self.db.query(KnowledgeChunk).order_by(KnowledgeChunk.source.asc(), KnowledgeChunk.source_index.asc()).all()
        self._sync_vector_chunks(rows)
        self.db.commit()
        return len(rows)

    def backup_vector_index(self) -> str:
        if not self.vector_store.can_embed:
            raise RuntimeError(getattr(self.vector_store, "error", "") or "Chroma 向量库不可用")
        snapshot = self.vector_store.snapshot()
        if snapshot is None:
            raise RuntimeError("Chroma 持久化目录不存在，无法生成快照")
        return snapshot

    def ingest(self, source: str, content: str) -> int:
        chunks = chunk_text(content, self.settings.knowledge_chunk_size, self.settings.knowledge_chunk_overlap)
        return self.ingest_chunks(source, chunks)

    def ingest_chunks(self, source: str, chunks: list[str], metadata: list[dict] | None = None) -> int:
        if metadata is not None and len(chunks) != len(metadata):
            raise ValueError("Research chunk metadata count must match chunk count")
        self._delete_vector_source(source)
        self.db.query(KnowledgeChunk).filter(KnowledgeChunk.source == source).delete()
        rows = []
        for index, chunk in enumerate(chunks):
            values = metadata[index] if metadata is not None else self._research_chunk_metadata.get((source, chunk), {})
            row = KnowledgeChunk(
                source=source,
                source_index=index,
                content=chunk,
                metadata_json=json.dumps(values, ensure_ascii=False, sort_keys=True),
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        self._index_vector_chunks(rows)
        self.db.commit()
        return len(chunks)

    def ingest_file(self, filename: str, data: bytes) -> int:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            text = extract_pdf(data)
        else:
            text = data.decode("utf-8", errors="ignore")
        return self.ingest(filename, text)

    def retrieve(self, query: str, top_k: int | None = None, corpus: str | None = None) -> list[SearchResult]:
        return self._retrieve_run(query, top_k, corpus).results

    def retrieve_debug(
        self, query: str, top_k: int | None = None, corpus: str | None = None
    ) -> RetrievalDebugResult:
        run = self._retrieve_run(query, top_k, corpus)
        fallback_reason = run.vector_failure_reason
        if self.settings.knowledge_vector_enabled and not self.vector_store.can_embed and not fallback_reason:
            fallback_reason = _sanitized_backend_reason(getattr(self.vector_store, "error", "vector backend unavailable"))
        fallback_used = bool(self.settings.knowledge_vector_enabled and fallback_reason)
        return RetrievalDebugResult(
            results=run.results,
            backend=RetrievalBackendStatus(
                vector_enabled=bool(self.settings.knowledge_vector_enabled),
                embedding_backend="openai-compatible" if self.settings.knowledge_vector_enabled else None,
                embedding_model=self.settings.openai_embedding_model if self.settings.knowledge_vector_enabled else None,
                chroma_query_used=run.vector_query_used,
                bm25_used=True,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason if fallback_used else None,
            ),
            diagnostics=self._retrieval_diagnostics(query, run),
        )

    def _retrieve_run(self, query: str, top_k: int | None, corpus: str | None) -> _RetrievalRun:
        top_k = top_k or self.settings.knowledge_top_k
        candidate_k = self._candidate_k(top_k)
        chunks = self._chunks_for_corpus(corpus)
        # Primary retrieval now uses hybrid recall: semantic vector candidates
        # plus BM25 keyword candidates, followed by deterministic local rerank.
        vector_results, vector_query_used, vector_failure_reason = self._retrieve_vector_with_status(query, candidate_k, corpus)
        bm25_results = self._retrieve_bm25(query, candidate_k, chunks)
        ranked = self._fuse_and_rerank(query, vector_results, bm25_results, top_k)
        results = self._expand_best(ranked, top_k) if ranked else []
        return _RetrievalRun(
            results=results,
            ranked=ranked,
            vector_results=vector_results,
            bm25_results=bm25_results,
            vector_query_used=vector_query_used,
            vector_failure_reason=vector_failure_reason,
        )

    def _chunks_for_corpus(self, corpus: str | None) -> list[KnowledgeChunk]:
        if corpus not in {None, "research"}:
            raise ValueError(f"Unsupported corpus: {corpus}")

        return self.db.query(KnowledgeChunk).all()

    def _retrieve_bm25(self, query: str, top_k: int, chunks: list[KnowledgeChunk] | None = None) -> list[SearchResult]:
        chunks = chunks if chunks is not None else self.db.query(KnowledgeChunk).all()
        retrieval_documents = [
            Bm25Document(chunk.id, self._retrieval_text(chunk))
            for chunk in chunks
        ]
        scores = bm25_scores(query, retrieval_documents)
        ranked = [
            self._search_result(chunk, scores.get(chunk.id, 0.0))
            for chunk in chunks
            if chunk.id is not None and scores.get(chunk.id, 0.0) > 0
        ]
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    def _translation_for(self, source: str, content: str) -> dict | None:
        return self._research_translations.get((source, content)) if source.startswith("research:") else None

    def _retrieval_text(self, chunk: KnowledgeChunk) -> str:
        translation = self._translation_for(chunk.source, chunk.content)
        content_zh = translation.get("content_zh") if translation else None
        metadata = self._metadata_for(chunk)
        provenance_text = " ".join(
            str(metadata.get(key) or "")
            for key in (
                "source_title",
                "file_path",
                "symbol",
                "symbol_tokens",
                "structural_tokens",
                "identifier_aliases_zh",
                "content_type",
            )
        )
        parts = [content_zh, provenance_text, chunk.content]
        return "\n".join(part for part in parts if part)

    def _search_result(self, chunk: KnowledgeChunk, score: float) -> SearchResult:
        translation = self._translation_for(chunk.source, chunk.content)
        metadata = self._metadata_for(chunk)
        is_source_code = metadata.get("content_type") == "source_code"
        return SearchResult(
            chunk.id,
            chunk.source,
            chunk.content,
            score,
            metadata.get("symbol") or markdown_section(chunk.content),
            content_en=chunk.content if chunk.source.startswith("research:") else None,
            content_zh=translation.get("content_zh") if translation else None,
            translation_status=(
                translation.get("translation_status", "missing")
                if translation
                else (
                    "skipped_source_code"
                    if is_source_code
                    else ("missing" if chunk.source.startswith("research:") else "not_applicable")
                )
            ),
            translation_method=translation.get("translation_method") if translation else None,
            translation_verified=bool(translation.get("translation_verified", False)) if translation else False,
            metadata=metadata,
        )

    def _fuse_and_rerank(
        self,
        query: str,
        vector_results: list[SearchResult],
        bm25_results: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        candidates: dict[Hashable, RetrievalCandidate] = {}
        vector_scores = {result_key(item): item.score for item in vector_results if item.score > 0}
        bm25_scores_by_key = {result_key(item): item.score for item in bm25_results if item.score > 0}
        normalized_vector = normalize_scores(vector_scores)
        normalized_bm25 = normalize_scores(bm25_scores_by_key)

        for item in [*vector_results, *bm25_results]:
            key = result_key(item)
            candidate = candidates.get(key)
            if candidate is None:
                candidate = RetrievalCandidate(result=item)
                candidates[key] = candidate
            candidate.vector_score = max(candidate.vector_score, normalized_vector.get(key, 0.0))
            candidate.bm25_score = max(candidate.bm25_score, normalized_bm25.get(key, 0.0))

        if not candidates:
            return []

        vector_weight = max(0.0, self.settings.knowledge_hybrid_vector_weight) if vector_results else 0.0
        bm25_weight = max(0.0, self.settings.knowledge_hybrid_bm25_weight)
        if vector_weight == 0.0 and bm25_weight == 0.0:
            bm25_weight = 1.0
        total_weight = vector_weight + bm25_weight

        fused = []
        for candidate in candidates.values():
            score = (
                candidate.vector_score * vector_weight
                + candidate.bm25_score * bm25_weight
            ) / total_weight
            fused.append(replace_score(candidate.result, score))

        fused.sort(key=lambda item: item.score, reverse=True)
        fused = fused[:self._candidate_k(top_k)]
        return self._rerank(query, fused, top_k)

    def _rerank(self, query: str, candidates: list[SearchResult], top_k: int) -> list[SearchResult]:
        if not self.settings.knowledge_rerank_enabled:
            return candidates[:top_k]
        reranked = [
            replace_score(item, rerank_score(query, self._rerank_text(item), item.score))
            for item in candidates
        ]
        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked[:top_k]

    def _rerank_text(self, result: SearchResult) -> str:
        if result.chunk_id is None:
            return result.content
        chunk = self.db.get(KnowledgeChunk, result.chunk_id)
        return self._retrieval_text(chunk) if chunk is not None else result.content

    def _candidate_k(self, top_k: int) -> int:
        return max(top_k, self.settings.knowledge_candidate_k)

    def _retrieve_vector(self, query: str, top_k: int, corpus: str | None = None) -> list[SearchResult]:
        results, _, _ = self._retrieve_vector_with_status(query, top_k, corpus)
        return results

    def _retrieve_vector_with_status(
        self, query: str, top_k: int, corpus: str | None = None
    ) -> tuple[list[SearchResult], bool, str | None]:
        if not self.vector_store.can_embed:
            return [], False, None
        try:
            self._ensure_vector_index()
            query_embedding = self.vector_store.embed_texts([query])[0]
            hits = self.vector_store.query(query_embedding, top_k, corpus=corpus)
        except Exception as exc:
            self._handle_vector_error("retrieve", exc)
            return [], False, _sanitized_vector_failure(exc)
        results = []
        for hit in hits:
            chunk = self.db.get(KnowledgeChunk, hit.chunk_id) if hit.chunk_id is not None else None
            if chunk is not None:
                results.append(self._search_result(chunk, hit.score))
            else:
                results.append(SearchResult(hit.chunk_id, hit.source, hit.content, hit.score, markdown_section(hit.content)))
        return results, True, None

    def _retrieval_diagnostics(self, query: str, run: _RetrievalRun) -> list[RetrievalResultDiagnostic]:
        vector_raw = {result_key(item): item.score for item in run.vector_results if item.score > 0}
        bm25_raw = {result_key(item): item.score for item in run.bm25_results if item.score > 0}
        normalized_vector = normalize_scores(vector_raw)
        normalized_bm25 = normalize_scores(bm25_raw)
        vector_weight = max(0.0, self.settings.knowledge_hybrid_vector_weight) if run.vector_results else 0.0
        bm25_weight = max(0.0, self.settings.knowledge_hybrid_bm25_weight)
        if vector_weight == 0.0 and bm25_weight == 0.0:
            bm25_weight = 1.0
        total_weight = vector_weight + bm25_weight
        ranked_by_key = {result_key(item): item for item in run.ranked}
        diagnostics = []
        for rank, result in enumerate(run.results, start=1):
            key = result_key(result)
            fusion_score = (
                normalized_vector.get(key, 0.0) * vector_weight
                + normalized_bm25.get(key, 0.0) * bm25_weight
            ) / total_weight
            ranked = ranked_by_key.get(key)
            final_score = ranked.score if ranked is not None else result.score
            retrieved_by = []
            if key in bm25_raw:
                retrieved_by.append("bm25")
            if key in vector_raw:
                retrieved_by.append("vector")
            diagnostics.append(RetrievalResultDiagnostic(
                chunk_id=result.chunk_id,
                source_id=result.source,
                file_path=result.metadata.get("file_path"),
                section=result.section,
                symbol=result.metadata.get("symbol"),
                qualified_symbol=result.metadata.get("qualified_symbol"),
                final_rank=rank,
                final_score=final_score,
                bm25_score=bm25_raw.get(key),
                vector_score=vector_raw.get(key),
                fusion_score=fusion_score,
                rerank_score=final_score if self.settings.knowledge_rerank_enabled else None,
                retrieved_by=retrieved_by,
            ))
        return diagnostics

    def _ensure_vector_index(self) -> None:
        rows = self.db.query(KnowledgeChunk).order_by(KnowledgeChunk.source.asc(), KnowledgeChunk.source_index.asc()).all()
        if not rows:
            return
        if (
            self.vector_store.count() == len(rows)
            and all(row.embedding_json for row in rows)
            and self.vector_store.has_exact_chunk_ids(rows)
        ):
            return
        self._sync_vector_chunks(rows)
        self.db.commit()

    def _delete_vector_source(self, source: str) -> None:
        if not self.vector_store.can_embed:
            return
        try:
            self.vector_store.delete_source(source)
        except Exception as exc:
            self._handle_vector_error("delete_source", exc)

    def _index_vector_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        if not chunks or not self.vector_store.can_embed:
            return
        try:
            embeddings = self._embeddings_for_chunks(chunks)
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding_json = json.dumps(embedding, separators=(",", ":"))
            self.vector_store.upsert_chunks(chunks, embeddings)
        except Exception as exc:
            self._handle_vector_error("index", exc)

    def _sync_vector_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        if not chunks or not self.vector_store.can_embed:
            return
        try:
            embeddings = self._embeddings_for_chunks(chunks)
            for chunk, embedding in zip(chunks, embeddings):
                chunk.embedding_json = json.dumps(embedding, separators=(",", ":"))
            self.vector_store.sync_chunks(chunks, embeddings)
        except Exception as exc:
            self._handle_vector_error("sync", exc)

    def _embeddings_for_chunks(self, chunks: list[KnowledgeChunk]) -> list[list[float]]:
        embeddings: list[list[float] | None] = []
        missing_indexes = []
        missing_texts = []
        for index, chunk in enumerate(chunks):
            embedding = parse_embedding(chunk.embedding_json)
            embeddings.append(embedding)
            if embedding is None:
                missing_indexes.append(index)
                missing_texts.append(chunk.content)
        if missing_texts:
            new_embeddings = self.vector_store.embed_texts(missing_texts)
            for index, embedding in zip(missing_indexes, new_embeddings):
                embeddings[index] = embedding
        resolved = [embedding for embedding in embeddings if embedding is not None]
        if len(resolved) != len(chunks):
            raise ValueError("Embedding response count did not match knowledge chunks.")
        return resolved

    def _handle_vector_error(self, action: str, exc: Exception) -> None:
        if self.settings.knowledge_vector_required:
            raise exc
        logger.warning(
            "%s %s failed; falling back to %s: %s",
            PRIMARY_RETRIEVAL_LABEL,
            action,
            FALLBACK_RETRIEVAL_LABEL,
            _sanitized_vector_failure(exc),
        )

    def _expand_best(self, ranked: list[SearchResult], top_k: int) -> list[SearchResult]:
        if not ranked:
            return []
        best = ranked[0]
        expanded = self._expand(best)
        results = [expanded]
        for item in ranked[1:]:
            if item.chunk_id != expanded.chunk_id and len(results) < top_k:
                results.append(item)
        return results

    def _expand(self, result: SearchResult) -> SearchResult:
        if result.chunk_id is None:
            return result
        chunk = self.db.get(KnowledgeChunk, result.chunk_id)
        if chunk is None:
            return result
        neighbors = (
            self.db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.source == chunk.source)
            .filter(KnowledgeChunk.source_index >= max(0, chunk.source_index - 1))
            .filter(KnowledgeChunk.source_index <= chunk.source_index + 1)
            .order_by(KnowledgeChunk.source_index.asc())
            .all()
        )
        if chunk.source.startswith("research:"):
            section = self._section_for(chunk)
            neighbors = [item for item in neighbors if self._section_for(item) == section]
        canonical = "\n\n".join(item.content for item in neighbors)
        translations = [self._translation_for(item.source, item.content) for item in neighbors]
        translated_parts = [entry.get("content_zh") for entry in translations if entry and entry.get("content_zh")]
        return SearchResult(
            chunk.id, chunk.source, canonical, result.score, self._section_for(chunk),
            content_en=canonical if chunk.source.startswith("research:") else None,
            content_zh="\n\n".join(translated_parts) if translated_parts else None,
            translation_status="success" if translated_parts else result.translation_status,
            translation_method=result.translation_method,
            translation_verified=False,
            metadata=result.metadata,
        )

    def _section_for(self, chunk: KnowledgeChunk) -> str | None:
        metadata = self._metadata_for(chunk)
        return metadata.get("symbol") or markdown_section(chunk.content)

    def _metadata_for(self, chunk: KnowledgeChunk) -> dict:
        registered = self._research_chunk_metadata.get((chunk.source, chunk.content))
        if registered is not None:
            return registered
        try:
            value = json.loads(chunk.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}
    
    def delete_source(self, source: str, *, commit: bool = True) -> int:
        """Remove one source from Chroma and SQL storage.

        ``commit=False`` lets a caller include the SQL deletion in a wider
        transaction. Chroma is not transactional, so callers remain
        responsible for repairing the vector index if that SQL transaction
        subsequently fails.
        """
        self._delete_vector_source(source)

        deleted = self.db.query(KnowledgeChunk).filter(
            KnowledgeChunk.source == source
        ).delete()

        if commit:
            self.db.commit()
        return int(deleted)


def chunk_text(content: str, size: int, overlap: int) -> list[str]:
    text = re.sub(r"\s+", " ", content or "").strip()
    if not text:
        return []
    chunks = []
    start = 0
    step = max(1, size - overlap)
    while start < len(text):
        chunks.append(text[start:start + size])
        start += step
    return chunks


def hybrid_score(query: str, content: str) -> float:
    return token_cosine(query, content) * 0.75 + keyword_score(query, content) * 0.25


def bm25_scores(query: str, chunks: list[KnowledgeChunk | Bm25Document]) -> dict[int, float]:
    query_terms = counts(tokenize(query))
    if not query_terms or not chunks:
        return {}

    documents = []
    doc_freqs: dict[str, int] = {}
    for chunk in chunks:
        if chunk.id is None:
            continue
        token_counts = counts(tokenize(chunk.content))
        documents.append((chunk.id, token_counts, sum(token_counts.values())))
        for term in token_counts:
            doc_freqs[term] = doc_freqs.get(term, 0) + 1

    total_docs = len(documents)
    if total_docs == 0:
        return {}
    average_length = sum(length for _, _, length in documents) / total_docs or 1.0
    k1 = 1.5
    b = 0.75
    scores: dict[int, float] = {}

    for chunk_id, token_counts, doc_length in documents:
        score = 0.0
        length_norm = k1 * (1.0 - b + b * doc_length / average_length)
        for term, query_frequency in query_terms.items():
            term_frequency = token_counts.get(term, 0)
            if term_frequency == 0:
                continue
            doc_frequency = doc_freqs.get(term, 0)
            idf = math.log(1.0 + (total_docs - doc_frequency + 0.5) / (doc_frequency + 0.5))
            query_boost = 1.0 + math.log(query_frequency)
            score += idf * query_boost * (term_frequency * (k1 + 1.0)) / (term_frequency + length_norm)
        if score > 0:
            scores[chunk_id] = score
    return scores


def rerank_score(query: str, content: str, base_score: float) -> float:
    lexical = hybrid_score(query, content)
    coverage = query_token_coverage(query, content)
    phrase = phrase_score(query, content)
    return base_score * 0.55 + lexical * 0.25 + coverage * 0.15 + phrase * 0.05


def query_token_coverage(query: str, content: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    content_tokens = set(tokenize(content))
    return len(query_tokens & content_tokens) / len(query_tokens)


def phrase_score(query: str, content: str) -> float:
    normalized_query = compact_text(query)
    if not normalized_query:
        return 0.0
    normalized_content = compact_text(content)
    if normalized_query in normalized_content:
        return 1.0
    return keyword_score(query, content)


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def normalize_scores(scores: dict[Hashable, float]) -> dict[Hashable, float]:
    positives = [score for score in scores.values() if score > 0]
    if not positives:
        return {key: 0.0 for key in scores}
    lowest = min(positives)
    highest = max(positives)
    if math.isclose(lowest, highest):
        return {key: 1.0 if score > 0 else 0.0 for key, score in scores.items()}
    return {
        key: (score - lowest) / (highest - lowest) if score > 0 else 0.0
        for key, score in scores.items()
    }


def result_key(result: SearchResult) -> Hashable:
    return result.chunk_id if result.chunk_id is not None else (result.source, result.content)


def replace_score(result: SearchResult, score: float) -> SearchResult:
    return SearchResult(
        result.chunk_id, result.source, result.content, score, result.section,
        result.content_en, result.content_zh, result.canonical_language,
        result.translation_status, result.translation_method, result.translation_verified,
        result.metadata,
    )


def _sanitized_vector_failure(exc: Exception) -> str:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is not None:
        return f"{type(exc).__name__}: HTTP {status_code}"
    return type(exc).__name__


def _sanitized_backend_reason(reason: str) -> str:
    text = str(reason or "vector backend unavailable")[:240]
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(?:api[_-]?key|token|secret)\s*[=:]\s*\S+", r"\1=[REDACTED]", text)
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", text)
    return text


def parse_embedding(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list) or not data:
        return None
    if not all(isinstance(item, (int, float)) for item in data):
        return None
    return [float(item) for item in data]


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", text.lower())
    grams = words[:]
    compact = "".join(ch for ch in text.lower() if "\u4e00" <= ch <= "\u9fff")
    grams.extend(compact[i:i + 2] for i in range(max(0, len(compact) - 1)))
    return [item for item in grams if item.strip()]


def token_cosine(left: str, right: str) -> float:
    left_counts = counts(tokenize(left))
    right_counts = counts(tokenize(right))
    if not left_counts or not right_counts:
        return 0.0
    dot = sum(value * right_counts.get(key, 0) for key, value in left_counts.items())
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    return 0.0 if left_norm == 0 or right_norm == 0 else dot / (left_norm * right_norm)


def keyword_score(query: str, content: str) -> float:
    terms = [term for term in re.split(r"[\s，。！？、；：,.!?;:]+", query.lower()) if len(term) >= 2]
    if not terms:
        return 0.0
    lower = content.lower()
    matched = sum(1 for term in terms if term in lower)
    return min(1.0, matched / len(terms))


def counts(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def extract_pdf(data: bytes) -> str:
    from io import BytesIO

    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

