from app.core.config import Settings
from app.core.database import SessionLocal
from app.services.knowledge import KnowledgeService


QUERY = (
    "How does ReAct interleave reasoning and acting, "
    "and how does interaction with the external environment "
    "incorporate information into reasoning?"
)

settings = Settings()
db = SessionLocal()

try:
    knowledge = KnowledgeService(db, settings)

    debug = knowledge.retrieve_debug(
        QUERY,
        top_k=5,
        corpus="research",
    )

    print("\n=== Backend ===")
    print(debug.backend)

    print("\n=== Retrieval Results ===")

    for rank, result in enumerate(debug.results, start=1):
        metadata = result.metadata or {}

        print("\n" + "=" * 70)
        print("rank   =", rank)
        print("source =", result.source)
        print("score  =", round(result.score, 4))
        print("page   =", metadata.get("page"))
        print("section=", metadata.get("section"))
        print(result.content[:1200])

    print("\n=== Diagnostics ===")

    for item in debug.diagnostics:
        print(
            "rank=", item.final_rank,
            "source=", item.source_id,
            "bm25=", item.bm25_score,
            "vector=", item.vector_score,
            "fusion=", item.fusion_score,
            "rerank=", item.rerank_score,
            "retrieved_by=", item.retrieved_by,
        )

finally:
    db.close()