from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.bootstrap import create_schema
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.knowledge import KnowledgeService
from app.services.research_chat import build_research_runtime
from app.services.source_ingestion import ResearchSourceIngestionService, SourceIngestionRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a GitHub repository or local PDF into Research RAG.")
    parser.add_argument("source_type", choices=("repository", "paper"))
    parser.add_argument("source_id", help="Research namespace, for example research:sampleproject")
    parser.add_argument("location", help="Public GitHub URL or local PDF path")
    parser.add_argument("--revision", help="Optional repository commit/tag")
    parser.add_argument("--query", help="Run a retrieval smoke query after ingestion")
    parser.add_argument("--debug-retrieval", action="store_true", help="Print retrieval backend and component scores")
    parser.add_argument("--runtime-query", help="Run the existing multi-agent Research Runtime after ingestion")
    args = parser.parse_args(argv)

    create_schema()
    db = SessionLocal()
    try:
        knowledge = KnowledgeService(db, get_settings())
        result = ResearchSourceIngestionService(knowledge).ingest(SourceIngestionRequest(
            source_type=args.source_type,
            source_id=args.source_id,
            location=args.location,
            revision=args.revision,
        ))
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        if result.status == "failed":
            return 1
        if args.query:
            debug = knowledge.retrieve_debug(args.query, 8, corpus="research") if args.debug_retrieval else None
            hits = debug.results if debug is not None else knowledge.retrieve(args.query, 8, corpus="research")
            selected = [item for item in hits if item.source == args.source_id]
            if debug is not None:
                print("\n=== Retrieval Backend ===")
                print(json.dumps(asdict(debug.backend), ensure_ascii=False, indent=2))
                print("\n=== Retrieval Diagnostics ===")
                print(json.dumps([
                    asdict(item) for item in debug.diagnostics if item.source_id == args.source_id
                ], ensure_ascii=False, indent=2))
            print("\n=== Retrieval Hits ===")
            print(json.dumps([
                {
                    "chunk_id": item.chunk_id,
                    "source_id": item.source,
                    "section": item.section,
                    "file_path": item.metadata.get("file_path"),
                    "symbol": item.metadata.get("symbol"),
                    "page": item.metadata.get("page"),
                    "score": item.score,
                }
                for item in selected
            ], ensure_ascii=False, indent=2))
            if not selected:
                return 2
        if args.runtime_query:
            run = build_research_runtime(db, get_settings()).run(args.runtime_query)
            if run.final_result is None:
                print("Research Runtime completed without a final result", file=sys.stderr)
                return 3
            print("\n=== Research Runtime ===")
            print(json.dumps({
                "answer": run.final_result.answer,
                "sources": run.final_result.sources,
                "verification": run.final_result.verification.model_dump(mode="json"),
            }, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
