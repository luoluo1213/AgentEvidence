from __future__ import annotations

import json
import unittest
import uuid

from fastapi.testclient import TestClient

from app.agents.events import AgentArtifact, AgentEvent, AgentEventType, CollaborationBlackboard
from app.agents.research_draft_generator import ResearchClaim, ResearchDraft
from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    EvidenceVerificationResult,
    ResearchSourceType,
    ResearchTask,
    ResearchTaskType,
)
from app.api.dependencies import get_research_execution_service
from app.main import create_app
from app.services.research_execution import (
    ResearchExecution,
    ResearchExecutionFailure,
)
from app.services.research_pipeline import build_final_research_result
from app.services.research_runtime import ResearchRuntimeRun


def _diagnostics(status: str = "success") -> dict:
    return {
        "result_status": status,
        "provider_failure": status == "provider_failure",
        "draft_validation_failure": False,
        "evidence_insufficient": status == "evidence_insufficient",
        "fallback_used": False,
        "draft_repair_attempts": 0,
        "retrieval_repair_attempts": None,
        "total_tokens": 12,
        "duration_ms": 4.2,
        "failure_stage": None,
        "error_type": None,
        "stage_traces": [],
    }


def _execution(run_id: str | None = None, *, sufficient: bool = True, with_events: bool = True):
    task = ResearchTask(
        task_id="research-task",
        query="How does the method work?",
        task_type=ResearchTaskType.FACT_LOOKUP,
        research_questions=["How does the method work?"],
    )
    evidence = EvidenceItem(
        evidence_id="ev-1",
        source_id="research:test_pdf",
        source_title="Test Paper",
        source_type=ResearchSourceType.PAPER,
        section="Method",
        content="The method uses observations.",
        canonical_content="The method uses observations.",
        query_used=task.query,
    )
    pool = EvidencePool(items=[evidence])
    draft = ResearchDraft(
        answer="该方法使用观察结果。",
        claims=[ResearchClaim(claim_id="claim-1", text="The method uses observations.", evidence_ids=["ev-1"])],
    )
    verification = EvidenceVerificationResult(
        sufficient=sufficient,
        supported_points=["claim-1"] if sufficient else [],
        missing_points=[] if sufficient else ["mechanism details"],
        reason="supported" if sufficient else "insufficient evidence",
    )
    final = build_final_research_result(task.query, task, pool, draft, verification)
    evidence_artifact = AgentArtifact(
        id="artifact:evidence",
        owner="ResearchAgent",
        kind="evidence_pool",
        payload={"value": pool},
        task_id="task:research:evidence",
    )
    draft_artifact = AgentArtifact(
        id="artifact:draft",
        owner="DraftAgent",
        kind="research_draft",
        payload={"value": draft},
        task_id="task:research:draft",
    )
    verification_artifact = AgentArtifact(
        id="artifact:verification",
        owner="EvidenceVerifier",
        kind="evidence_verification",
        payload={"value": verification},
        task_id="task:research:verification",
    )
    events = ()
    artifacts = ()
    if with_events:
        artifacts = (evidence_artifact, draft_artifact, verification_artifact)
        events = (
            AgentEvent(AgentEventType.TASK_CLAIMED, "ResearchAgent", task_id="task:research:evidence"),
            AgentEvent(
                AgentEventType.ARTIFACT_PUBLISHED,
                "ResearchAgent",
                task_id="task:research:evidence",
                artifact_id=evidence_artifact.id,
            ),
            AgentEvent(AgentEventType.TASK_CLOSED, "ResearchAgent", task_id="task:research:evidence"),
            AgentEvent(AgentEventType.TASK_CLAIMED, "DraftAgent", task_id="task:research:draft"),
            AgentEvent(
                AgentEventType.ARTIFACT_PUBLISHED,
                "DraftAgent",
                task_id="task:research:draft",
                artifact_id=draft_artifact.id,
            ),
            AgentEvent(AgentEventType.TASK_CLOSED, "DraftAgent", task_id="task:research:draft"),
            AgentEvent(AgentEventType.TASK_CLAIMED, "EvidenceVerifier", task_id="task:research:verification"),
            AgentEvent(
                AgentEventType.ARTIFACT_PUBLISHED,
                "EvidenceVerifier",
                task_id="task:research:verification",
                artifact_id=verification_artifact.id,
            ),
            AgentEvent(AgentEventType.TASK_CLOSED, "EvidenceVerifier", task_id="task:research:verification"),
        )
    board = CollaborationBlackboard(turn_id="turn", events=events, artifacts=artifacts)
    return ResearchExecution(
        run_id=run_id or uuid.uuid4().hex,
        run=ResearchRuntimeRun(board=board, final_result=final),
        diagnostics=_diagnostics("success" if sufficient else "evidence_insufficient"),
        duration_ms=4.2,
    )


class FakeResearchService:
    def __init__(self, *, sufficient=True, fail=False, with_events=True):
        self.sufficient = sufficient
        self.fail = fail
        self.with_events = with_events
        self.calls = []

    def execute(self, query, session_id=None, *, run_id=None):
        self.calls.append((query, session_id, run_id))
        if self.fail:
            raise ResearchExecutionFailure(
                run_id or "failed-run",
                "provider_failure",
                "The configured AI provider could not complete the research run.",
                _diagnostics("provider_failure"),
                status_code=502,
            )
        return _execution(run_id, sufficient=self.sufficient, with_events=self.with_events)


def _sse_events(text: str):
    parsed = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[7:] for line in lines if line.startswith("event: "))
        payload = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
        parsed.append((event, payload))
    return parsed


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(init_database=False)

    def client_with(self, service):
        self.app.dependency_overrides[get_research_execution_service] = lambda: service
        return TestClient(self.app)

    def test_app_import_startup_and_health(self):
        with TestClient(self.app) as client:
            response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "status": "ok", "service": "AgentEvidence", "version": "0.1.0"
        })

    def test_empty_query_is_rejected(self):
        response = self.client_with(FakeResearchService()).post(
            "/api/v1/research", json={"query": "   "}
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_verified_research_response_is_serializable(self):
        service = FakeResearchService()
        response = self.client_with(service).post(
            "/api/v1/research",
            json={"query": "How?", "session_id": "session-1"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertTrue(body["verification"]["sufficient"])
        self.assertEqual(body["sources"][0]["source_id"], "research:test_pdf")
        json.dumps(body)

    def test_insufficient_evidence_is_distinct(self):
        response = self.client_with(FakeResearchService(sufficient=False)).post(
            "/api/v1/research", json={"query": "How?"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "evidence_insufficient")
        self.assertFalse(response.json()["verification"]["sufficient"])

    def test_provider_failure_has_error_status(self):
        response = self.client_with(FakeResearchService(fail=True)).post(
            "/api/v1/research", json={"query": "How?"}
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["error"]["code"], "provider_failure")

    def test_independent_requests_receive_distinct_runs(self):
        service = FakeResearchService()
        client = self.client_with(service)
        first = client.post("/api/v1/research", json={"query": "one"}).json()
        second = client.post("/api/v1/research", json={"query": "two"}).json()
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual([call[0] for call in service.calls], ["one", "two"])

    def test_sse_order_and_terminal_success(self):
        response = self.client_with(FakeResearchService()).post(
            "/api/v1/research/stream", json={"query": "How?"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = _sse_events(response.text)
        names = [name for name, _ in events]
        self.assertEqual(names, [
            "run.started", "task.started", "artifact.created",
            "retrieval.completed", "task.completed",
            "task.started", "artifact.created", "draft.completed", "task.completed",
            "task.started", "artifact.created", "verification.completed", "task.completed",
            "run.completed",
        ])
        sequences = [payload["sequence"] for _, payload in events]
        self.assertEqual(sequences, list(range(1, len(events) + 1)))
        self.assertEqual(events[-1][1]["data"]["status"], "success")

    def test_sse_failure_is_terminal_and_has_no_secret(self):
        response = self.client_with(FakeResearchService(fail=True)).post(
            "/api/v1/research/stream", json={"query": "How?"}
        )
        events = _sse_events(response.text)
        self.assertEqual([event for event, _ in events], ["run.started", "run.failed"])
        self.assertNotIn("api_key", response.text.lower())
        self.assertNotIn("bearer", response.text.lower())

    def test_sse_insufficient_result_still_has_completed_terminal(self):
        response = self.client_with(FakeResearchService(sufficient=False)).post(
            "/api/v1/research/stream", json={"query": "How?"}
        )
        events = _sse_events(response.text)
        self.assertEqual(events[-1][0], "run.completed")
        self.assertEqual(events[-1][1]["data"]["status"], "evidence_insufficient")

    def test_sse_does_not_fabricate_task_events(self):
        response = self.client_with(FakeResearchService(with_events=False)).post(
            "/api/v1/research/stream", json={"query": "How?"}
        )
        names = [event for event, _ in _sse_events(response.text)]
        self.assertEqual(names, ["run.started", "run.completed"])


if __name__ == "__main__":
    unittest.main()
