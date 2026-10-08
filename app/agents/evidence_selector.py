from __future__ import annotations

import re

from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    ResearchTask,
)


_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
    "with", "how", "does", "do", "is", "are", "each", "method",
    "agent", "agents", "use", "using", "what", "which", "their",
}

_BENCHMARK_TERMS = {
    "benchmark",
    "performance",
    "result",
    "results",
    "accuracy",
    "success rate",
    "score",
    "evaluation",
    "experiment",
    "ablation",
}


class EvidenceSelector:
    """
    Lightweight deterministic evidence selection.

    Goals:
    - preserve source coverage for multi-source tasks;
    - prefer query-relevant and entity-relevant evidence;
    - down-rank obvious table/noise chunks when the task is not asking
      about experimental results;
    - enforce the final evidence budget.
    """

    def select(
        self,
        task: ResearchTask,
        pool: EvidencePool,
        *,
        max_items: int,
    ) -> EvidencePool:
        if max_items < 1 or not pool.items:
            return EvidencePool()

        ranked = sorted(
            pool.items,
            key=lambda item: self._score(task, item),
            reverse=True,
        )

        selected: list[EvidenceItem] = []

        # Multi-source comparison: reserve evidence for each target source.
        if task.requires_multiple_sources:
            target_sources = self._target_sources(task, ranked)

            if len(target_sources) >= 2:
                per_source = max(
                    1,
                    min(2, max_items // len(target_sources)),
                )

                for source_id in target_sources:
                    source_items = [
                        item
                        for item in ranked
                        if item.source_id == source_id
                    ]

                    for item in source_items[:per_source]:
                        self._append_unique(selected, item)

        # Fill remaining slots globally by quality score.
        for item in ranked:
            if len(selected) >= max_items:
                break

            self._append_unique(selected, item)

        return EvidencePool(items=selected[:max_items])

    def _score(
        self,
        task: ResearchTask,
        item: EvidenceItem,
    ) -> float:
        retrieval_score = float(item.score or 0.0)

        relevance = self._query_overlap(task, item)
        entity_match = self._entity_match(task, item)

        penalty = self._quality_penalty(task, item)

        return (
            0.55 * retrieval_score
            + 0.35 * relevance
            + 0.10 * entity_match
            - penalty
        )

    def _query_overlap(
        self,
        task: ResearchTask,
        item: EvidenceItem,
    ) -> float:
        query_text = " ".join(
            [task.query, *task.research_questions]
        )

        query_tokens = self._tokens(query_text)
        content_tokens = self._tokens(item.content)

        if not query_tokens or not content_tokens:
            return 0.0

        overlap = query_tokens & content_tokens

        return min(
            1.0,
            len(overlap) / max(1, len(query_tokens)),
        )

    def _entity_match(
        self,
        task: ResearchTask,
        item: EvidenceItem,
    ) -> float:
        provenance = self._provenance(item)

        for entity in task.entities:
            normalized = self._normalize(entity)

            if normalized and normalized in provenance:
                return 1.0

        return 0.0

    def _quality_penalty(
        self,
        task: ResearchTask,
        item: EvidenceItem,
    ) -> float:
        text = item.content.strip()

        if not text:
            return 0.50

        query_lower = task.query.lower()

        asks_for_results = any(
            term in query_lower
            for term in _BENCHMARK_TERMS
        )

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        penalty = 0.0

        # 极短 chunk：上下文不足
        if len(text) < 300:
            penalty += 0.10

        if lines:
            short_lines = sum(
                1
                for line in lines
                if len(line) <= 30
            )

            numeric_lines = sum(
                1
                for line in lines
                if re.fullmatch(
                    r"[\d.%+\-()]+",
                    line,
                )
            )

            short_ratio = short_lines / len(lines)
            numeric_ratio = numeric_lines / len(lines)

            # 当前问题不是实验结果问题时，
            # 强烈降权表格型 evidence
            if not asks_for_results:
                if short_ratio >= 0.50:
                    penalty += 0.30

                if numeric_ratio >= 0.15:
                    penalty += 0.20

        # 标题页 / 作者信息型 chunk
        lower = text.lower()

        author_markers = (
            "university",
            "institute of technology",
            "@",
            "abstract",
        )

        marker_count = sum(
            marker in lower
            for marker in author_markers
        )

        if marker_count >= 3:
            penalty += 0.15

        return min(penalty, 0.50)

    def _target_sources(
        self,
        task: ResearchTask,
        items: list[EvidenceItem],
    ) -> list[str]:
        matched_sources: list[str] = []

        for entity in task.entities:
            normalized_entity = self._normalize(entity)

            for item in items:
                if (
                    normalized_entity
                    and normalized_entity
                    in self._provenance(item)
                    and item.source_id not in matched_sources
                ):
                    matched_sources.append(item.source_id)
                    break

        # Fallback: provenance may not contain entity names.
        if len(matched_sources) < 2:
            for item in items:
                if item.source_id not in matched_sources:
                    matched_sources.append(item.source_id)

        return matched_sources

    @staticmethod
    def _append_unique(
        items: list[EvidenceItem],
        candidate: EvidenceItem,
    ) -> None:
        if any(
            item.evidence_id == candidate.evidence_id
            for item in items
        ):
            return

        items.append(candidate)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        tokens = {
            token.lower()
            for token in re.findall(
                r"[A-Za-z][A-Za-z0-9_-]{2,}",
                text,
            )
        }

        return tokens - _STOPWORDS

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(
            char.lower()
            for char in text
            if char.isalnum()
        )

    def _provenance(
        self,
        item: EvidenceItem,
    ) -> str:
        metadata = item.metadata or {}

        values = [
            item.source_id,
            item.source_title,
            metadata.get("source_title"),
            metadata.get("file_path"),
            metadata.get("repository_url"),
        ]

        return self._normalize(
            " ".join(
                str(value or "")
                for value in values
            )
        )