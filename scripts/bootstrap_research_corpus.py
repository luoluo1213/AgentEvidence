from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.core.database import Base
from app.services.knowledge import KnowledgeService
from app.services.research_corpus import ResearchCorpusLoader


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest provenance-backed research corpus files.")
    parser.add_argument("--database-url", help="Override DATABASE_URL (useful for local integration validation).")
    parser.add_argument("--no-vector", action="store_true", help="Disable vector indexing for local fallback validation.")
    args = parser.parse_args(argv)
    overrides = {}
    if args.database_url:
        overrides["database_url"] = args.database_url
    if args.no_vector:
        overrides["knowledge_vector_enabled"] = False
    settings = Settings(**overrides)
    engine_args = {"connect_args": {"check_same_thread": False}} if settings.database_url.startswith("sqlite") else {}
    engine = create_engine(settings.database_url, **engine_args)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        service = KnowledgeService(db, settings)
        rows = ResearchCorpusLoader(PROJECT_ROOT / "data" / "research_corpus").bootstrap(service)
        print("=== Research Corpus Bootstrap ===")
        for metadata, count in rows:
            print(f"Source: {metadata.namespace}\nType: {metadata.source_type.value}\nChunks: {count}\n")
        print(f"Total sources: {len(rows)}")
        print(f"Total chunks: {sum(count for _, count in rows)}")
        if service.vector_store.can_embed:
            service.rebuild_vector_index()
            print("Vector indexing: completed")
        else:
            print(f"Vector indexing: unavailable ({service.vector_store.error}); BM25 fallback ready")
    finally:
        db.close()
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
