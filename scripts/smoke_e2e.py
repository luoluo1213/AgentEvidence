from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings, settings_for_research_llm
from app.core.database import SessionLocal
from app.research_harness.harness import ResearchHarness
from app.services.ai import AiClient
from app.services.knowledge import KnowledgeService
from app.services.research_runtime import ResearchEventDrivenRuntime
from app.research_harness.harness import HarnessEvidenceVerifier

settings = Settings()
db = SessionLocal()

try:
    client = AiClient(settings_for_research_llm(settings))

    harness = ResearchHarness.from_settings(settings)
    harness.begin_case("clean-e2e-smoke")

    knowledge = KnowledgeService(db, settings)

    analyzer = TaskAnalyzerAgent(
        harness.wrap_client(
            client,
            stage="analysis",
            agent="TaskAnalyzer",
        )
    )

    researcher = ResearchAgent(
        knowledge,
        top_k=settings.research_retrieval_top_k,
        max_evidence_items=settings.research_max_evidence_items,
    )

    draft_generator = harness.wrap_draft_generator(
        ResearchDraftGenerator(
            harness.wrap_client(
                client,
                stage="draft",
                agent="DraftAgent",
            )
        )
    )

    raw_verifier = EvidenceVerifier(
        harness.wrap_client(
            client,
            stage="verification",
            agent="EvidenceVerifier",
        )
    )

    verifier = HarnessEvidenceVerifier(
        raw_verifier,
        harness,
    )

    runtime = ResearchEventDrivenRuntime(
        analyzer,
        researcher,
        draft_generator,
        verifier,
        settings,
    )

    QUERY = (
    "Compare ReAct and Reflexion. "
    "How does each method use environmental interaction, feedback, or reflection "
    "to improve an agent's subsequent reasoning or behavior?"
    )

    run = runtime.run(QUERY)

    print("\n=== Research Task ===")

    for artifact in run.board.artifacts:
        if artifact.kind == "research_task":
            task = artifact.payload["value"]
            print(task.model_dump())


    print("\n=== Evidence Pool ===")

    for artifact in run.board.artifacts:
        if artifact.kind == "evidence_pool":
            pool = artifact.payload["value"]

            print("items =", len(pool.items))
            print("sources =", pool.source_ids())

            for item in pool.items:
                print(
                    "\n",
                    item.evidence_id,
                    "| source =", item.source_id,
                    "| score =", item.score,
                )
                print(item.content[:400])

    print("\n=== Final Answer ===")
    if run.final_result:
        print(run.final_result.answer)
    else:
        print("NO FINAL RESULT")

    print("\n=== Sources ===")
    if run.final_result:
        print(run.final_result.sources)

    print("\n=== Verification ===")
    if run.final_result:
        print(run.final_result.verification.model_dump())

    print("\n=== Blackboard Artifacts ===")
    for artifact in run.board.artifacts:
        print(
            artifact.kind,
            "->",
            type(artifact.payload.get("value")).__name__,
        )

    print("\n=== Harness Diagnostics ===")
    print(harness.diagnostics.as_record_fields())

finally:
    db.close()