from __future__ import annotations

import time
import uuid
import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import SessionLocal
from app.research_harness.errors import ProviderError
from app.services.research_factory import ResearchRuntimeBundle, build_research_runtime
from app.services.research_runtime import ResearchRuntimeRun


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResearchExecution:
    run_id: str
    run: ResearchRuntimeRun
    diagnostics: dict
    duration_ms: float


class ResearchExecutionFailure(RuntimeError):
    def __init__(
        self,
        run_id: str,
        code: str,
        public_message: str,
        diagnostics: dict,
        *,
        status_code: int,
    ):
        super().__init__(public_message)
        self.run_id = run_id
        self.code = code
        self.public_message = public_message
        self.diagnostics = diagnostics
        self.status_code = status_code


class ResearchExecutionService:
    """Request-safe boundary around the synchronous research runtime."""

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        runtime_builder=build_research_runtime,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.runtime_builder = runtime_builder

    def execute(
        self,
        query: str,
        session_id: str | None = None,
        *,
        run_id: str | None = None,
    ) -> ResearchExecution:
        run_id = run_id or uuid.uuid4().hex
        started = time.perf_counter()
        db = self.session_factory()
        bundle: ResearchRuntimeBundle | None = None
        try:
            bundle = self.runtime_builder(db, self.settings, run_id=run_id)
            run = bundle.runtime.run(query, session_id=session_id or "")
            if run.final_result is None:
                diagnostics = _safe_diagnostics(bundle, started)
                revision = next(
                    (event for event in reversed(run.board.events) if event.type.value == "REVISION_REQUESTED"),
                    None,
                )
                diagnostics.update({
                    "result_status": "runtime_incomplete",
                    "failure_stage": revision.actor if revision else None,
                    "error_type": revision.metadata.get("errorType") if revision else "RuntimeIncomplete",
                })
                logger.error("research runtime incomplete; run_id=%s failure_stage=%s", run_id, diagnostics["failure_stage"])
                raise ResearchExecutionFailure(
                    run_id,
                    "runtime_incomplete",
                    "Research runtime ended without a final result.",
                    diagnostics,
                    status_code=500,
                )
            return ResearchExecution(
                run_id=run_id,
                run=run,
                diagnostics=_safe_diagnostics(bundle, started),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        except ResearchExecutionFailure:
            raise
        except ProviderError as exc:
            logger.warning(
                "research provider failure; run_id=%s stage=%s error_type=%s",
                run_id,
                exc.stage,
                exc.error_type,
            )
            diagnostics = _safe_diagnostics(bundle, started)
            diagnostics.update({
                "provider_failure": True,
                "result_status": "provider_failure",
                "failure_stage": exc.stage,
                "error_type": exc.error_type,
            })
            raise ResearchExecutionFailure(
                run_id,
                "provider_failure",
                "The configured AI provider could not complete the research run.",
                diagnostics,
                status_code=502,
            ) from exc
        except Exception as exc:
            logger.exception("research runtime failure; run_id=%s error_type=%s", run_id, type(exc).__name__)
            diagnostics = _safe_diagnostics(bundle, started)
            diagnostics.update({
                "result_status": "runtime_failure",
                "error_type": type(exc).__name__,
            })
            raise ResearchExecutionFailure(
                run_id,
                "runtime_failure",
                "The research runtime failed to complete.",
                diagnostics,
                status_code=500,
            ) from exc
        finally:
            db.close()


def _safe_diagnostics(bundle: ResearchRuntimeBundle | None, started: float) -> dict:
    duration = round((time.perf_counter() - started) * 1000, 3)
    if bundle is None:
        return {
            "result_status": "runtime_failure",
            "provider_failure": False,
            "draft_validation_failure": False,
            "evidence_insufficient": False,
            "fallback_used": False,
            "draft_repair_attempts": 0,
            "retrieval_repair_attempts": None,
            "total_tokens": None,
            "duration_ms": duration,
            "failure_stage": None,
            "error_type": None,
            "stage_traces": [],
        }
    fields = bundle.harness.diagnostics.as_record_fields()
    traces = fields.get("llm_traces") or []
    usage_available = any(
        int(trace.get("prompt_tokens") or 0)
        or int(trace.get("completion_tokens") or 0)
        or int(trace.get("total_tokens") or 0)
        for trace in traces
    )
    return {
        "result_status": fields.get("result_status", "pending"),
        "provider_failure": bool(fields.get("provider_failure")),
        "draft_validation_failure": bool(fields.get("draft_validation_failure")),
        "evidence_insufficient": bool(fields.get("evidence_insufficient")),
        "fallback_used": bool(fields.get("fallback_used")),
        "draft_repair_attempts": int(fields.get("draft_repair_attempts") or 0),
        "retrieval_repair_attempts": None,
        "total_tokens": fields.get("total_tokens") if usage_available else None,
        "duration_ms": duration,
        "failure_stage": fields.get("failure_stage"),
        "error_type": fields.get("error_type"),
        "stage_traces": [
            {
                "stage": trace.get("stage"),
                "agent": trace.get("agent"),
                "attempt": trace.get("attempt"),
                "latency_ms": trace.get("latency_ms"),
                "status": trace.get("status"),
                "error_type": trace.get("error_type"),
                "prompt_tokens": trace.get("prompt_tokens") if _trace_has_usage(trace) else None,
                "completion_tokens": trace.get("completion_tokens") if _trace_has_usage(trace) else None,
                "total_tokens": trace.get("total_tokens") if _trace_has_usage(trace) else None,
                "provider": trace.get("provider"),
                "model": trace.get("model"),
            }
            for trace in traces
        ],
    }


def _trace_has_usage(trace: dict) -> bool:
    return any(
        int(trace.get(field) or 0)
        for field in ("prompt_tokens", "completion_tokens", "total_tokens")
    )
