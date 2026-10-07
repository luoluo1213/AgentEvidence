from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from pydantic import ValidationError

from app.agents.research_draft_generator import ResearchDraft
from app.agents.research_types import EvidencePool, EvidenceVerificationResult, ResearchTask
from app.schemas.dtos import AiMessage


logger = logging.getLogger(__name__)

EVIDENCE_VERIFIER_SYSTEM_PROMPT = """You are an evidence verifier for a research system.

Judge only from the supplied task, actual draft, and evidence. Do not use outside knowledge.
Verify every draft claim against its cited evidence, overall research-question coverage, overreach, and whether source conflicts are preserved rather than silently resolved.
Suggested queries are focused retrieval queries for a later repair stage. They must not be answers.

Return structured JSON only:
{
  "sufficient": false,
  "supported_points": ["supported claim or point"],
  "missing_points": ["specific unsupported or uncovered point"],
  "weak_evidence_ids": ["exact supplied evidence_id"],
  "suggested_queries": ["short focused retrieval query"],
  "reason": "concise verification rationale"
}

Rules:
- Inspect the ACTUAL draft answer and every claim; do not verify only the task or evidence pool.
- For each claim, check that cited evidence exists and genuinely entails the claim without obvious over-inference.
- Check whether disagreements in the supplied evidence are explicitly retained in the draft.
- Check every research question for coverage.
- Set sufficient=false when any material claim is unsupported, partially supported, over-inferred, or any research question is materially uncovered.
- When insufficient, name exactly what is missing and propose only a few targeted retrieval queries.
"""


class CompletingAiClient(Protocol):
    def complete(self, messages: list[AiMessage]) -> str:
        ...


class EvidenceVerifier:
    def __init__(self, ai_client: CompletingAiClient):
        self.ai_client = ai_client

    def verify(
        self,
        task: ResearchTask,
        draft: ResearchDraft,
        evidence_pool: EvidencePool,
    ) -> EvidenceVerificationResult:
        from app.research_harness.errors import ProviderError, as_provider_error, is_provider_exception

        preflight = self._preflight(task, draft, evidence_pool)
        if preflight is not None:
            return preflight
        try:
            raw = self.ai_client.complete(self._messages(task, draft, evidence_pool))
            result = EvidenceVerificationResult.model_validate(_extract_json_object(raw))
            return self._validate_result(task, draft, evidence_pool, result)
        except ProviderError as exc:
            raise as_provider_error(exc, stage="verification")
        except (RuntimeError, TimeoutError, ValueError, TypeError, KeyError, json.JSONDecodeError, ValidationError) as exc:
            if is_provider_exception(exc):
                raise as_provider_error(exc, stage="verification") from exc
            logger.warning("evidence verifier fallback; task_id=%s error_type=%s", task.task_id, type(exc).__name__)
        except Exception as exc:
            if is_provider_exception(exc):
                raise as_provider_error(exc, stage="verification") from exc
            logger.warning(
                "evidence verifier fallback; task_id=%s unexpected_error_type=%s",
                task.task_id,
                type(exc).__name__,
                exc_info=True,
            )
        return _fallback_result(task, draft, "Evidence verifier provider or response validation failed.")

    def _messages(
        self,
        task: ResearchTask,
        draft: ResearchDraft,
        evidence_pool: EvidencePool,
    ) -> list[AiMessage]:
        payload = {
            "task": task.model_dump(mode="json"),
            "draft": draft.model_dump(mode="json"),
            "evidence": [
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
            ],
        }
        return [
            AiMessage(role="system", content=EVIDENCE_VERIFIER_SYSTEM_PROMPT),
            AiMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ]

    @staticmethod
    def _preflight(
        task: ResearchTask,
        draft: ResearchDraft,
        evidence_pool: EvidencePool,
    ) -> EvidenceVerificationResult | None:
        evidence_ids = {item.evidence_id for item in evidence_pool.items}
        missing_references: list[tuple[str, str]] = []
        for claim in draft.claims:
            for evidence_id in claim.evidence_ids:
                if evidence_id not in evidence_ids:
                    missing_references.append((claim.claim_id, evidence_id))
        if missing_references:
            missing_points = [
                f"Claim {claim_id} cites unavailable evidence_id {evidence_id}."
                for claim_id, evidence_id in missing_references
            ]
            claim_queries = [
                claim.text for claim in draft.claims
                if any(claim.claim_id == claim_id for claim_id, _ in missing_references)
            ]
            return EvidenceVerificationResult(
                sufficient=False,
                supported_points=[],
                missing_points=_unique(missing_points),
                weak_evidence_ids=_unique([evidence_id for _, evidence_id in missing_references]),
                suggested_queries=_focused_queries(task, claim_queries),
                reason="The draft contains evidence references that are absent from the supplied EvidencePool.",
            )
        if not draft.claims:
            return EvidenceVerificationResult(
                sufficient=False,
                supported_points=[],
                missing_points=["The draft contains no verifiable claims."],
                weak_evidence_ids=[],
                suggested_queries=_focused_queries(task),
                reason="No claim-to-evidence support can be verified.",
            )
        return None

    @staticmethod
    def _validate_result(
        task: ResearchTask,
        draft: ResearchDraft,
        evidence_pool: EvidencePool,
        result: EvidenceVerificationResult,
    ) -> EvidenceVerificationResult:
        cited_ids = {evidence_id for claim in draft.claims for evidence_id in claim.evidence_ids}
        pool_ids = {item.evidence_id for item in evidence_pool.items}
        invalid_weak_ids = set(result.weak_evidence_ids) - (cited_ids & pool_ids)
        if invalid_weak_ids:
            raise ValueError(f"verifier returned invalid weak evidence IDs: {sorted(invalid_weak_ids)}")
        if result.sufficient:
            if result.missing_points or result.weak_evidence_ids:
                raise ValueError("sufficient result cannot contain missing points or weak evidence")
            if not result.supported_points:
                raise ValueError("sufficient result must identify supported points")
            return result.model_copy(update={"suggested_queries": []})
        if not result.missing_points:
            raise ValueError("insufficient result must identify missing points")
        answer_texts = {draft.answer.strip(), *(claim.text.strip() for claim in draft.claims)}
        queries = _unique([
            query.strip()
            for query in result.suggested_queries
            if query.strip() and query.strip() not in answer_texts
        ])[:4]
        if not queries:
            queries = _focused_queries(task, [claim.text for claim in draft.claims])
        return result.model_copy(update={
            "supported_points": _unique(result.supported_points),
            "missing_points": _unique(result.missing_points),
            "weak_evidence_ids": _unique(result.weak_evidence_ids),
            "suggested_queries": queries,
        })


def _fallback_result(task: ResearchTask, draft: ResearchDraft, reason: str) -> EvidenceVerificationResult:
    return EvidenceVerificationResult(
        sufficient=False,
        supported_points=[],
        missing_points=["Claim support and research-question coverage could not be verified."],
        weak_evidence_ids=[],
        suggested_queries=_focused_queries(task, [claim.text for claim in draft.claims]),
        reason=reason,
    )


def _focused_queries(task: ResearchTask, points: list[str] | None = None) -> list[str]:
    claim_queries = [f"evidence supporting claim: {point.strip()}" for point in (points or []) if point.strip()]
    candidates = [*(task.research_questions or [task.query]), *claim_queries]
    return _unique([candidate.strip() for candidate in candidates if candidate and candidate.strip()])[:4]


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


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
    raise ValueError("evidence verifier response does not contain a JSON object")
