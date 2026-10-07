from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings
from app.services.ai import AiClient
from app.services.research_runtime import RESEARCH_TASKS, ResearchEventDrivenRuntime
from scripts.demo_research_agent import build_local_knowledge_service
from scripts.demo_research_draft import DemoEvidenceVerifierClient, DemoGroundedDraftClient
from scripts.demo_task_analyzer import DemoMockAiClient


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run the event-driven multi-agent research runtime.")
    parser.add_argument("query")
    parser.add_argument("--live", action="store_true", help="Use configured live LLM providers.")
    args = parser.parse_args(argv)

    settings = Settings(knowledge_vector_enabled=False)
    use_demo = not args.live
    analyzer_client = DemoMockAiClient() if use_demo else AiClient(settings)
    draft_client = DemoGroundedDraftClient() if use_demo else AiClient(settings)
    verifier_client = DemoEvidenceVerifierClient() if use_demo else AiClient(settings)
    knowledge, db = build_local_knowledge_service(settings)
    try:
        runtime = ResearchEventDrivenRuntime(
            TaskAnalyzerAgent(analyzer_client),
            ResearchAgent(
                knowledge,
                top_k=settings.research_retrieval_top_k,
                max_evidence_items=settings.research_max_evidence_items,
            ),
            ResearchDraftGenerator(draft_client),
            EvidenceVerifier(verifier_client),
            settings,
        )
        run = runtime.run(args.query)
    finally:
        db.close()

    print("=== Agent Tasks ===")
    for task_id, agent_name, *_ in RESEARCH_TASKS:
        task = run.board.tasks[task_id]
        owner = ",".join(task.claimed_by) or "unclaimed"
        display_status = "COMPLETE" if task.status.value == "CLOSED" else task.status.value
        print(f"{agent_name} {display_status} claimed_by={owner}")

    print("\n=== Runtime Events ===")
    for index, event in enumerate(run.board.events, start=1):
        details = f" task={event.task_id}" if event.task_id else ""
        if event.artifact_id:
            details += f" artifact={event.artifact_id}"
        print(f"{index}. {event.type.value} actor={event.actor}{details} {event.message}".rstrip())

    print("\n=== Final Answer ===")
    print(run.final_result.answer if run.final_result else "No final research result")
    print("\n=== Verification ===")
    if run.final_result:
        print(f"sufficient: {str(run.final_result.verification.sufficient).lower()}")
        print(f"missing_points: {json.dumps(run.final_result.verification.missing_points, ensure_ascii=False)}")
    else:
        print("sufficient: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
