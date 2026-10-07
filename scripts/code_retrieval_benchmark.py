from __future__ import annotations

import argparse
import json
import sys
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.models.entities import KnowledgeChunk
from app.services.knowledge import KnowledgeService
from app.services.research_corpus import ResearchCorpusLoader

DEFAULT_DATASET = ROOT / "app" / "research_eval" / "mini-swe-code-retrieval-benchmark.json"
RESULTS_ROOT = ROOT / "artifacts" / "results"
BM25_OUTPUT = RESULTS_ROOT / "mini-swe-code-retrieval-bm25.json"
HYBRID_OUTPUT = RESULTS_ROOT / "mini-swe-code-retrieval-hybrid.json"
COMPARISON_OUTPUT = RESULTS_ROOT / "mini-swe-code-retrieval-comparison.json"
REPORT_OUTPUT = RESULTS_ROOT / "mini-swe-code-retrieval-report.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare BM25-only and current hybrid code retrieval.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    args = parser.parse_args(argv)
    dataset_path = Path(args.dataset).resolve()
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    if len(cases) != 7:
        raise ValueError("Step 11A benchmark must contain exactly seven cases")
    top_k = int(dataset.get("top_k", 5))

    base = Settings()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    with tempfile.TemporaryDirectory(prefix="code-retrieval-chroma-", ignore_cleanup_errors=True) as directory:
        temp_root = Path(directory)
        bm25_settings = base.model_copy(update={"knowledge_vector_enabled": False})
        bm25_service = KnowledgeService(db, bm25_settings)
        ResearchCorpusLoader(ROOT / "data" / "research_corpus").bootstrap(bm25_service)
        db.query(KnowledgeChunk).filter(KnowledgeChunk.source != "research:mini_swe_agent").delete()
        db.commit()
        _verify_expectations(db, cases)

        bm25 = _evaluate("bm25_only", bm25_service, cases, top_k)
        if any(item["backend"]["vector_enabled"] for item in bm25["cases"]):
            raise RuntimeError("BM25-only run unexpectedly enabled vector retrieval")

        hybrid_settings = base.model_copy(update={
            "knowledge_vector_enabled": True,
            "chroma_persist_dir": str(temp_root / "chroma"),
            "chroma_snapshot_dir": str(temp_root / "snapshots"),
            "chroma_collection_name": f"code_retrieval_{uuid.uuid4().hex}",
        })
        hybrid_service = KnowledgeService(db, hybrid_settings)
        hybrid = _evaluate("hybrid", hybrid_service, cases, top_k)
        invalid_hybrid = [
            item["case_id"] for item in hybrid["cases"]
            if item["backend"]["fallback_used"] or not item["backend"]["chroma_query_used"]
        ]
        if invalid_hybrid:
            raise RuntimeError(f"Hybrid validation failed for cases: {invalid_hybrid}")

    db.close()
    engine.dispose()
    comparison = _compare(dataset_path, bm25, hybrid)
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    BM25_OUTPUT.write_text(json.dumps(bm25, ensure_ascii=False, indent=2), encoding="utf-8")
    HYBRID_OUTPUT.write_text(json.dumps(hybrid, ensure_ascii=False, indent=2), encoding="utf-8")
    COMPARISON_OUTPUT.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_OUTPUT.write_text(_markdown(comparison), encoding="utf-8")
    print("mini-SWE-agent Code Retrieval Benchmark")
    print(f"Cases: {len(cases)}")
    print(f"BM25-only: {json.dumps(bm25['metrics'], ensure_ascii=False)}")
    print(f"Hybrid: {json.dumps(hybrid['metrics'], ensure_ascii=False)}")
    print(f"Hybrid recovered: {comparison['hybrid_recovered_cases']}")
    print(f"Hybrid missed: {comparison['hybrid_remaining_misses']}")
    print(f"Vector noise: {comparison['vector_noise_cases']}")
    print(f"Report: {REPORT_OUTPUT}")
    return 0


def _evaluate(mode: str, service: KnowledgeService, cases: list[dict], top_k: int) -> dict:
    rows = []
    for case in cases:
        debug = service.retrieve_debug(case["query"], top_k, corpus="research")
        diagnostics = [asdict(item) for item in debug.diagnostics[:top_k]]
        ranks = _symbol_ranks(case, diagnostics)
        first_rank = min((rank for rank in ranks.values() if rank is not None), default=None)
        rows.append({
            "case_id": case["case_id"],
            "query": case["query"],
            "expected_source_id": case["expected_source_id"],
            "expected_symbols": case["expected_symbols"],
            "qualified_symbols": case.get("qualified_symbols", []),
            "expected_file_paths": case.get("expected_file_paths", []),
            "backend": asdict(debug.backend),
            "symbol_ranks": ranks,
            "first_expected_rank": first_rank,
            "any_expected_symbol_hit_at_5": first_rank is not None and first_rank <= 5,
            "all_expected_symbols_hit_at_5": all(rank is not None and rank <= 5 for rank in ranks.values()),
            "top_5": diagnostics,
        })
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "top_k": top_k,
        "ranking": {
            "candidate_k": service.settings.knowledge_candidate_k,
            "vector_weight": service.settings.knowledge_hybrid_vector_weight,
            "bm25_weight": service.settings.knowledge_hybrid_bm25_weight,
            "rerank_enabled": service.settings.knowledge_rerank_enabled,
        },
        "metrics": _metrics(rows),
        "cases": rows,
    }


def _symbol_ranks(case: dict, diagnostics: list[dict]) -> dict[str, int | None]:
    ranks = {}
    for expected in case["expected_symbols"]:
        rank = next((
            item["final_rank"] for item in diagnostics
            if item["source_id"] == case["expected_source_id"]
            and expected in {item.get("symbol"), item.get("qualified_symbol")}
        ), None)
        ranks[expected] = rank
    return ranks


def _metrics(rows: list[dict]) -> dict:
    ranks = [rank for row in rows for rank in row["symbol_ranks"].values()]
    total_symbols = len(ranks)
    total_cases = len(rows)
    return {
        "symbol_hit_at_1": sum(rank is not None and rank <= 1 for rank in ranks) / total_symbols,
        "symbol_hit_at_3": sum(rank is not None and rank <= 3 for rank in ranks) / total_symbols,
        "symbol_hit_at_5": sum(rank is not None and rank <= 5 for rank in ranks) / total_symbols,
        "any_expected_symbol_hit_at_5": sum(row["any_expected_symbol_hit_at_5"] for row in rows) / total_cases,
        "all_expected_symbols_hit_at_5": sum(row["all_expected_symbols_hit_at_5"] for row in rows) / total_cases,
        "mrr": sum(1.0 / row["first_expected_rank"] if row["first_expected_rank"] else 0.0 for row in rows) / total_cases,
    }


def _verify_expectations(db, cases: list[dict]) -> None:
    rows = db.query(KnowledgeChunk).filter(KnowledgeChunk.source == "research:mini_swe_agent").all()
    observed: dict[str, set[str]] = {}
    for row in rows:
        metadata = json.loads(row.metadata_json or "{}")
        for symbol in {metadata.get("symbol"), metadata.get("qualified_symbol")} - {None}:
            observed.setdefault(str(symbol), set()).add(str(metadata.get("file_path") or ""))
    for case in cases:
        for symbol in case["expected_symbols"]:
            if symbol not in observed:
                raise ValueError(f"Expected symbol is absent from corpus metadata: {symbol}")
            paths = set(case.get("expected_file_paths", []))
            if paths and not (observed[symbol] & paths):
                raise ValueError(f"Expected path does not match corpus metadata for {symbol}")


def _compare(dataset_path: Path, bm25: dict, hybrid: dict) -> dict:
    bm25_cases = {item["case_id"]: item for item in bm25["cases"]}
    hybrid_cases = {item["case_id"]: item for item in hybrid["cases"]}
    recovered = []
    remaining = []
    noise = []
    changes = []
    for case_id, before in bm25_cases.items():
        after = hybrid_cases[case_id]
        if not before["any_expected_symbol_hit_at_5"] and after["any_expected_symbol_hit_at_5"]:
            recovered.append(case_id)
        if not after["all_expected_symbols_hit_at_5"]:
            remaining.append(case_id)
        before_rank = before["first_expected_rank"]
        after_rank = after["first_expected_rank"]
        before_ids = {item["chunk_id"] for item in before["top_5"]}
        expected = set(after["expected_symbols"])
        vector_added_non_expected = [
            {
                "chunk_id": item["chunk_id"],
                "symbol": item.get("symbol"),
                "rank": item["final_rank"],
            }
            for item in after["top_5"]
            if item["chunk_id"] not in before_ids
            and "vector" in item["retrieved_by"]
            and not ({item.get("symbol"), item.get("qualified_symbol")} & expected)
        ]
        rank_worsened = before_rank is not None and (after_rank is None or after_rank > before_rank)
        rank_improved = after_rank is not None and (before_rank is None or after_rank < before_rank)
        introduced_noise = rank_worsened or bool(vector_added_non_expected and not rank_improved)
        if introduced_noise:
            noise.append(case_id)
        changes.append({
            "case_id": case_id,
            "bm25_first_expected_rank": before_rank,
            "hybrid_first_expected_rank": after_rank,
            "hybrid_recovered": case_id in recovered,
            "vector_introduced_noise": introduced_noise,
            "vector_added_non_expected_top_5": vector_added_non_expected,
        })
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "cases": len(bm25_cases),
        "metric_definition": {
            "symbol_hit_at_k": "micro recall of expected symbols within top K",
            "any_expected_symbol_hit_at_5": "fraction of cases with at least one expected symbol in top 5",
            "all_expected_symbols_hit_at_5": "fraction of cases with every expected symbol in top 5",
            "mrr": "mean reciprocal rank of the first expected symbol per case; misses score zero",
        },
        "bm25_only_metrics": bm25["metrics"],
        "hybrid_metrics": hybrid["metrics"],
        "hybrid_recovered_cases": recovered,
        "hybrid_remaining_misses": remaining,
        "vector_noise_cases": noise,
        "per_case_changes": changes,
        "validation": {
            "bm25_vector_disabled": all(not item["backend"]["vector_enabled"] for item in bm25["cases"]),
            "hybrid_chroma_used": all(item["backend"]["chroma_query_used"] for item in hybrid["cases"]),
            "hybrid_fallback_used": any(item["backend"]["fallback_used"] for item in hybrid["cases"]),
        },
    }


def _markdown(comparison: dict) -> str:
    def percent(value: float) -> str:
        return f"{value * 100:.2f}%"

    lines = [
        "# Step 11A — Code Retrieval Baseline: BM25 vs Hybrid",
        "",
        f"Cases: {comparison['cases']}",
        "",
        "| Metric | BM25-only | Hybrid |",
        "|---|---:|---:|",
    ]
    for key in ("symbol_hit_at_1", "symbol_hit_at_3", "symbol_hit_at_5", "any_expected_symbol_hit_at_5", "all_expected_symbols_hit_at_5", "mrr"):
        lines.append(f"| {key} | {percent(comparison['bm25_only_metrics'][key])} | {percent(comparison['hybrid_metrics'][key])} |")
    lines.extend([
        "",
        f"- Hybrid recovered: {', '.join(comparison['hybrid_recovered_cases']) or 'none'}",
        f"- Hybrid remaining misses: {', '.join(comparison['hybrid_remaining_misses']) or 'none'}",
        f"- Vector introduced noise: {', '.join(comparison['vector_noise_cases']) or 'none'}",
        "",
        "## Per-case first expected-symbol rank",
        "",
        "| Case | BM25 | Hybrid | Recovered | Vector noise |",
        "|---|---:|---:|---|---|",
    ])
    for row in comparison["per_case_changes"]:
        lines.append(
            f"| {row['case_id']} | {row['bm25_first_expected_rank'] or 'miss'} | "
            f"{row['hybrid_first_expected_rank'] or 'miss'} | {row['hybrid_recovered']} | {row['vector_introduced_noise']} |"
        )
    lines.extend([
        "",
        "## Validation",
        "",
        f"- BM25 vector disabled: {comparison['validation']['bm25_vector_disabled']}",
        f"- Hybrid Chroma used for every case: {comparison['validation']['hybrid_chroma_used']}",
        f"- Hybrid fallback used: {comparison['validation']['hybrid_fallback_used']}",
    ])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
