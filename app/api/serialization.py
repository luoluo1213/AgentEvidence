from __future__ import annotations

from collections import OrderedDict

from app.api.schemas import (
    ResearchDiagnosticsResponse,
    ResearchResponse,
    SourceResponse,
    VerificationResponse,
)
from app.services.research_execution import ResearchExecution


def research_response(execution: ResearchExecution, session_id: str | None) -> ResearchResponse:
    final = execution.run.final_result
    if final is None:  # guarded by ResearchExecutionService
        raise ValueError("final result is unavailable")
    sufficient = final.verification.sufficient
    status = "success" if sufficient else "evidence_insufficient"
    diagnostics = dict(execution.diagnostics)
    diagnostics["result_status"] = status
    diagnostics["evidence_insufficient"] = not sufficient
    return ResearchResponse(
        run_id=execution.run_id,
        status=status,
        session_id=session_id,
        answer=final.answer,
        sources=_sources(final.evidence_pool.items),
        verification=VerificationResponse.model_validate(final.verification.model_dump()),
        diagnostics=ResearchDiagnosticsResponse.model_validate(diagnostics),
    )


def _sources(items) -> list[SourceResponse]:
    grouped: OrderedDict[str, dict] = OrderedDict()
    for item in items:
        entry = grouped.setdefault(item.source_id, {
            "source_id": item.source_id,
            "source_title": item.source_title,
            "source_type": item.source_type.value,
            "evidence_ids": [],
            "sections": [],
        })
        if item.evidence_id not in entry["evidence_ids"]:
            entry["evidence_ids"].append(item.evidence_id)
        if item.section and item.section not in entry["sections"]:
            entry["sections"].append(item.section)
    return [SourceResponse.model_validate(value) for value in grouped.values()]
