from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.research_agent import ResearchAgent
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings
from app.core.database import Base
from app.services.ai import AiClient
from app.services.knowledge import KnowledgeService
from app.services.research_corpus import ResearchCorpusLoader
from scripts.demo_task_analyzer import DemoMockAiClient


def build_local_knowledge_service(settings: Settings, *, legacy: bool = False, include_translations: bool = True):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    service = KnowledgeService(db, settings)
    corpus_root = PROJECT_ROOT / "data" / "research_corpus"
    if legacy:
        for path in sorted(corpus_root.glob("*/content.md")):
            service.ingest(f"research:{path.parent.name}", path.read_text(encoding="utf-8"))
    else:
        ResearchCorpusLoader(corpus_root).bootstrap(service, include_translations=include_translations)
    return service, db


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run TaskAnalyzerAgent and ResearchAgent against the current corpus.")
    parser.add_argument("query")
    parser.add_argument("--mock", action="store_true", help="Use the deterministic local task-analyzer provider.")
    parser.add_argument("--legacy", action="store_true", help="Use Step 4.5 processed files and fixed-window chunking.")
    parser.add_argument("--no-translations", action="store_true", help="Use normalized English chunks without bilingual retrieval text.")
    args = parser.parse_args(argv)

    settings = Settings(knowledge_vector_enabled=False)
    analyzer_client = DemoMockAiClient() if args.mock or settings.ai_provider.lower() == "mock" else AiClient(settings)
    task = TaskAnalyzerAgent(analyzer_client).analyze(args.query)
    knowledge, db = build_local_knowledge_service(
        settings,
        legacy=args.legacy,
        include_translations=not args.no_translations,
    )
    try:
        print("=== Retrieval Diagnostics ===")
        questions = (task.research_questions or [task.query])[:4]
        for question in questions:
            raw = knowledge.retrieve(question, settings.research_retrieval_top_k, corpus="research")
            print(f"Research Question: {question}")
            print(f"Raw result count: {len(raw)}")
            print(f"Raw top source IDs: {[item.source for item in raw]}")
            print(f"Raw top sections: {[item.section for item in raw]}")
            print(f"After dedup count: {len({(item.chunk_id, item.source) for item in raw})}")
        pool = ResearchAgent(
            knowledge,
            top_k=settings.research_retrieval_top_k,
            max_evidence_items=settings.research_max_evidence_items,
        ).research(task)
        print(f"After merge count: {len(pool)}")
        logical_ids = [item.evidence_id for item in pool.items]
        print(f"Duplicate logical chunk count: {len(logical_ids) - len(set(logical_ids))}")
    finally:
        db.close()

    print(f"Task Type:\n{task.task_type.value}\n")
    print("Research Questions:")
    print("\n".join(f"{index}. {question}" for index, question in enumerate(task.research_questions, start=1)))
    print("\n=== Evidence ===")
    if not pool.items:
        print("No research evidence found in current knowledge corpus.")
        return 0

    for index, item in enumerate(pool.items, start=1):
        canonical_preview = " ".join((item.canonical_content or item.content).split())[:240]
        chinese_preview = " ".join((item.translated_content or item.display_content or item.content).split())[:240]
        print(f"\nEvidence {index}")
        print(f"Source:\n{item.source_title}")
        print(f"Query Used:\n{item.query_used}")
        print(f"Section:\n{item.section}")
        print(f"File:\n{item.metadata.get('file_path')}")
        print(f"Symbol:\n{item.metadata.get('symbol')}")
        print(f"Content Type:\n{item.metadata.get('content_type')}")
        print(f"Chinese Preview:\n{chinese_preview}")
        print(f"Canonical English Preview:\n{canonical_preview}")
        print(f"Score:\n{item.score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
