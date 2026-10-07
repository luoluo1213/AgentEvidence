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
from app.services.research_pipeline import ResearchPipeline
from scripts.demo_research_agent import build_local_knowledge_service
from scripts.demo_research_draft import DemoEvidenceVerifierClient, DemoGroundedDraftClient
from scripts.demo_task_analyzer import DemoMockAiClient


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run the end-to-end evidence-grounded research pipeline.")
    parser.add_argument("query")
    parser.add_argument("--debug", action="store_true", help="Print retrieval details and canonical evidence content.")
    parser.add_argument("--live", action="store_true", help="Use the configured live LLM provider instead of deterministic demo providers.")
    args = parser.parse_args(argv)

    settings = Settings(knowledge_vector_enabled=False)
    use_mock = not args.live
    analyzer_client = DemoMockAiClient() if use_mock else AiClient(settings)
    draft_client = DemoGroundedDraftClient() if use_mock else AiClient(settings)
    verifier_client = DemoEvidenceVerifierClient() if use_mock else AiClient(settings)
    knowledge, db = build_local_knowledge_service(settings)
    try:
        pipeline = ResearchPipeline(
            TaskAnalyzerAgent(analyzer_client),
            ResearchAgent(
                knowledge,
                top_k=settings.research_retrieval_top_k,
                max_evidence_items=settings.research_max_evidence_items,
            ),
            ResearchDraftGenerator(draft_client),
            EvidenceVerifier(verifier_client),
        )
        result = pipeline.run(args.query)
    finally:
        db.close()

    print("=== Final Answer ===")
    print(result.answer)
    print("\n=== Verification ===")
    print(f"sufficient: {str(result.verification.sufficient).lower()}")
    print(f"missing_points: {json.dumps(result.verification.missing_points, ensure_ascii=False)}")
    print(f"suggested_queries: {json.dumps(result.verification.suggested_queries, ensure_ascii=False)}")
    print(f"reason: {result.verification.reason}")
    print("\n=== Sources ===")
    print("\n".join(result.sources) or "none")
    print("\n=== Claims ===")
    for index, claim in enumerate(result.draft.claims, start=1):
        print(f"Claim {index} ({claim.claim_id}) → {claim.evidence_ids}")

    if args.debug:
        print("\n=== Retrieval Details ===")
        for evidence in result.evidence_pool.items:
            print(json.dumps({
                "evidence_id": evidence.evidence_id,
                "source_id": evidence.source_id,
                "source_title": evidence.source_title,
                "section": evidence.section,
                "query_used": evidence.query_used,
                "score": evidence.score,
                "metadata": evidence.metadata,
                "canonical_content": evidence.canonical_content or evidence.content,
            }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
