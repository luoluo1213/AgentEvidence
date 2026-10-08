from __future__ import annotations

import json
from datetime import datetime, timezone

from app.agents.events import AgentEventType
from app.api.schemas import ResearchResponse
from app.services.research_execution import ResearchExecution


def encode_sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


class SseEnvelopeFactory:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.sequence = 0

    def make(self, event: str, data: dict) -> tuple[str, dict]:
        self.sequence += 1
        return event, {
            "event": event,
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence": self.sequence,
            "data": data,
        }


def observed_runtime_events(
    execution: ResearchExecution,
    response: ResearchResponse,
    factory: SseEnvelopeFactory,
):
    board = execution.run.board
    artifacts = {artifact.id: artifact for artifact in board.artifacts}
    for internal in board.events:
        if internal.type == AgentEventType.TASK_CLAIMED:
            yield factory.make("task.started", {
                "task_id": internal.task_id,
                "agent": internal.actor,
                "status": "started",
            })
        elif internal.type == AgentEventType.TASK_CLOSED:
            yield factory.make("task.completed", {
                "task_id": internal.task_id,
                "agent": internal.actor,
                "status": "completed",
            })
        elif internal.type == AgentEventType.ARTIFACT_PUBLISHED:
            artifact = artifacts.get(internal.artifact_id)
            if artifact is None:
                continue
            yield factory.make("artifact.created", {
                "artifact_id": artifact.id,
                "artifact_kind": artifact.kind,
                "task_id": artifact.task_id,
                "agent": artifact.owner,
            })
            value = artifact.payload.get("value")
            if artifact.kind == "evidence_pool" and value is not None:
                yield factory.make("retrieval.completed", {
                    "task_id": artifact.task_id,
                    "artifact_id": artifact.id,
                    "evidence_count": len(value.items),
                    "source_ids": value.source_ids(),
                })
            elif artifact.kind == "research_draft" and value is not None:
                yield factory.make("draft.completed", {
                    "task_id": artifact.task_id,
                    "artifact_id": artifact.id,
                    "claim_count": len(value.claims),
                })
            elif artifact.kind == "evidence_verification" and value is not None:
                yield factory.make("verification.completed", {
                    "task_id": artifact.task_id,
                    "artifact_id": artifact.id,
                    "sufficient": bool(value.sufficient),
                    "missing_points": list(value.missing_points),
                })
    yield factory.make("run.completed", response.model_dump(mode="json"))
