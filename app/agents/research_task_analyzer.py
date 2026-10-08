from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Protocol

from pydantic import ValidationError

from app.agents.research_types import ResearchSourceType, ResearchTask, ResearchTaskType
from app.schemas.dtos import AiMessage


logger = logging.getLogger(__name__)


TASK_ANALYZER_SYSTEM_PROMPT = """You are a research task analyzer for an AI-agent technical research system.

Your job is to transform a user's question into a structured research task. You do NOT answer the user's question.

Classify the task into exactly one supported task type:
- FACT_LOOKUP: one focused fact or mechanism can be answered from one document or a small amount of evidence.
- COMPARISON: the query explicitly compares two or more entities, systems, methods, mechanisms, or sources. This type requires comparison, but it does not necessarily require multiple sources; multiple concepts or mechanisms may be compared within a single source.
- MULTI_HOP_RESEARCH: the answer requires several intermediate questions or multiple pieces of evidence to be combined.
- PAPER_REPO_ANALYSIS: the query explicitly asks for joint analysis of a paper and code, GitHub repository, implementation, or README.
- GENERAL_RESEARCH: use only when the task cannot reliably fit another supported type.

Identify only concrete named entities that are present or clearly implied by the query. Do not invent papers, repositories, methods, benchmarks, or entities.

Break the query into the minimum set of research questions required to answer it, normally one to four. Set requires_comparison=true only when comparison is required. Set requires_multiple_sources=true only when reliable analysis needs distinct sources. Use only these source types: paper, repository, documentation, benchmark, other.

Return only one JSON object with exactly these fields:
{
  "task_type": "FACT_LOOKUP|COMPARISON|MULTI_HOP_RESEARCH|PAPER_REPO_ANALYSIS|GENERAL_RESEARCH",
  "entities": ["entity"],
  "research_questions": ["question"],
  "expected_source_types": ["paper|repository|documentation|benchmark|other"],
  "requires_comparison": false,
  "requires_multiple_sources": false
}
"""


class CompletingAiClient(Protocol):
    def complete(self, messages: list[AiMessage]) -> str:
        ...


class TaskAnalyzerAgent:
    def __init__(self, ai_client: CompletingAiClient):
        self.ai_client = ai_client

    def analyze(self, query: str) -> ResearchTask:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")

        from app.research_harness.errors import ProviderError, as_provider_error, is_provider_exception

        logger.info("task analyzer started; query_chars=%d", len(normalized_query))
        try:
            raw = self.ai_client.complete(self._messages(normalized_query))
            task = self._parse_task(normalized_query, raw)
        except ProviderError as exc:
            raise as_provider_error(exc, stage="analysis")
        except (RuntimeError, TimeoutError, ValueError, TypeError, KeyError, json.JSONDecodeError, ValidationError) as exc:
            if is_provider_exception(exc):
                raise as_provider_error(exc, stage="analysis") from exc
            logger.warning("task analyzer fallback; error_type=%s", type(exc).__name__)
            return self._fallback_analysis(normalized_query)
        except Exception as exc:
            if is_provider_exception(exc):
                raise as_provider_error(exc, stage="analysis") from exc
            logger.warning("task analyzer fallback; unexpected_error_type=%s", type(exc).__name__, exc_info=True)
            return self._fallback_analysis(normalized_query)

        logger.info("task analyzer completed; task_type=%s", task.task_type.value)
        return task

    def _messages(self, query: str) -> list[AiMessage]:
        return [
            AiMessage(role="system", content=TASK_ANALYZER_SYSTEM_PROMPT),
            AiMessage(role="user", content=query),
        ]

    def _parse_task(self, query: str, raw: str) -> ResearchTask:
        payload = _extract_json_object(raw)
        payload["task_id"] = _task_id()
        payload["query"] = query
        task = ResearchTask.model_validate(payload)
        return _normalize_task(task)


    def _fallback_analysis(self, query: str) -> ResearchTask:
        lowered = query.lower()
        has_paper = _contains_any(lowered, ("论文", "paper"))
        has_repository = _contains_any(lowered, ("github", "repo", "repository", "代码", "实现", "readme"))
        is_comparison = _contains_any(
            lowered,
            ("比较", "区别", "差异", "相比", " vs ", "versus", "difference", "compare", "comparison"),
        )
        is_multi_hop = _contains_any(lowered, ("哪些", "分别", "为什么以及如何", "综合分析", "multiple methods"))

        expected_source_types: list[ResearchSourceType] = []
        if has_paper:
            expected_source_types.append(ResearchSourceType.PAPER)
        if has_repository:
            expected_source_types.append(ResearchSourceType.REPOSITORY)
        if _contains_any(lowered, ("documentation", "docs", "文档")) and ResearchSourceType.DOCUMENTATION not in expected_source_types:
            expected_source_types.append(ResearchSourceType.DOCUMENTATION)

        if has_paper and has_repository:
            task_type = ResearchTaskType.PAPER_REPO_ANALYSIS
            requires_comparison = False
            requires_multiple_sources = _explicitly_requires_multiple_sources(lowered)
        elif is_comparison:
            task_type = ResearchTaskType.COMPARISON
            requires_comparison = True
            requires_multiple_sources = True
        elif is_multi_hop:
            task_type = ResearchTaskType.MULTI_HOP_RESEARCH
            requires_comparison = False
            requires_multiple_sources = True
        else:
            task_type = ResearchTaskType.FACT_LOOKUP
            requires_comparison = False
            requires_multiple_sources = False

        return ResearchTask(
            task_id=_task_id(),
            query=query,
            task_type=task_type,
            entities=[],
            research_questions=[query],
            expected_source_types=expected_source_types,
            requires_comparison=requires_comparison,
            requires_multiple_sources=requires_multiple_sources,
        )

def _explicitly_requires_multiple_sources(text: str) -> bool:
    return _contains_any(
        text,
        (
            "两篇论文",
            "多篇论文",
            "不同论文",
            "多个来源",
            "不同来源",
            "multiple papers",
            "multiple sources",
            "different papers",
            "different sources",
            "cross-document",
        ),
    )

def _extract_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    decoder = json.JSONDecoder()
    for start, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("task analyzer response does not contain a JSON object")


def _normalize_task(task: ResearchTask) -> ResearchTask:
    updates = {}
    if not task.research_questions:
        updates["research_questions"] = [task.query]
    if task.task_type == ResearchTaskType.COMPARISON:
        updates["requires_comparison"] = True
    elif task.task_type == ResearchTaskType.PAPER_REPO_ANALYSIS:
        source_types = list(task.expected_source_types)
        for source_type in (ResearchSourceType.PAPER, ResearchSourceType.REPOSITORY):
            if source_type not in source_types:
                source_types.append(source_type)
        updates["expected_source_types"] = source_types
        updates["requires_multiple_sources"] = True
    return task.model_copy(update=updates) if updates else task


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _task_id() -> str:
    return f"research-task-{uuid.uuid4().hex}"
