from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from app.agents.research_draft_generator import (
    ResearchDraft,
    ResearchDraftGenerator,
    fallback_draft,
)

from app.agents.research_types import (
    EvidencePool,
    EvidenceVerificationResult,
    ResearchTask,
)
from app.core.config import Settings
from app.research_harness.draft_validator import (
    draft_snapshot,
    is_evidence_refusal,
    validate_draft,
)
from app.research_harness.errors import (
    DraftValidationError,
    ProviderError,
    as_provider_error,
    is_provider_exception,
)
from app.research_harness.policy import ExecutionPolicy
from app.schemas.dtos import AiMessage


logger = logging.getLogger(__name__)

REPAIR_PROMPT = (
    "The previous draft failed deterministic validation.\n"
    "validation_reason={reason}\n"
    "validation_message={error}\n"
    "Original query:\n{query}\n"
    "Previous draft JSON or text:\n{previous}\n"
    "Return one complete JSON object only with a grounded answer and claims that cite exact evidence_id values. "
    "For comparison tasks, every entity-specific claim must cite evidence whose provenance matches that entity."
)


class CompletingAiClient(Protocol):
    def complete(self, messages: list[AiMessage]) -> str:
        ...


@dataclass
class LlmCallTrace:
    run_id: str
    case_id: str
    stage: str
    agent: str
    attempt: int
    latency_ms: float
    status: str
    error_type: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider: str
    model: str
    estimated_cost: float | None = None


@dataclass
class CaseDiagnostics:
    provider_failure: bool = False
    error_type: str | None = None
    error_message: str | None = None
    failure_stage: str | None = None
    draft_validation_failure: bool = False
    draft_validation_reason: str | None = None
    draft_validation_message: str | None = None
    draft_repair_attempts: int = 0
    draft_repair_success: bool = False
    evidence_insufficient: bool = False
    fallback_used: bool = False
    agent_stage_failure: bool = False
    result_status: str = "pending"
    original_draft: dict | None = None
    original_validation_reason: str | None = None
    original_validation_message: str | None = None
    repaired_draft: dict | None = None
    repair_validation_reason: str | None = None
    repair_validation_message: str | None = None
    traces: list[LlmCallTrace] = field(default_factory=list)

    def reset_draft_fields(self) -> None:
        self.draft_validation_failure = False
        self.draft_validation_reason = None
        self.draft_validation_message = None
        self.draft_repair_attempts = 0
        self.draft_repair_success = False
        self.evidence_insufficient = False
        self.fallback_used = False
        self.agent_stage_failure = False
        self.result_status = "pending"
        self.original_draft = None
        self.original_validation_reason = None
        self.original_validation_message = None
        self.repaired_draft = None
        self.repair_validation_reason = None
        self.repair_validation_message = None
        if not self.provider_failure:
            self.error_type = None
            self.error_message = None
            self.failure_stage = None

    def as_record_fields(self) -> dict[str, Any]:
        usage = usage_totals(self.traces)
        return {
            "provider_failure": self.provider_failure,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "failure_stage": self.failure_stage,
            "draft_validation_failure": self.draft_validation_failure,
            "draft_validation_reason": self.draft_validation_reason,
            "draft_validation_message": self.draft_validation_message,
            "draft_repair_attempts": self.draft_repair_attempts,
            "draft_repair_success": self.draft_repair_success,
            "evidence_insufficient": self.evidence_insufficient,
            "fallback_used": self.fallback_used,
            "agent_stage_failure": self.agent_stage_failure,
            "result_status": self.result_status,
            "original_draft": self.original_draft,
            "original_validation_reason": self.original_validation_reason,
            "original_validation_message": self.original_validation_message,
            "repaired_draft": self.repaired_draft,
            "repair_validation_reason": self.repair_validation_reason,
            "repair_validation_message": self.repair_validation_message,
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "estimated_cost": usage["estimated_cost"],
            "llm_traces": [asdict(trace) for trace in self.traces],
        }


class ResearchHarness:
    def __init__(
        self,
        policy: ExecutionPolicy | None = None,
        *,
        settings: Settings | None = None,
        run_id: str | None = None,
        sleep=time.sleep,
    ):
        self.policy = policy or (ExecutionPolicy.from_settings(settings) if settings is not None else ExecutionPolicy())
        self.settings = settings
        self.run_id = run_id or uuid.uuid4().hex
        self.sleep = sleep
        self.case_id = ""
        self._llm_calls = 0
        self.diagnostics = CaseDiagnostics()
        self.all_traces: list[LlmCallTrace] = []

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs) -> "ResearchHarness":
        return cls(ExecutionPolicy.from_settings(settings), settings=settings, **kwargs)

    def begin_case(self, case_id: str) -> None:
        self.case_id = case_id
        self._llm_calls = 0
        self.diagnostics = CaseDiagnostics()

    def note_evidence_insufficient(self, *, message: str | None = None) -> None:
        self.diagnostics.evidence_insufficient = True
        self.diagnostics.fallback_used = False
        self.diagnostics.agent_stage_failure = False
        self.diagnostics.result_status = "evidence_insufficient"
        if message and not self.diagnostics.error_message:
            self.diagnostics.error_message = message

    def record_provider_failure(self, exc: ProviderError, *, stage: str | None = None) -> None:
        self.diagnostics.provider_failure = True
        self.diagnostics.error_type = exc.error_type
        self.diagnostics.error_message = exc.error_message
        self.diagnostics.failure_stage = stage or exc.stage or "provider"
        self.diagnostics.fallback_used = False
        self.diagnostics.result_status = "provider_failure"

    def invoke(self, client: CompletingAiClient, messages: list[AiMessage], *, stage: str, agent: str) -> str:
        last_error: ProviderError | None = None
        for attempt in range(1, self.policy.max_provider_retries + 2):
            if self._llm_calls >= self.policy.max_total_llm_calls:
                raise ProviderError("budget_exceeded", "max_total_llm_calls exceeded", stage=stage)
            self._llm_calls += 1
            started = time.perf_counter()
            try:
                text = client.complete(messages)
                self._record_trace(stage, agent, attempt, started, "ok", None, client)
                return text
            except Exception as exc:
                error = as_provider_error(exc, stage=stage)
                last_error = error
                self._record_trace(stage, agent, attempt, started, "error", error.error_type, client)
                if error.error_type == "auth_quota" or not error.retryable:
                    self.record_provider_failure(error, stage=stage)
                    raise error
                if attempt > self.policy.max_provider_retries:
                    self.record_provider_failure(error, stage=stage)
                    raise error
                if self.policy.retry_backoff_seconds:
                    self.sleep(self.policy.retry_backoff_seconds * attempt)
        assert last_error is not None
        self.record_provider_failure(last_error, stage=stage)
        raise last_error

    def _record_trace(self, stage: str, agent: str, attempt: int, started: float, status: str, error_type: str | None, client) -> None:
        usage = _client_usage(client)
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
        cost = self._estimate_cost(prompt_tokens, completion_tokens)
        provider, model = _provider_model(client, self.settings)
        trace = LlmCallTrace(
            run_id=self.run_id,
            case_id=self.case_id,
            stage=stage,
            agent=agent,
            attempt=attempt,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            status=status,
            error_type=error_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            provider=provider,
            model=model,
            estimated_cost=cost,
        )
        self.diagnostics.traces.append(trace)
        self.all_traces.append(trace)

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float | None:
        if self.policy.prompt_token_price_usd <= 0 and self.policy.completion_token_price_usd <= 0:
            return None
        return round(
            prompt_tokens * self.policy.prompt_token_price_usd
            + completion_tokens * self.policy.completion_token_price_usd,
            8,
        )

    def wrap_client(self, client: CompletingAiClient, *, stage: str, agent: str) -> "StagedAiClient":
        return StagedAiClient(client, self, stage, agent)

    def wrap_draft_generator(self, generator: ResearchDraftGenerator) -> "HarnessDraftGenerator":
        return HarnessDraftGenerator(generator, self)


class StagedAiClient:
    def __init__(self, inner: CompletingAiClient, harness: ResearchHarness, stage: str, agent: str):
        self.inner = inner
        self.harness = harness
        self.stage = stage
        self.agent = agent

    def complete(self, messages: list[AiMessage]) -> str:
        return self.harness.invoke(self.inner, messages, stage=self.stage, agent=self.agent)

    @property
    def last_usage(self) -> dict[str, Any]:
        return _client_usage(self.inner)

    @property
    def settings(self):
        return getattr(self.inner, "settings", None)

    @contextmanager
    def using_stage(self, stage: str, agent: str | None = None):
        previous = (self.stage, self.agent)
        self.stage = stage
        if agent:
            self.agent = agent
        try:
            yield self
        finally:
            self.stage, self.agent = previous


class HarnessDraftGenerator:
    def __init__(self, inner: ResearchDraftGenerator, harness: ResearchHarness):
        self.inner = inner
        self.harness = harness

    def generate(self, task: ResearchTask, evidence_pool: EvidencePool) -> ResearchDraft:
        diag = self.harness.diagnostics
        diag.reset_draft_fields()
        if not evidence_pool.items:
            self.harness.note_evidence_insufficient(message="evidence pool is empty")
            draft = fallback_draft()
            diag.original_draft = draft_snapshot(draft)
            return draft
        try:
            draft = self._attempt(task, evidence_pool)
        except ProviderError as exc:
            self.harness.record_provider_failure(exc, stage=exc.stage or "draft")
            raise
        except DraftValidationError as exc:
            return self._repair_or_fallback(task, evidence_pool, exc, original_draft=exc.draft)

        validation = validate_draft(task, evidence_pool, draft, raw=getattr(self.inner, "last_raw", ""))
        if validation.valid:
            if is_evidence_refusal(draft):
                self.harness.note_evidence_insufficient(message="draft refused due to insufficient evidence")
            # Do not mark success here.
            # Final success is decided by EvidenceVerifier.
            return draft
        return self._repair_or_fallback(
            task,
            evidence_pool,
            DraftValidationError(validation.reason or "draft_invalid", validation.message, raw=getattr(self.inner, "last_raw", ""), draft=draft),
            original_draft=draft,
        )

    def _attempt(self, task: ResearchTask, evidence_pool: EvidencePool, extra: list[AiMessage] | None = None) -> ResearchDraft:
        from app.research_harness.draft_validator import classify_draft_exception

        try:
            return self.inner.try_generate(task, evidence_pool, extra)
        except ProviderError as exc:
            raise as_provider_error(exc, stage="draft")
        except DraftValidationError as exc:
            raise classify_draft_exception(exc, raw=getattr(self.inner, "last_raw", ""))
        except Exception as exc:
            if is_provider_exception(exc):
                raise as_provider_error(exc, stage="draft") from exc
            raise classify_draft_exception(exc, raw=getattr(self.inner, "last_raw", "")) from exc

    def _repair_or_fallback(
        self,
        task: ResearchTask,
        evidence_pool: EvidencePool,
        error: DraftValidationError,
        *,
        original_draft: ResearchDraft | None,
    ) -> ResearchDraft:
        diag = self.harness.diagnostics
        diag.draft_validation_failure = True
        diag.draft_validation_reason = error.error_type
        diag.draft_validation_message = str(error)
        diag.original_validation_reason = error.error_type
        diag.original_validation_message = str(error)
        diag.original_draft = draft_snapshot(original_draft) or draft_snapshot(error.draft)
        diag.error_type = error.error_type
        diag.error_message = str(error)
        diag.failure_stage = "draft_validation"

        if diag.draft_repair_attempts >= self.harness.policy.max_draft_repairs:
            return self._finalize_failed_repair(task, error)

        diag.draft_repair_attempts += 1
        previous = error.raw or (error.draft.model_dump_json() if error.draft is not None else "")
        if original_draft is not None and not previous:
            previous = original_draft.model_dump_json()
        repair_message = AiMessage(
            role="user",
            content=REPAIR_PROMPT.format(
                reason=error.error_type,
                error=error,
                query=task.query,
                previous=previous[:4000],
            ),
        )
        client = self.inner.ai_client
        stage_cm = client.using_stage("draft_repair", "DraftAgent") if hasattr(client, "using_stage") else nullcontext()
        try:
            with stage_cm:
                repaired = self._attempt(task, evidence_pool, [repair_message])
        except ProviderError as exc:
            self.harness.record_provider_failure(exc, stage="draft_repair")
            raise
        except DraftValidationError as exc:
            diag.repaired_draft = draft_snapshot(exc.draft)
            diag.repair_validation_reason = exc.error_type
            diag.repair_validation_message = str(exc)
            return self._finalize_failed_repair(task, exc)

        repair_validation = validate_draft(task, evidence_pool, repaired, raw=getattr(self.inner, "last_raw", ""))
        diag.repaired_draft = draft_snapshot(repaired)
        if repair_validation.valid:
            diag.draft_repair_success = True
            diag.repair_validation_reason = None
            diag.repair_validation_message = None
            diag.failure_stage = None
            diag.agent_stage_failure = False
            diag.fallback_used = False
            if is_evidence_refusal(repaired):
                self.harness.note_evidence_insufficient(message="repaired draft refused due to insufficient evidence")
            else:
                diag.result_status = "success"
                diag.evidence_insufficient = False
            return repaired

        diag.repair_validation_reason = repair_validation.reason
        diag.repair_validation_message = repair_validation.message
        return self._finalize_failed_repair(
            task,
            DraftValidationError(
                repair_validation.reason or "draft_invalid",
                repair_validation.message,
                raw=getattr(self.inner, "last_raw", ""),
                draft=repaired,
            ),
        )

    def _finalize_failed_repair(self, task: ResearchTask, error: DraftValidationError) -> ResearchDraft:
        diag = self.harness.diagnostics
        logger.warning(
            "research draft repair failed; task_id=%s reason=%s error=%s",
            task.task_id,
            error.error_type,
            error,
        )
        diag.draft_repair_success = False
        diag.fallback_used = True
        diag.agent_stage_failure = True
        diag.failure_stage = "draft_validation"
        diag.result_status = "draft_fallback"
        diag.error_type = error.error_type
        diag.error_message = str(error)
        if diag.repair_validation_reason is None:
            diag.repair_validation_reason = error.error_type
            diag.repair_validation_message = str(error)
        return fallback_draft()

class HarnessEvidenceVerifier:
    """
    Verification-aware wrapper.

    Draft validity only means that the draft structure and citations are valid.
    Final success is decided here according to evidence sufficiency.
    """

    def __init__(self, inner, harness: ResearchHarness):
        self.inner = inner
        self.harness = harness

    def verify(
        self,
        task: ResearchTask,
        draft: ResearchDraft,
        evidence_pool: EvidencePool,
    ) -> EvidenceVerificationResult:
        result = self.inner.verify(
            task,
            draft,
            evidence_pool,
        )

        if result.sufficient:
            self.harness.diagnostics.evidence_insufficient = False
            self.harness.diagnostics.result_status = "success"

            if (
                self.harness.diagnostics.error_type is None
                and not self.harness.diagnostics.provider_failure
            ):
                self.harness.diagnostics.error_message = None

        else:
            self.harness.note_evidence_insufficient(
                message=result.reason
            )

        return result

def usage_totals(traces: list[LlmCallTrace]) -> dict[str, Any]:
    prompt = sum(trace.prompt_tokens for trace in traces)
    completion = sum(trace.completion_tokens for trace in traces)
    total = sum(trace.total_tokens for trace in traces)
    costs = [trace.estimated_cost for trace in traces if trace.estimated_cost is not None]
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "estimated_cost": round(sum(costs), 8) if costs else None,
    }


def latency_by_stage(traces: list[LlmCallTrace]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[float]] = {}
    for trace in traces:
        grouped.setdefault(trace.stage, []).append(trace.latency_ms)
    summary = {}
    for stage, values in grouped.items():
        summary[stage] = {
            "count": len(values),
            "avg_latency_ms": round(sum(values) / len(values), 3),
            "total_latency_ms": round(sum(values), 3),
        }
    return summary


def _client_usage(client) -> dict[str, Any]:
    usage = getattr(client, "last_usage", None)
    if isinstance(usage, dict):
        return usage
    inner = getattr(client, "inner", None)
    nested = getattr(inner, "last_usage", None)
    return nested if isinstance(nested, dict) else {}


def _provider_model(client, settings: Settings | None) -> tuple[str, str]:
    client_settings = getattr(client, "settings", None) or settings
    if client_settings is None:
        return "", ""
    provider = str(getattr(client_settings, "ai_provider", "") or "")
    if provider.lower() == "openai":
        model = str(getattr(client_settings, "openai_model", "") or "")
    else:
        model = str(getattr(client_settings, "ollama_model", "") or "")
    return provider, model

