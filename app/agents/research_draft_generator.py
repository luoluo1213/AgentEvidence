from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agents.research_types import EvidenceItem, EvidencePool, ResearchTask, ResearchTaskType
from app.schemas.dtos import AiMessage


logger = logging.getLogger(__name__)

FALLBACK_ANSWER = "无法基于当前证据可靠生成回答"

RESEARCH_DRAFT_SYSTEM_PROMPT = """You generate a strictly evidence-grounded research draft.

Use ONLY the evidence supplied in the user message. Never add external facts, background knowledge, or invented citations.
Return one JSON object only, with this exact shape:
{
  "answer": "answer text",
  "claims": [
    {"claim_id": "claim-1", "text": "one factual claim", "evidence_ids": ["an exact supplied evidence_id"]}
  ]
}

Rules:
- Produce a complete synthesis, not a one-sentence summary and not a list of retrieved chunks.
- Address every research question explicitly. Explain mechanisms, processes, relationships, differences, and implementation details whenever the supplied evidence supports them.
- Organize the answer into a coherent explanation with enough detail to show how the supported conclusions follow from the evidence.
- The answer must be a genuine synthesis across relevant evidence. It must not merely concatenate or lightly rephrase the claim texts.
- Every factual claim must cite one or more exact evidence_id values from the supplied evidence.
- claim_id values must be unique.
- If evidence is insufficient, explicitly say so and omit unsupported claims. Do not guess.
- Preserve disagreements between sources. Present each position separately with its own evidence; never silently reconcile them.
- For comparison tasks, first explain each entity separately, then compare their mechanisms, processes, relationships, and differences. Claims about an entity must cite evidence whose provenance matches that entity; use evidence_ids_by_entity when provided. Direct comparison claims must cite evidence for every entity they compare.
- You may combine multiple evidence items in one claim when they jointly support it.
- Answer Chinese questions in natural, professional, complete Chinese. Evidence remains in its canonical source language.
- Always return a complete, parseable JSON object. Prefer a shorter finished answer over a truncated long answer.
"""

COMPACT_RETRY_PROMPT = """Your previous JSON was incomplete or truncated. Return one complete JSON object only, with no markdown and no extra text. Keep the answer to at most three short paragraphs and include 2-4 claims with exact evidence_id values."""


class CompletingAiClient(Protocol):
    def complete(self, messages: list[AiMessage]) -> str:
        ...


class ResearchClaim(BaseModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class ResearchDraft(BaseModel):
    answer: str
    claims: list[ResearchClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_claim_ids(self) -> "ResearchDraft":
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique")
        return self


class ResearchDraftGenerator:
    def __init__(self, ai_client: CompletingAiClient):
        self.ai_client = ai_client
        self.last_raw = ""

    def try_generate(
        self,
        task: ResearchTask,
        evidence_pool: EvidencePool,
        extra_messages: list[AiMessage] | None = None,
    ) -> ResearchDraft:
        from app.research_harness.draft_validator import classify_draft_exception
        from app.research_harness.errors import DraftValidationError, ProviderError, as_provider_error, is_provider_exception

        if not evidence_pool.items:
            raise DraftValidationError("empty_output", "no evidence items were supplied")
        messages = self._messages(task, evidence_pool)
        if extra_messages:
            messages = [*messages, *extra_messages]
        draft: ResearchDraft | None = None
        try:
            raw = self.ai_client.complete(messages)
            self.last_raw = raw or ""
            draft = ResearchDraft.model_validate(_extract_json_object(raw))
            self._validate_grounding(task, evidence_pool, draft)
            return draft
        except ProviderError:
            raise
        except Exception as exc:
            if is_provider_exception(exc):
                raise as_provider_error(exc, stage="draft") from exc
            raise classify_draft_exception(exc, raw=getattr(self, "last_raw", ""), draft=draft) from exc

    def generate(self, task: ResearchTask, evidence_pool: EvidencePool) -> ResearchDraft:
        from app.research_harness.errors import DraftValidationError, ProviderError

        if not evidence_pool.items:
            return fallback_draft()
        last_error: Exception | None = None
        retry_content: str | None = None
        for attempt in range(2):
            extra = [AiMessage(role="user", content=retry_content)] if retry_content else None
            try:
                draft = self.try_generate(task, evidence_pool, extra)
                if attempt:
                    logger.info("research draft recovered after retry; task_id=%s", task.task_id)
                return draft
            except ProviderError:
                raise
            except DraftValidationError as exc:
                last_error = exc
                raw = exc.raw or self.last_raw
                if attempt == 0:
                    retry_content = _retry_user_prompt(task, evidence_pool, raw, exc)
                    if retry_content:
                        logger.warning(
                            "research draft retrying; task_id=%s error_type=%s error=%s raw_chars=%d",
                            task.task_id,
                            type(exc).__name__,
                            exc,
                            len(raw or ""),
                        )
                        continue
                logger.warning(
                    "research draft fallback; task_id=%s error_type=%s error=%s raw_chars=%d raw_preview=%s",
                    task.task_id,
                    type(exc).__name__,
                    exc,
                    len(raw or ""),
                    (raw or "")[:300],
                )
                return fallback_draft()
            except Exception as exc:
                logger.warning(
                    "research draft fallback; task_id=%s unexpected_error_type=%s raw_chars=%d",
                    task.task_id,
                    type(exc).__name__,
                    len(self.last_raw or ""),
                    exc_info=True,
                )
                return fallback_draft()
        logger.warning(
            "research draft fallback; task_id=%s error_type=%s error=%s raw_chars=%d raw_preview=%s",
            task.task_id,
            type(last_error).__name__ if last_error else "UnknownError",
            last_error,
            len(self.last_raw or ""),
            (self.last_raw or "")[:300],
        )
        return fallback_draft()

    def _messages(self, task: ResearchTask, evidence_pool: EvidencePool) -> list[AiMessage]:
        evidence = [
            {
                "evidence_id": item.evidence_id,
                "source_id": item.source_id,
                "source_title": item.source_title,
                "section": item.section,
                "file_path": item.metadata.get("file_path"),
                "symbol": item.metadata.get("symbol"),
                "content": item.canonical_content or item.content,
            }
            for item in evidence_pool.items
        ]
        evidence_ids_by_entity = _evidence_ids_by_entity(task, evidence_pool)
        payload = {
            "task": {
                "query": task.query,
                "task_type": task.task_type.value,
                "entities": task.entities,
                "research_questions": task.research_questions or [task.query],
                "requires_comparison": task.requires_comparison,
                "requires_multiple_sources": task.requires_multiple_sources,
            },
            "evidence": evidence,
            "evidence_ids_by_entity": evidence_ids_by_entity,
            "evidence_ids_by_source": _evidence_ids_by_source(evidence_pool),
        }
        return [
            AiMessage(role="system", content=RESEARCH_DRAFT_SYSTEM_PROMPT),
            AiMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ]

    def _validate_grounding(
        self,
        task: ResearchTask,
        evidence_pool: EvidencePool,
        draft: ResearchDraft,
    ) -> None:
        evidence_by_id = {item.evidence_id: item for item in evidence_pool.items}
        if not draft.claims and not _expresses_insufficient_evidence(draft.answer):
            raise ValueError("uncited answer without an insufficiency statement")
        if _contains_chinese(task.query):
            if not _contains_chinese(draft.answer):
                raise ValueError("Chinese query requires a Chinese answer")
            if any(not _contains_chinese(claim.text) for claim in draft.claims):
                raise ValueError("Chinese query requires Chinese claim text")
        if draft.claims and _is_claim_concatenation(draft):
            raise ValueError("answer must synthesize rather than concatenate claim text")
        cited_ids: set[str] = set()
        for claim in draft.claims:
            if len(claim.evidence_ids) != len(set(claim.evidence_ids)):
                raise ValueError("duplicate evidence_id in claim")
            unknown = set(claim.evidence_ids) - evidence_by_id.keys()
            if unknown:
                raise ValueError(f"unknown evidence ids: {sorted(unknown)}")
            cited_ids.update(claim.evidence_ids)
            if _is_comparison(task):
                self._validate_comparison_claim(task, claim, evidence_by_id)

        if _is_comparison(task):
            cited_sources = {evidence_by_id[evidence_id].source_id for evidence_id in cited_ids}
            if len(cited_sources) < 2:
                raise ValueError("comparison draft must cite multiple sources")
            self._validate_comparison_coverage(task, draft, evidence_by_id)

    @staticmethod
    def _validate_comparison_claim(
        task: ResearchTask,
        claim: ResearchClaim,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> None:
        claim_text = _normalize_match_text(claim.text)
        cited_ids = set(claim.evidence_ids)
        for entity in task.entities:
            normalized_entity = _normalize_match_text(entity)
            if not normalized_entity or normalized_entity not in claim_text:
                continue
            matching_evidence = {
                evidence_id
                for evidence_id, item in evidence_by_id.items()
                if _evidence_matches_entity(item, normalized_entity)
            }
            if matching_evidence and not (cited_ids & matching_evidence):
                raise ValueError(f"claim about entity {entity!r} lacks matching evidence")

    @staticmethod
    def _validate_comparison_coverage(
        task: ResearchTask,
        draft: ResearchDraft,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> None:
        for entity in task.entities:
            normalized_entity = _normalize_match_text(entity)
            matching_evidence = {
                evidence_id
                for evidence_id, item in evidence_by_id.items()
                if normalized_entity and _evidence_matches_entity(item, normalized_entity)
            }
            if not matching_evidence:
                continue
            entity_claims = [
                claim for claim in draft.claims
                if normalized_entity in _normalize_match_text(claim.text)
            ]
            if not entity_claims:
                raise ValueError(f"comparison draft does not separately cover entity {entity!r}")
            if not any(set(claim.evidence_ids) & matching_evidence for claim in entity_claims):
                raise ValueError(f"comparison entity {entity!r} lacks matching cited evidence")


def fallback_draft() -> ResearchDraft:
    return ResearchDraft(answer=FALLBACK_ANSWER, claims=[])


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
    raise ValueError("research draft response does not contain a JSON object")


def _should_retry_truncated_json(raw: str, exc: Exception) -> bool:
    text = str(raw or "").strip()
    if "{" not in text:
        return False
    message = str(exc).lower()
    return isinstance(exc, json.JSONDecodeError) or "does not contain a json object" in message


def _should_retry_grounding(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(term in message for term in (
        "lacks matching evidence",
        "comparison draft",
        "unknown evidence ids",
        "does not separately cover entity",
    ))


def _retry_user_prompt(task: ResearchTask, evidence_pool: EvidencePool, raw: str, exc: Exception) -> str | None:
    if _should_retry_truncated_json(raw, exc):
        return COMPACT_RETRY_PROMPT
    if not _should_retry_grounding(exc):
        return None
    return (
        "The previous JSON failed evidence grounding: "
        f"{exc}\n"
        "Return one complete JSON object only. Keep the same synthesis if it is supported. "
        "Every claim that names an entity MUST cite at least one evidence_id from that entity's list. "
        "Direct comparison claims MUST cite at least one evidence_id for every compared entity.\n"
        f"evidence_ids_by_entity={json.dumps(_evidence_ids_by_entity(task, evidence_pool), ensure_ascii=False)}\n"
        f"evidence_ids_by_source={json.dumps(_evidence_ids_by_source(evidence_pool), ensure_ascii=False)}"
    )


def _evidence_ids_by_source(evidence_pool: EvidencePool) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in evidence_pool.items:
        grouped.setdefault(item.source_id, []).append(item.evidence_id)
    return grouped


def _evidence_ids_by_entity(task: ResearchTask, evidence_pool: EvidencePool) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for entity in task.entities:
        ids = [
            item.evidence_id
            for item in evidence_pool.items
            if _evidence_matches_entity(item, _normalize_match_text(entity))
        ]
        if ids:
            grouped[entity] = ids
    return grouped


def _is_comparison(task: ResearchTask) -> bool:
    return task.requires_comparison or task.task_type == ResearchTaskType.CROSS_DOCUMENT_COMPARISON


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _expresses_insufficient_evidence(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in ("不足", "无法", "不充分", "insufficient", "cannot reliably"))


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
    return normalized_entity in _normalize_match_text(provenance)


def _is_claim_concatenation(draft: ResearchDraft) -> bool:
    answer = re.sub(r"\s+", "", draft.answer).strip("。.!！?？;；")
    joined = "".join(re.sub(r"\s+", "", claim.text).strip("。.!！?？;；") for claim in draft.claims)
    return bool(answer) and answer == joined
