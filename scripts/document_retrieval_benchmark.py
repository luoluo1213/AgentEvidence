from __future__ import annotations

import argparse
import hashlib
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
from app.services.knowledge import (
    KnowledgeService,
    RetrievalBackendStatus,
    RetrievalResultDiagnostic,
    result_key,
)
from app.services.source_ingestion import ResearchSourceIngestionService, SourceIngestionRequest


DEFAULT_DATASET = ROOT / "app" / "research_eval" / "document-retrieval-benchmark.json"
RESULTS = ROOT / "artifacts" / "results"
OUTPUTS = {
    "bm25": RESULTS / "document-retrieval-bm25.json",
    "vector": RESULTS / "document-retrieval-vector.json",
    "hybrid": RESULTS / "document-retrieval-hybrid.json",
    "comparison": RESULTS / "document-retrieval-comparison.json",
    "report": RESULTS / "document-retrieval-report.md",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark PDF retrieval with BM25, vector, and hybrid modes.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    args = parser.parse_args(argv)
    dataset_path = Path(args.dataset).resolve()
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    _validate_dataset(dataset)
    top_k = int(dataset.get("top_k", 5))
    titles = {source["source_id"]: source["document_title"] for source in dataset["sources"]}

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    with tempfile.TemporaryDirectory(prefix="document-retrieval-chroma-", ignore_cleanup_errors=True) as directory:
        temp_root = Path(directory)
        base = Settings()
        bm25_settings = base.model_copy(update={"knowledge_vector_enabled": False})
        bm25_service = KnowledgeService(db, bm25_settings)
        ingestion = ResearchSourceIngestionService(bm25_service, temp_root / "ingestion")
        corpus_summary = _ingest_sources(ingestion, dataset["sources"])
        resolved = _resolve_labels(db, dataset["cases"])

        bm25 = _evaluate_standard("bm25_only", bm25_service, dataset["cases"], resolved, titles, top_k)
        if any(row["backend"]["vector_enabled"] for row in bm25["cases"]):
            raise RuntimeError("BM25-only validation failed: vector retrieval was enabled")

        live_settings = base.model_copy(update={
            "knowledge_vector_enabled": True,
            "chroma_persist_dir": str(temp_root / "chroma"),
            "chroma_snapshot_dir": str(temp_root / "snapshots"),
            "chroma_collection_name": f"document_retrieval_{uuid.uuid4().hex}",
        })
        live_service = KnowledgeService(db, live_settings)
        vector = _evaluate_vector_only(live_service, dataset["cases"], resolved, titles, top_k)
        hybrid = _evaluate_standard("hybrid", live_service, dataset["cases"], resolved, titles, top_k)
        _require_live_vector("vector", vector)
        _require_live_vector("hybrid", hybrid)

    db.close()
    engine.dispose()
    comparison = _compare(dataset, corpus_summary, bm25, vector, hybrid)
    RESULTS.mkdir(parents=True, exist_ok=True)
    OUTPUTS["bm25"].write_text(json.dumps(bm25, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUTS["vector"].write_text(json.dumps(vector, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUTS["hybrid"].write_text(json.dumps(hybrid, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUTS["comparison"].write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUTS["report"].write_text(_markdown(comparison), encoding="utf-8")
    print("AgentEvidence Document Retrieval Benchmark")
    print(f"Cases: {len(dataset['cases'])}")
    for name, report in (("BM25", bm25), ("Vector", vector), ("Hybrid", hybrid)):
        print(f"{name}: {json.dumps(report['metrics'], ensure_ascii=False)}")
    print(f"Hybrid recovered: {comparison['hybrid_recovered_cases']}")
    print(f"All-method misses: {comparison['all_method_misses']}")
    print(f"Report: {OUTPUTS['report']}")
    return 0


def _ingest_sources(ingestion: ResearchSourceIngestionService, sources: list[dict]) -> list[dict]:
    summary = []
    for source in sources:
        path = (ROOT / source["location"]).resolve()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        if digest != source["sha256"]:
            raise ValueError(f"PDF SHA256 mismatch for {source['source_id']}")
        result = ingestion.ingest(SourceIngestionRequest(
            source_type="paper",
            source_id=source["source_id"],
            location=str(path),
        ))
        if result.status not in {"completed", "unchanged"} or result.errors:
            raise RuntimeError(f"PDF ingestion failed for {source['source_id']}: {result.errors}")
        summary.append({
            "source_id": source["source_id"],
            "document_title": source["document_title"],
            "source_url": source["source_url"],
            "path": str(path),
            "sha256": digest,
            "chunks": result.chunks_total,
        })
    return summary


def _resolve_labels(db, cases: list[dict]) -> dict[str, list[int]]:
    resolved = {}
    for case in cases:
        rows = db.query(KnowledgeChunk).filter(KnowledgeChunk.source == case["expected_source_id"]).all()
        matches = []
        for row in rows:
            metadata = json.loads(row.metadata_json or "{}")
            if metadata.get("page") not in case["expected_pages"]:
                continue
            if (metadata.get("section") or metadata.get("symbol")) not in case["expected_sections"]:
                continue
            normalized = _normalize(row.content)
            if all(_normalize(anchor) in normalized for anchor in case["expected_evidence_anchors"]):
                matches.append(int(row.id))
        if not matches:
            raise ValueError(f"Benchmark evidence labels did not resolve for {case['case_id']}")
        resolved[case["case_id"]] = sorted(matches)
    return resolved


def _evaluate_standard(
    mode: str,
    service: KnowledgeService,
    cases: list[dict],
    resolved: dict[str, list[int]],
    titles: dict[str, str],
    top_k: int,
) -> dict:
    rows = []
    for case in cases:
        debug = service.retrieve_debug(case["query"], top_k, corpus="research")
        rows.append(_case_result(case, resolved[case["case_id"]], debug.backend, debug.diagnostics, titles, top_k))
    return _evaluation_report(mode, service, rows, top_k)


def _evaluate_vector_only(
    service: KnowledgeService,
    cases: list[dict],
    resolved: dict[str, list[int]],
    titles: dict[str, str],
    top_k: int,
) -> dict:
    rows = []
    for case in cases:
        candidates, query_used, failure = service._retrieve_vector_with_status(
            case["query"], service._candidate_k(top_k), corpus="research"
        )
        if failure or not query_used:
            raise RuntimeError(f"Vector-only validation failed for {case['case_id']}: {failure or 'Chroma query not used'}")
        ranked = service._rerank(case["query"], candidates, top_k)
        results = service._expand_best(ranked, top_k) if ranked else []
        raw_scores = {result_key(item): item.score for item in candidates}
        final_scores = {result_key(item): item.score for item in ranked}
        diagnostics = []
        for rank, item in enumerate(results, start=1):
            key = result_key(item)
            final_score = final_scores.get(key, item.score)
            diagnostics.append(RetrievalResultDiagnostic(
                chunk_id=item.chunk_id,
                source_id=item.source,
                file_path=item.metadata.get("file_path"),
                section=item.section,
                symbol=item.metadata.get("symbol"),
                qualified_symbol=item.metadata.get("qualified_symbol"),
                final_rank=rank,
                final_score=final_score,
                bm25_score=None,
                vector_score=raw_scores.get(key),
                fusion_score=None,
                rerank_score=final_score if service.settings.knowledge_rerank_enabled else None,
                retrieved_by=["vector"],
            ))
        backend = RetrievalBackendStatus(
            vector_enabled=True,
            embedding_backend="openai-compatible",
            embedding_model=service.settings.openai_embedding_model,
            chroma_query_used=True,
            bm25_used=False,
            fallback_used=False,
            fallback_reason=None,
        )
        rows.append(_case_result(case, resolved[case["case_id"]], backend, diagnostics, titles, top_k))
    return _evaluation_report("vector_only", service, rows, top_k)


def _case_result(case, expected_ids, backend, diagnostics, titles, top_k):
    top = []
    for item in diagnostics[:top_k]:
        values = asdict(item)
        values["document_title"] = titles.get(item.source_id, item.source_id)
        values["page"] = _page_from_diagnostic(item)
        values["expected_evidence_match"] = item.chunk_id in expected_ids
        top.append(values)
    first_rank = next((item["final_rank"] for item in top if item["expected_evidence_match"]), None)
    source_hit = any(item["source_id"] == case["expected_source_id"] for item in top)
    return {
        "case_id": case["case_id"],
        "query": case["query"],
        "query_type": case["query_type"],
        "expected_source_id": case["expected_source_id"],
        "expected_pages": case["expected_pages"],
        "expected_sections": case["expected_sections"],
        "expected_evidence_anchors": case["expected_evidence_anchors"],
        "resolved_expected_chunk_ids": expected_ids,
        "backend": asdict(backend),
        "first_expected_rank": first_rank,
        "source_hit_at_5": source_hit,
        "top_5": top,
    }


def _page_from_diagnostic(item: RetrievalResultDiagnostic) -> int | None:
    if item.section and item.section.startswith("Page "):
        try:
            return int(item.section.removeprefix("Page ").strip())
        except ValueError:
            return None
    return None


def _evaluation_report(mode, service, rows, top_k):
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
        "metrics_by_query_type": {
            query_type: _metrics([row for row in rows if row["query_type"] == query_type])
            for query_type in ("lexical", "paraphrase", "method")
        },
        "cases": rows,
    }


def _metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"evidence_hit_at_1": 0.0, "evidence_hit_at_3": 0.0, "evidence_hit_at_5": 0.0, "mrr": 0.0, "source_hit_at_5": 0.0}
    return {
        "evidence_hit_at_1": sum(row["first_expected_rank"] is not None and row["first_expected_rank"] <= 1 for row in rows) / len(rows),
        "evidence_hit_at_3": sum(row["first_expected_rank"] is not None and row["first_expected_rank"] <= 3 for row in rows) / len(rows),
        "evidence_hit_at_5": sum(row["first_expected_rank"] is not None and row["first_expected_rank"] <= 5 for row in rows) / len(rows),
        "mrr": sum(1.0 / row["first_expected_rank"] if row["first_expected_rank"] else 0.0 for row in rows) / len(rows),
        "source_hit_at_5": sum(row["source_hit_at_5"] for row in rows) / len(rows),
    }


def _require_live_vector(mode: str, report: dict) -> None:
    invalid = [
        row["case_id"] for row in report["cases"]
        if row["backend"]["fallback_used"] or not row["backend"]["chroma_query_used"]
    ]
    if invalid:
        raise RuntimeError(f"{mode} run was invalid because live Chroma was not used: {invalid}")


def _compare(dataset, corpus, bm25, vector, hybrid):
    reports = {"bm25": bm25, "vector": vector, "hybrid": hybrid}
    indexed = {name: {row["case_id"]: row for row in report["cases"]} for name, report in reports.items()}
    recovered = []
    all_missed = []
    semantic_noise = []
    failure_analysis = []
    for case in dataset["cases"]:
        case_id = case["case_id"]
        ranks = {name: indexed[name][case_id]["first_expected_rank"] for name in reports}
        if ranks["bm25"] is None and ranks["hybrid"] is not None:
            recovered.append(case_id)
        if all(rank is None for rank in ranks.values()):
            all_missed.append(case_id)
        bm25_ids = {item["chunk_id"] for item in indexed["bm25"][case_id]["top_5"]}
        vector_noise = [
            {"chunk_id": item["chunk_id"], "source_id": item["source_id"], "rank": item["final_rank"]}
            for item in indexed["hybrid"][case_id]["top_5"]
            if item["chunk_id"] not in bm25_ids and "vector" in item["retrieved_by"] and not item["expected_evidence_match"]
        ]
        if vector_noise and not (ranks["hybrid"] is not None and (ranks["bm25"] is None or ranks["hybrid"] < ranks["bm25"])):
            semantic_noise.append(case_id)
        failure_analysis.append({
            "case_id": case_id,
            "query_type": case["query_type"],
            "bm25_rank": ranks["bm25"],
            "vector_rank": ranks["vector"],
            "hybrid_rank": ranks["hybrid"],
            "hybrid_recovered": case_id in recovered,
            "vector_added_non_expected_candidates": vector_noise,
            "failure_cause": "retrieval_miss" if case_id in all_missed else None,
            "chunk_boundary_issue": False,
        })
    best_by_type = {}
    for query_type in ("lexical", "paraphrase", "method"):
        scores = {name: report["metrics_by_query_type"][query_type]["evidence_hit_at_5"] for name, report in reports.items()}
        best = max(scores.values())
        best_by_type[query_type] = {"best_methods": [name for name, score in scores.items() if score == best], "evidence_hit_at_5": best}
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(dataset["cases"]),
        "query_type_distribution": {query_type: sum(case["query_type"] == query_type for case in dataset["cases"]) for query_type in ("lexical", "paraphrase", "method")},
        "corpus": corpus,
        "metrics": {name: report["metrics"] for name, report in reports.items()},
        "metrics_by_query_type": {name: report["metrics_by_query_type"] for name, report in reports.items()},
        "best_by_query_type": best_by_type,
        "hybrid_recovered_cases": recovered,
        "vector_semantic_noise_cases": semantic_noise,
        "all_method_misses": all_missed,
        "failure_analysis": failure_analysis,
        "backend_validation": {
            "bm25_vector_disabled": all(not row["backend"]["vector_enabled"] for row in bm25["cases"]),
            "vector_chroma_used": all(row["backend"]["chroma_query_used"] for row in vector["cases"]),
            "hybrid_chroma_used": all(row["backend"]["chroma_query_used"] for row in hybrid["cases"]),
            "vector_fallback_used": any(row["backend"]["fallback_used"] for row in vector["cases"]),
            "hybrid_fallback_used": any(row["backend"]["fallback_used"] for row in hybrid["cases"]),
        },
    }


def _markdown(comparison: dict) -> str:
    pct = lambda value: f"{value * 100:.2f}%"
    lines = [
        "# Step 11 — PDF / Document Retrieval Benchmark",
        "",
        f"Cases: {comparison['case_count']}  ",
        f"Distribution: {comparison['query_type_distribution']}",
        "",
        "## Corpus",
        "",
    ]
    for source in comparison["corpus"]:
        lines.append(f"- {source['document_title']} (`{source['source_id']}`): {source['chunks']} chunks, SHA256 `{source['sha256']}`")
    lines.extend(["", "## Overall metrics", "", "| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Source Hit@5 |", "|---|---:|---:|---:|---:|---:|"])
    for mode in ("bm25", "vector", "hybrid"):
        m = comparison["metrics"][mode]
        lines.append(f"| {mode} | {pct(m['evidence_hit_at_1'])} | {pct(m['evidence_hit_at_3'])} | {pct(m['evidence_hit_at_5'])} | {m['mrr']:.4f} | {pct(m['source_hit_at_5'])} |")
    lines.extend(["", "## Metrics by query type", "", "| Type | Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Source Hit@5 |", "|---|---|---:|---:|---:|---:|---:|"])
    for query_type in ("lexical", "paraphrase", "method"):
        for mode in ("bm25", "vector", "hybrid"):
            m = comparison["metrics_by_query_type"][mode][query_type]
            lines.append(f"| {query_type} | {mode} | {pct(m['evidence_hit_at_1'])} | {pct(m['evidence_hit_at_3'])} | {pct(m['evidence_hit_at_5'])} | {m['mrr']:.4f} | {pct(m['source_hit_at_5'])} |")
    lines.extend([
        "",
        "## Comparison",
        "",
        f"- Best by query type: `{json.dumps(comparison['best_by_query_type'], ensure_ascii=False)}`",
        f"- Hybrid recovered over BM25: {', '.join(comparison['hybrid_recovered_cases']) or 'none'}",
        f"- Vector semantic-noise cases: {', '.join(comparison['vector_semantic_noise_cases']) or 'none'}",
        f"- Missed by all methods: {', '.join(comparison['all_method_misses']) or 'none'}",
        "- Chunk-boundary failures: none; every label resolved to at least one real chunk before evaluation.",
        "",
        "## Backend validation",
        "",
    ])
    for key, value in comparison["backend_validation"].items():
        lines.append(f"- {key}: {value}")
    lines.extend([
        "",
        "## Limitations",
        "",
        "- This is a small 18-case internal benchmark over three papers.",
        "- Ground truth is deterministic anchor/page matching, not graded answer relevance.",
        "- Chroma telemetry warnings from the installed client do not affect retrieval results.",
    ])
    return "\n".join(lines) + "\n"


def _validate_dataset(dataset: dict) -> None:
    cases = dataset.get("cases", [])
    if not 15 <= len(cases) <= 20:
        raise ValueError("Document benchmark must contain 15-20 cases")
    if {case["query_type"] for case in cases} != {"lexical", "paraphrase", "method"}:
        raise ValueError("Document benchmark must cover lexical, paraphrase, and method queries")
    if len(dataset.get("sources", [])) < 3:
        raise ValueError("Document benchmark requires at least three sources")


def _normalize(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


if __name__ == "__main__":
    raise SystemExit(main())
