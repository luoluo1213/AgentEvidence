from __future__ import annotations

import hashlib
import logging
from typing import Protocol
from app.agents.evidence_selector import EvidenceSelector
from app.agents.research_types import EvidenceItem, EvidencePool, ResearchSourceType, ResearchTask, ResearchTaskType,EvidenceVerificationResult


logger = logging.getLogger(__name__)

MAX_QUERIES_PER_TASK = 4


class KnowledgeResult(Protocol):
    chunk_id: int | None
    source: str
    content: str
    score: float
    section: str | None
    content_en: str | None
    content_zh: str | None


class ResearchKnowledgeService(Protocol):
    def retrieve(
        self, query: str, top_k: int | None = None, corpus: str | None = None
    ) -> list[KnowledgeResult]:
        ...


class ResearchAgent:
    def __init__(
        self,
        knowledge_service: ResearchKnowledgeService,
        *,
        top_k: int = 8,
        max_evidence_items: int = 12,
        corpus: str | None = "research",
        evidence_selector: EvidenceSelector | None = None,
    ):
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if max_evidence_items < 1:
            raise ValueError("max_evidence_items must be at least 1")
        self.knowledge_service = knowledge_service
        self.top_k = top_k
        self.max_evidence_items = max_evidence_items
        self.corpus = corpus
        self.evidence_selector = evidence_selector or EvidenceSelector()

    def research(self, task: ResearchTask, retrieval_round: int = 1,queries: list[str] | None = None) -> EvidencePool:
        if retrieval_round < 1:
            raise ValueError("retrieval_round must be at least 1")

        # queries = self._queries_for(task)
        retrieval_queries = (
            self._normalize_queries(queries)
            if queries is not None
            else self._queries_for(task)
        )

        logger.info(
            "research started; task_id=%s task_type=%s number_of_queries=%d",
            task.task_id,
            task.task_type.value,
            len(retrieval_queries),
        )

        result_groups: list[tuple[str, list[KnowledgeResult]]] = []
        for query_index, query in enumerate(retrieval_queries, start=1):
            try:
                results = self.knowledge_service.retrieve(query, self.top_k, corpus=self.corpus)
            except Exception as exc:
                logger.warning(
                    "retrieval query failed; task_id=%s query_index=%d error_type=%s",
                    task.task_id,
                    query_index,
                    type(exc).__name__,
                )
                continue
            result_groups.append((query, list(results)))
            logger.info(
                "retrieval query completed; task_id=%s query_index=%d result_count=%d",
                task.task_id,
                query_index,
                len(results),
            )

        # pool = self._prefer_expected_sources(
        #     task,
        #     self._round_robin_merge(result_groups, retrieval_round, limit=self.max_evidence_items * 2),
        # )
        # pool = self._prefer_entity_sources(task, pool)
        # if len(pool) > self.max_evidence_items:
        #     pool = EvidencePool(items=list(pool.items)[: self.max_evidence_items])
        
        pool = self._prefer_expected_sources(
            task,
            self._round_robin_merge(
                result_groups,
                retrieval_round,
                limit=self.max_evidence_items * 3,
            ),
        )

        pool = self._prefer_entity_sources(task, pool)

        pool = self.evidence_selector.select(
            task,
            pool,
            max_items=self.max_evidence_items,
        )

        logger.info(
            "research completed; task_id=%s evidence_count=%d unique_source_count=%d",
            task.task_id,
            len(pool),
            len(pool.source_ids()),
        )
        return pool

    def _queries_for(self, task: ResearchTask) -> list[str]:
        candidates = task.research_questions or [task.query]
        if task.task_type == ResearchTaskType.FACT_LOOKUP:
            candidates = candidates[:1]
        queries = []
        seen = set()
        for candidate in candidates:
            query = _unwrap_current_question(candidate.strip())
            if not query or query in seen:
                continue
            seen.add(query)
            queries.append(query)
            if len(queries) >= MAX_QUERIES_PER_TASK:
                break

        if not queries and task.query.strip():
            queries.append(_unwrap_current_question(task.query.strip()))
        return queries
    
    def _normalize_queries(
        self,
        queries: list[str],
    ) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for candidate in queries:
            query = _unwrap_current_question(
                str(candidate or "").strip()
            )

            if not query or query in seen:
                continue

            seen.add(query)
            normalized.append(query)

            if len(normalized) >= MAX_QUERIES_PER_TASK:
                break

        return normalized
    
    def repair(
        self,
        task: ResearchTask,
        evidence_pool: EvidencePool,
        verification: EvidenceVerificationResult,
    ) -> EvidencePool:
        queries = self._normalize_queries(
            verification.suggested_queries
        )

        if not queries:
            logger.info(
                "retrieval repair skipped; task_id=%s reason=no_suggested_queries",
                task.task_id,
            )
            return evidence_pool

        logger.info(
            "retrieval repair started; task_id=%s query_count=%d",
            task.task_id,
            len(queries),
        )

        repaired_pool = self.research(
            task,
            retrieval_round=2,
            queries=queries,
        )

        merged_pool = EvidencePool(
            items=list(evidence_pool.items)
        )
        merged_pool.extend(repaired_pool.items)

        merged_pool = self._prefer_expected_sources(
            task,
            merged_pool,
        )
        merged_pool = self._prefer_entity_sources(
            task,
            merged_pool,
        )

        if len(merged_pool) > self.max_evidence_items:
            round_two = [
                item
                for item in merged_pool.items
                if item.retrieval_round == 2
            ]
            previous = [
                item
                for item in merged_pool.items
                if item.retrieval_round != 2
            ]

            ordered_items: list[EvidenceItem] = []

            max_length = max(
                len(round_two),
                len(previous),
            )

            for index in range(max_length):
                if index < len(round_two):
                    ordered_items.append(round_two[index])

                if index < len(previous):
                    ordered_items.append(previous[index])

                if len(ordered_items) >= self.max_evidence_items:
                    break

            merged_pool = EvidencePool(
                items=ordered_items[: self.max_evidence_items]
            )

        logger.info(
            "retrieval repair completed; task_id=%s "
            "old_evidence=%d new_evidence=%d merged_evidence=%d",
            task.task_id,
            len(evidence_pool),
            len(repaired_pool),
            len(merged_pool),
        )

        return merged_pool

    def _round_robin_merge(
        self,
        result_groups: list[tuple[str, list[KnowledgeResult]]],
        retrieval_round: int,
        limit: int | None = None,
    ) -> EvidencePool:
        limit = self.max_evidence_items if limit is None else limit
        pool = EvidencePool()
        max_group_size = max((len(results) for _, results in result_groups), default=0)
        for rank in range(max_group_size):
            for query, results in result_groups:
                if rank >= len(results):
                    continue
                pool.add(_to_evidence(results[rank], query, retrieval_round))
                if len(pool) >= limit:
                    return pool
        return pool

    def _prefer_expected_sources(self, task: ResearchTask, pool: EvidencePool) -> EvidencePool:
        expected = list(task.expected_source_types)
        if not expected or not pool.items:
            return pool
        preferred = [item for item in pool.items if item.source_type in expected]
        others = [item for item in pool.items if item.source_type not in expected]
        if not preferred:
            return pool
        selected = preferred if len(preferred) >= min(4, self.max_evidence_items) else preferred + others
        return EvidencePool(items=selected)

    def _prefer_entity_sources(
        self,
        task: ResearchTask,
        pool: EvidencePool,
    ) -> EvidencePool:
        entities = [
            _normalize_match_text(entity)
            for entity in task.entities
            if entity and entity.strip()
        ]

        if not entities or not pool.items:
            return pool

        matching = [
            item
            for item in pool.items
            if any(
                _evidence_matches_entity(item, entity)
                for entity in entities
            )
        ]

        # 没有任何 provenance 能匹配实体时，
        # 保留原始检索结果，避免错误过滤。
        if not matching:
            return pool

        # 比较任务需要保证多个实体都有证据。
        if task.requires_comparison:
            all_entities_covered = all(
                any(
                    _evidence_matches_entity(item, entity)
                    for item in matching
                )
                for entity in entities
            )

            if not all_entities_covered:
                return pool

        return EvidencePool(items=matching)


def _to_evidence(result: KnowledgeResult, query_used: str, retrieval_round: int) -> EvidenceItem:
    source_id = str(result.source or "unknown-source")
    chunk_id = str(result.chunk_id) if result.chunk_id is not None else None
    metadata = getattr(result, "metadata", {})
    return EvidenceItem(
        evidence_id=_evidence_id(source_id, chunk_id, result.content),
        source_id=source_id,
        source_title=source_id,
        source_type=_source_type(source_id, metadata),
        section=getattr(result, "section", None),
        content=result.content,
        canonical_content=getattr(result, "content_en", None) or result.content,
        display_content=getattr(result, "content_zh", None) or result.content,
        translated_content=getattr(result, "content_zh", None),
        score=float(result.score) if result.score is not None else None,
        query_used=query_used,
        retrieval_round=retrieval_round,
        chunk_id=chunk_id,
        metadata={
            **metadata,
            "canonical_language": getattr(result, "canonical_language", "en"),
            "translation_status": getattr(result, "translation_status", "missing"),
            "translation_method": getattr(result, "translation_method", None),
            "translation_verified": getattr(result, "translation_verified", False),
        },
    )


def _evidence_id(source_id: str, chunk_id: str | None, content: str) -> str:
    if chunk_id is not None:
        return f"{source_id}:{chunk_id}"
    digest = hashlib.sha256(f"{source_id}\0{content}".encode("utf-8")).hexdigest()[:20]
    return f"{source_id}:{digest}"


def _unwrap_current_question(query: str) -> str:
    marker = "Current research question:"
    if marker in query:
        current = query.split(marker, 1)[-1].strip()
        if current:
            return current
    return query


def _source_type(source: str, metadata: dict | None = None) -> ResearchSourceType:
    metadata = metadata or {}
    explicit_type = str(metadata.get("source_type") or "").lower()
    if explicit_type in {item.value for item in ResearchSourceType}:
        return ResearchSourceType(explicit_type)
    if metadata.get("repository_url") or metadata.get("commit") or metadata.get("content_type") == "source_code":
        return ResearchSourceType.REPOSITORY
    lowered = source.lower()
    if any(term in lowered for term in ("github", "repository", "repo/", "repo-")):
        return ResearchSourceType.REPOSITORY
    if any(term in lowered for term in ("arxiv", "paper", ".pdf")):
        return ResearchSourceType.PAPER
    if any(term in lowered for term in ("readme", "documentation", "docs", "manual")):
        return ResearchSourceType.DOCUMENTATION
    if any(term in lowered for term in ("benchmark", "eval", "leaderboard")):
        return ResearchSourceType.BENCHMARK
    return ResearchSourceType.OTHER


def _normalize_match_text(text: str) -> str:
    return "".join(character.lower() for character in text if character.isalnum())


def _evidence_matches_entity(item: EvidenceItem, normalized_entity: str) -> bool:
    provenance = " ".join(str(value or "") for value in (
        item.source_id,
        item.source_title,
        item.metadata.get("source_title"),
        item.metadata.get("repository_url"),
        item.metadata.get("file_path"),
    ))
    return bool(normalized_entity) and normalized_entity in _normalize_match_text(provenance)
