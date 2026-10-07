from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from pydantic import ValidationError

from app.agents.research_draft_generator import FALLBACK_ANSWER, ResearchDraft
from app.agents.research_types import EvidencePool, ResearchTask
from app.research_harness.errors import DraftValidationError


_PLACEHOLDER_COMPARISON = re.compile(
    r".+的\s*(?:\.{2,}|…|⋯)\s*。\s*.+的\s*(?:\.{2,}|…|⋯)\s*。\s*比较",
    re.DOTALL,
)
_PLACEHOLDER_TOKEN = re.compile(r"(?i)\b(?:tbd|xxx)\b")
_MIN_ANSWER_CHARS = 12

REASON_EMPTY_OUTPUT = "empty_output"
REASON_PLACEHOLDER_OUTPUT = "placeholder_output"
REASON_TOO_SHORT = "too_short"
REASON_GENERIC_FALLBACK = "generic_fallback"
REASON_SCHEMA_ERROR = "schema_error"
REASON_INVALID_EVIDENCE_REFERENCE = "invalid_evidence_reference"
REASON_MISSING_REQUIRED_FIELD = "missing_required_field"


@dataclass(frozen=True)
class DraftValidationResult:
    valid: bool
    reason: str | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.valid

    @property
    def error_type(self) -> str | None:
        return self.reason

    def raise_if_invalid(self, *, raw: str = "", draft: ResearchDraft | None = None) -> None:
        if not self.valid:
            raise DraftValidationError(
                self.reason or "draft_invalid",
                self.message,
                raw=raw,
                draft=draft,
            )

    def as_dict(self) -> dict:
        return asdict(self)


def validate_draft(
    task: ResearchTask,
    evidence_pool: EvidencePool,
    draft: ResearchDraft | None,
    *,
    raw: str = "",
) -> DraftValidationResult:
    if draft is None:
        return DraftValidationResult(False, REASON_EMPTY_OUTPUT, "draft is None")
    answer = str(draft.answer or "")
    stripped = answer.strip()
    if not stripped:
        return DraftValidationResult(False, REASON_EMPTY_OUTPUT, "draft answer is empty")
    if stripped in {"...", "…", "⋯"}:
        return DraftValidationResult(False, REASON_PLACEHOLDER_OUTPUT, "draft answer is ellipsis")
    if _PLACEHOLDER_TOKEN.search(stripped):
        return DraftValidationResult(False, REASON_PLACEHOLDER_OUTPUT, "draft contains TBD/xxx placeholder")
    if _PLACEHOLDER_COMPARISON.search(stripped):
        return DraftValidationResult(False, REASON_PLACEHOLDER_OUTPUT, "draft is a comparison placeholder skeleton")

    if is_evidence_refusal(draft):
        # Natural evidence refusal is not a draft-system failure.
        return DraftValidationResult(True)

    if stripped == FALLBACK_ANSWER and draft.claims:
        return DraftValidationResult(
            False,
            REASON_GENERIC_FALLBACK,
            "generic fallback sentence coexists with claims",
        )

    if len(stripped) < _MIN_ANSWER_CHARS:
        return DraftValidationResult(False, REASON_TOO_SHORT, f"draft answer shorter than {_MIN_ANSWER_CHARS} characters")

    evidence_ids = {item.evidence_id for item in evidence_pool.items}
    for claim in draft.claims:
        if not claim.claim_id or not str(claim.claim_id).strip():
            return DraftValidationResult(False, REASON_MISSING_REQUIRED_FIELD, "claim_id is required")
        if not claim.text or not str(claim.text).strip():
            return DraftValidationResult(False, REASON_MISSING_REQUIRED_FIELD, "claim text is required")
        if not claim.evidence_ids:
            return DraftValidationResult(False, REASON_MISSING_REQUIRED_FIELD, "claim evidence_ids is required")
        unknown = [evidence_id for evidence_id in claim.evidence_ids if evidence_id not in evidence_ids]
        if unknown:
            return DraftValidationResult(
                False,
                REASON_INVALID_EVIDENCE_REFERENCE,
                f"unknown evidence ids: {sorted(unknown)}",
            )
    return DraftValidationResult(True)


def classify_draft_exception(exc: BaseException, *, raw: str = "", draft: ResearchDraft | None = None) -> DraftValidationError:
    if isinstance(exc, DraftValidationError):
        return DraftValidationError(
            normalize_reason(exc.error_type, str(exc)),
            str(exc),
            raw=exc.raw or raw,
            draft=exc.draft if exc.draft is not None else draft,
        )
    message = str(exc)
    reason = normalize_reason(type(exc).__name__, message)
    return DraftValidationError(reason, message, raw=raw, draft=draft)


def normalize_reason(error_type: str | None, message: str) -> str:
    text = f"{error_type or ''} {message or ''}".lower()
    if any(term in text for term in (
        "unknown evidence",
        "lacks matching evidence",
        "invalid evidence",
        "duplicate evidence_id",
        "comparison draft must cite",
        "does not separately cover entity",
        "comparison entity",
    )):
        return REASON_INVALID_EVIDENCE_REFERENCE
    if any(term in text for term in (
        "json",
        "validation error",
        "does not contain a json",
        "model_validate",
        "claim_id values must be unique",
    )):
        return REASON_SCHEMA_ERROR
    if any(term in text for term in ("required", "missing", "field required")):
        return REASON_MISSING_REQUIRED_FIELD
    if "placeholder" in text or "tbd" in text or "ellipsis" in text:
        return REASON_PLACEHOLDER_OUTPUT
    if "too short" in text or "shorter than" in text:
        return REASON_TOO_SHORT
    if "empty" in text:
        return REASON_EMPTY_OUTPUT
    if "fallback" in text:
        return REASON_GENERIC_FALLBACK
    if isinstance(error_type, str) and error_type in {
        REASON_EMPTY_OUTPUT,
        REASON_PLACEHOLDER_OUTPUT,
        REASON_TOO_SHORT,
        REASON_GENERIC_FALLBACK,
        REASON_SCHEMA_ERROR,
        REASON_INVALID_EVIDENCE_REFERENCE,
        REASON_MISSING_REQUIRED_FIELD,
    }:
        return error_type
    if "valueerror" in (error_type or "").lower():
        # Grounding ValueErrors that are not evidence-id specific still block the draft.
        if any(term in text for term in ("chinese", "concatenate", "uncited", "insufficiency")):
            return REASON_SCHEMA_ERROR
        return REASON_INVALID_EVIDENCE_REFERENCE
    return REASON_SCHEMA_ERROR


def is_evidence_refusal(draft: ResearchDraft | None) -> bool:
    if draft is None:
        return False
    answer = str(draft.answer or "").strip()
    if not answer:
        return False
    if draft.claims:
        return False
    return _expresses_insufficient_evidence(answer)


def _expresses_insufficient_evidence(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in (
        "不足",
        "无法",
        "不充分",
        "无法回答",
        "无法基于",
        "insufficient",
        "cannot reliably",
        "cannot answer",
        "not enough evidence",
    ))


def parse_draft_json(raw: str) -> dict:
    text = str(raw or "").strip()
    if not text:
        raise DraftValidationError(REASON_EMPTY_OUTPUT, "provider returned empty draft text", raw=raw)
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
    raise DraftValidationError(REASON_SCHEMA_ERROR, "research draft response does not contain a JSON object", raw=raw)


def draft_snapshot(draft: ResearchDraft | None) -> dict | None:
    if draft is None:
        return None
    return draft.model_dump(mode="json")
