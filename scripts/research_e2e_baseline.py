from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import FALLBACK_ANSWER, ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import get_settings, settings_for_research_llm
from app.core.database import SessionLocal
from app.models.entities import KnowledgeChunk
from app.research_harness.checkpoint import CheckpointStore
from app.research_harness.errors import ProviderError
from app.research_harness.harness import ResearchHarness, latency_by_stage
from app.services.ai import AiClient
from app.services.knowledge import KnowledgeService
from app.services.memory import RedisShortTermMemoryStore
from app.services.research_memory import ResearchMemoryService
from app.services.research_runtime import ResearchEventDrivenRuntime
from scripts.research_e2e_benchmark import (
    StatelessEvaluationMemory,
    cleanup,
    create_case_identity,
    sanitize,
)


DATASET = ROOT / "app" / "research_eval" / "research-e2e-baseline.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts"
REQUIRED_SOURCES = (
    "research:attention_pdf",
    "research:react_pdf",
    "research:reflexion_pdf",
)
REQUIRED_CATEGORIES = {
    "single_document": 9,
    "cross_document": 4,
    "insufficient": 3,
    "same_session": 2,
    "cross_session": 2,
}
REQUIRED_CATEGORIES_100 = {
    "single_document": 45,
    "cross_document": 25,
    "insufficient": 10,
    "same_session": 10,
    "cross_session": 10,
}
CATEGORY_PROFILES = (REQUIRED_CATEGORIES, REQUIRED_CATEGORIES_100)
HUMAN_LABELS = {"correct", "partial", "incorrect"}
RUN_VARIANT = "baseline"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the AgentEvidence E2E baseline evaluation.")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--category")
    parser.add_argument("--case-id")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--stateless-ablation", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--aggregate-human-annotations", action="store_true")
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Resume from output-dir checkpoint if present")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    paths = output_paths(output_dir)
    if args.aggregate_human_annotations:
        return write_aggregated_report(paths)

    dataset = _read_json(Path(args.dataset))
    validate_dataset(dataset)
    cases = select_cases(dataset["cases"], args.category, args.case_id)
    if not cases:
        raise ValueError("no cases matched the requested filters")

    settings = get_settings()
    db = SessionLocal()
    created_users: list[int] = []
    redis_sessions: set[str] = set()
    redis_store = RedisShortTermMemoryStore(settings)
    started = time.perf_counter()
    checkpoint = CheckpointStore(output_dir / "research-e2e-baseline-checkpoint.json")
    completed = checkpoint.completed_records() if args.resume else {}
    results: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    try:
        preflight(
            db,
            settings,
            redis_store,
            dataset.get("required_sources") or REQUIRED_SOURCES,
        )
        knowledge = KnowledgeService(db, settings)
        for index, case in enumerate(cases, start=1):
            if case["id"] in completed:
                print(f"[{index:02d}/{len(cases)}] {case['id']} (checkpoint)", flush=True)
                results.append(completed[case["id"]])
                continue
            print(f"[{index:02d}/{len(cases)}] {case['id']}", flush=True)
            case_started = time.perf_counter()
            harness = ResearchHarness.from_settings(settings)
            harness.begin_case(case["id"])
            try:
                record = run_case(
                    case,
                    settings,
                    knowledge,
                    db,
                    redis_store,
                    created_users,
                    redis_sessions,
                    index,
                    args.stateless_ablation,
                    harness,
                )
            except ProviderError as exc:
                db.rollback()
                record = error_record(case, exc, case_started, harness)
            except Exception as exc:
                db.rollback()
                record = error_record(case, exc, case_started, harness)
            record["latency_ms"] = round((time.perf_counter() - case_started) * 1000, 3)
            results.append(record)
            traces.extend(record.get("llm_traces") or [])
            checkpoint.save(results, traces)
    finally:
        if not args.keep_data:
            cleanup(db, created_users, redis_store, redis_sessions)
        db.close()

    report = build_report(dataset, results, settings, started, args.stateless_ablation)
    annotation = build_human_annotation(dataset["cases"], results)
    write_outputs(paths, report, annotation)
    print_summary(report)
    return 0 if all(row["runtime_success"] for row in results) else 1


def output_paths(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "report_json": output_dir / "research-e2e-baseline-report.json",
        "report_md": output_dir / "research-e2e-baseline-report.md",
        "annotation_json": output_dir / "research-e2e-baseline-human-annotation.json",
        "annotation_md": output_dir / "research-e2e-baseline-human-annotation.md",
    }


def validate_dataset(dataset: dict[str, Any]) -> None:
    cases = dataset.get("cases") or []
    counts = Counter(case.get("category") for case in cases)
    if dict(counts) not in CATEGORY_PROFILES:
        raise ValueError(f"invalid case distribution: {dict(counts)}")
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    required = {"id", "category", "query", "expected_sources", "expected_concepts", "answerable"}
    for case in cases:
        missing = required - set(case)
        if missing:
            raise ValueError(f"invalid case {case.get('id')}: missing {sorted(missing)}")
        if case["category"] not in REQUIRED_CATEGORIES_100:
            raise ValueError(f"unknown category: {case['category']}")
        if case["category"] in {"same_session", "cross_session"}:
            if not case.get("prior_turns"):
                raise ValueError(f"memory case lacks prior_turns: {case['id']}")
            if not str(case.get("memory_referent") or "").strip():
                raise ValueError(f"memory case lacks memory_referent: {case['id']}")
        if case["category"] == "insufficient" and case.get("answerable") is not False:
            raise ValueError(f"insufficient case must set answerable=false: {case['id']}")
        if case["category"] == "single_document" and len(case.get("expected_sources") or []) != 1:
            raise ValueError(f"single_document case needs one expected source: {case['id']}")
        if case["category"] == "cross_document" and len(case.get("expected_sources") or []) < 2:
            raise ValueError(f"cross_document case needs multiple expected sources: {case['id']}")

    attention = [case for case in cases if case["category"] == "single_document" and case["expected_sources"] == ["research:attention_pdf"]]
    react = [case for case in cases if case["category"] == "single_document" and case["expected_sources"] == ["research:react_pdf"]]
    reflexion = [case for case in cases if case["category"] == "single_document" and case["expected_sources"] == ["research:reflexion_pdf"]]
    if dict(counts) == REQUIRED_CATEGORIES:
        if len(attention) != 3 or len(react) != 3 or len(reflexion) != 3:
            raise ValueError("single_document cases must be 3 Attention + 3 ReAct + 3 Reflexion")
    elif len(attention) < 3 or len(react) < 3 or len(reflexion) < 3:
        raise ValueError("dataset is missing the original Attention/ReAct/Reflexion single-document cases")
    required_queries = {
        "为什么 scaled dot-product attention 要除以 sqrt(d_k)？",
        "ReAct 如何交错进行推理和行动，环境反馈起什么作用？",
        "Reflexion 如何利用语言反馈和情景记忆，在多次 trial 之间改进行为？",
    }
    present = {case["query"] for case in cases}
    if not required_queries <= present:
        raise ValueError("dataset is missing the three human-verified queries")
    for case in cases:
        query = str(case.get("query") or "")
        if not re.search(r"[\u4e00-\u9fff]", query):
            raise ValueError(f"query must be Chinese: {case.get('id')}")
        for prior in case.get("prior_turns") or []:
            if not re.search(r"[\u4e00-\u9fff]", str(prior)):
                raise ValueError(f"prior_turns must be Chinese: {case.get('id')}")


def select_cases(cases: list[dict[str, Any]], category: str | None, case_id: str | None) -> list[dict[str, Any]]:
    selected = list(cases)
    if category:
        selected = [case for case in selected if case["category"] == category]
    if case_id:
        selected = [case for case in selected if case["id"] == case_id]
    return selected


def preflight(db, settings, redis_store, required_sources=REQUIRED_SOURCES) -> None:
    if settings.ai_provider.lower() not in {"openai", "ollama"}:
        raise RuntimeError("baseline evaluation requires a real provider; mock is forbidden")
    if settings.ai_provider.lower() == "openai" and not str(settings.openai_api_key or "").strip():
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if not settings.knowledge_vector_enabled:
        raise RuntimeError("Chroma/vector backend is not enabled")
    if not str(settings.chroma_persist_dir or "").strip():
        raise RuntimeError("chroma_persist_dir is not configured")
    if redis_store.client is None or not redis_store.client.ping():
        raise RuntimeError("live Redis is required for baseline memory evaluation")
    missing = []
    for source_id in required_sources:
        count = db.query(func.count(KnowledgeChunk.id)).filter(KnowledgeChunk.source == source_id).scalar() or 0
        if count <= 0:
            missing.append(source_id)
    if missing:
        raise RuntimeError("missing core research corpus chunks: " + ", ".join(missing))


def build_runtime(settings, knowledge, memory, harness: ResearchHarness):
    client = AiClient(settings_for_research_llm(settings))
    return ResearchEventDrivenRuntime(
        TaskAnalyzerAgent(harness.wrap_client(client, stage="analysis", agent="TaskAnalyzer")),
        ResearchAgent(
            knowledge,
            top_k=settings.research_retrieval_top_k,
            max_evidence_items=settings.research_max_evidence_items,
        ),
        harness.wrap_draft_generator(ResearchDraftGenerator(harness.wrap_client(client, stage="draft", agent="DraftAgent"))),
        EvidenceVerifier(harness.wrap_client(client, stage="verification", agent="EvidenceVerifier")),
        settings,
        memory,
    )


def run_turn(query: str, settings, knowledge, memory, harness: ResearchHarness, user_id=None, session_id=""):
    run = build_runtime(settings, knowledge, memory, harness).run(query, user_id=user_id, session_id=session_id)
    context_artifact = run.board.latest_artifact("conversation_context")
    context = context_artifact.payload.get("value") if context_artifact else None
    return {"run": run, "context": context, "harness": harness}


def run_case(case, settings, knowledge, db, redis_store, created_users, redis_sessions, index, stateless_ablation, harness: ResearchHarness):
    case_started = time.perf_counter()
    if case["category"] in {"same_session", "cross_session"}:
        token = uuid.uuid4().hex[:10]
        user, session_a, session_b = create_case_identity(db, token, index, case["category"] == "cross_session")
        created_users.append(user.id)
        redis_sessions.update(x for x in (session_a.public_id, session_b.public_id if session_b else "") if x)
        memory = ResearchMemoryService(db, settings, redis_store)
        hierarchical = run_memory_conversation(case, settings, knowledge, memory, user.id, session_a.public_id, session_b.public_id if session_b else None, harness)
        record = result_record(case, hierarchical, session_a.public_id if case["category"] == "same_session" else (session_b.public_id if session_b else session_a.public_id), harness)
        if stateless_ablation:
            stateless_harness = ResearchHarness.from_settings(settings)
            stateless_harness.begin_case(case["id"] + ":stateless")
            stateless = run_memory_conversation(case, settings, knowledge, StatelessEvaluationMemory(), user.id, session_a.public_id, session_b.public_id if session_b else None, stateless_harness)
            record["memory_ablation"] = {
                "hierarchical_resolved": memory_resolved(case, hierarchical.get("context")),
                "stateless_resolved": memory_resolved(case, stateless.get("context")),
            }
        else:
            record["memory_ablation"] = {
                "hierarchical_resolved": memory_resolved(case, hierarchical.get("context")),
                "stateless_resolved": None,
            }
        record["latency_ms"] = round((time.perf_counter() - case_started) * 1000, 3)
        return record

    outcome = run_turn(case["query"], settings, knowledge, StatelessEvaluationMemory(), harness)
    return result_record(case, outcome, "", harness)


def run_memory_conversation(case, settings, knowledge, memory, user_id, session_a, session_b, harness: ResearchHarness):
    for query in case.get("prior_turns") or []:
        run_turn(query, settings, knowledge, memory, harness, user_id, session_a)
    target = session_b if case["category"] == "cross_session" else session_a
    return run_turn(case["query"], settings, knowledge, memory, harness, user_id, target or "")


def result_record(case, outcome, session_id: str, harness: ResearchHarness | None = None) -> dict[str, Any]:
    run = outcome["run"]
    final = run.final_result
    actual_sources = list(final.evidence_pool.source_ids()) if final else []
    answer = final.answer if final else ""
    diagnostics = harness.diagnostics.as_record_fields() if harness is not None else {}
    provider_failure = bool(diagnostics.get("provider_failure"))
    evidence_insufficient = _detect_evidence_insufficient(final, diagnostics)
    fallback = bool(diagnostics.get("fallback_used"))
    if provider_failure or evidence_insufficient:
        fallback = False
    elif not diagnostics and is_fallback(answer, final):
        fallback = True
    agent_stage_failure = bool(diagnostics.get("agent_stage_failure")) or (
        bool(diagnostics.get("draft_validation_failure"))
        and not bool(diagnostics.get("draft_repair_success"))
        and fallback
    )
    result_status = diagnostics.get("result_status") or "success"
    if provider_failure:
        result_status = "provider_failure"
    elif evidence_insufficient:
        result_status = "evidence_insufficient"
    elif fallback:
        result_status = "draft_fallback"
    fallback_stage = None
    if evidence_insufficient:
        fallback_stage = None
    elif fallback:
        fallback_stage = diagnostics.get("failure_stage") or "draft"
    record = {
        "case_id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "expected_sources": list(case.get("expected_sources") or []),
        "expected_concepts": list(case.get("expected_concepts") or []),
        "answerable": case.get("answerable", True),
        "actual_sources": actual_sources,
        "answer": answer,
        "session_id": session_id,
        "source_hit": source_hit(case, actual_sources),
        "runtime_success": final is not None and not provider_failure,
        "provider_failure": provider_failure,
        "verification_sufficient": bool(final.verification.sufficient) if final else False,
        "fallback_used": fallback,
        "fallback_stage": fallback_stage,
        "error_type": diagnostics.get("error_type") or diagnostics.get("draft_validation_reason"),
        "error_message": diagnostics.get("error_message") or diagnostics.get("draft_validation_message"),
        "result_status": result_status,
        "agent_stage_failure": agent_stage_failure,
        "evidence_insufficient": evidence_insufficient,
        "run_variant": RUN_VARIANT,
        "memory_resolved": memory_resolved(case, outcome.get("context")) if case["category"] in {"same_session", "cross_session"} else None,
    }
    record.update({key: diagnostics[key] for key in diagnostics if key not in record})
    record["fallback_used"] = fallback
    record["evidence_insufficient"] = evidence_insufficient
    record["agent_stage_failure"] = agent_stage_failure
    record["result_status"] = result_status
    return record


def _detect_evidence_insufficient(final, diagnostics: dict[str, Any]) -> bool:
    if diagnostics.get("provider_failure"):
        return False
    if diagnostics.get("fallback_used") and diagnostics.get("draft_validation_failure") and not diagnostics.get("draft_repair_success"):
        # Failed repair fallback is an agent-stage failure, not evidence insufficiency.
        return False
    if diagnostics.get("evidence_insufficient"):
        return True
    if final is None:
        return False
    pool = getattr(final, "evidence_pool", None)
    draft = getattr(final, "draft", None)
    verification = getattr(final, "verification", None)
    if pool is not None and len(getattr(pool, "items", []) or []) == 0:
        return True
    from app.research_harness.draft_validator import is_evidence_refusal

    if draft is not None and is_evidence_refusal(draft):
        return True
    answer = str(getattr(final, "answer", "") or "")
    if verification is not None and not bool(getattr(verification, "sufficient", True)):
        if is_fallback(answer, final) or any(term in answer for term in ("不足", "无法基于", "无法回答", "insufficient")):
            if draft is None or not getattr(draft, "claims", None):
                return True
    return False


def error_record(case, exc: Exception, case_started: float, harness: ResearchHarness | None = None) -> dict[str, Any]:
    diagnostics = harness.diagnostics.as_record_fields() if harness is not None else {}
    provider_failure = True if isinstance(exc, ProviderError) else bool(diagnostics.get("provider_failure"))
    error_type = getattr(exc, "error_type", None) or diagnostics.get("error_type") or type(exc).__name__
    record = {
        "case_id": case["id"],
        "category": case["category"],
        "query": case["query"],
        "expected_sources": list(case.get("expected_sources") or []),
        "expected_concepts": list(case.get("expected_concepts") or []),
        "answerable": case.get("answerable", True),
        "actual_sources": [],
        "answer": "",
        "session_id": "",
        "source_hit": False,
        "runtime_success": False,
        "provider_failure": provider_failure,
        "verification_sufficient": False,
        "fallback_used": False,
        "fallback_stage": None,
        "error_type": error_type,
        "error_message": sanitize(str(exc)),
        "failure_stage": getattr(exc, "stage", None) or diagnostics.get("failure_stage") or "runtime",
        "run_variant": RUN_VARIANT,
        "latency_ms": round((time.perf_counter() - case_started) * 1000, 3),
        "memory_resolved": None,
    }
    record.update({key: diagnostics[key] for key in diagnostics if key not in record or record.get(key) in {None, False, 0, ""}})
    record["provider_failure"] = provider_failure
    record["fallback_used"] = False
    return record


def source_hit(case: dict[str, Any], actual_sources: list[str]) -> bool | None:
    expected = list(case.get("expected_sources") or [])
    actual = set(actual_sources or [])
    if case.get("category") == "single_document":
        return bool(expected) and expected[0] in actual
    if case.get("category") == "cross_document":
        return bool(expected) and all(source in actual for source in expected)
    return None


def memory_resolved(case: dict[str, Any], context) -> bool:
    referent = str(case.get("memory_referent") or "").strip().casefold()
    if not referent or context is None:
        return False
    if hasattr(context, "model_dump"):
        payload = context.model_dump()
    elif isinstance(context, dict):
        payload = context
    else:
        return False
    searchable = "\n".join([
        str(payload.get("contextualized_query") or ""),
        str(payload.get("session_summary") or ""),
        *(str(item) for item in payload.get("long_term_memories") or []),
        *(str(message.get("content") if isinstance(message, dict) else getattr(message, "content", "")) for message in payload.get("recent_messages") or []),
    ]).casefold()
    tokens = [token for token in referent.replace("—", " ").replace("-", " ").split() if len(token) > 2]
    haystack = searchable.replace("-", " ")
    return bool(tokens) and all(token in haystack for token in tokens)


def is_fallback(answer: str, final) -> bool:
    if not answer:
        return False
    if answer.strip() == FALLBACK_ANSWER:
        return True
    if final is not None and not final.draft.claims and FALLBACK_ANSWER[:4] in answer:
        return True
    return False


def latency_summary(results: list[dict[str, Any]]) -> dict[str, float | None]:
    values = [row["latency_ms"] for row in results if row.get("latency_ms") is not None]
    if not values:
        return {"avg_latency_ms": None, "median_latency_ms": None}
    return {
        "avg_latency_ms": round(sum(values) / len(values), 3),
        "median_latency_ms": round(statistics.median(values), 3),
    }


def memory_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    def _rate(category: str, key: str) -> dict[str, Any]:
        rows = [row for row in results if row.get("category") == category and row.get("memory_ablation")]
        values = [row["memory_ablation"].get(key) for row in rows if row["memory_ablation"].get(key) is not None]
        hits = sum(value is True for value in values)
        return {"hits": hits, "total": len(values), "rate": round(hits / len(values), 6) if values else None}

    return {
        "same_session": {
            "hierarchical": _rate("same_session", "hierarchical_resolved"),
            "stateless": _rate("same_session", "stateless_resolved"),
        },
        "cross_session": {
            "hierarchical": _rate("cross_session", "hierarchical_resolved"),
            "stateless": _rate("cross_session", "stateless_resolved"),
        },
    }


def source_hit_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    def _rate(category: str) -> dict[str, Any]:
        rows = [row for row in results if row.get("category") == category]
        hits = sum(row.get("source_hit") is True for row in rows)
        return {"hits": hits, "total": len(rows), "rate": round(hits / len(rows), 6) if rows else None}

    return {
        "single_document": _rate("single_document"),
        "cross_document": _rate("cross_document"),
    }


def build_human_annotation(dataset_cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {row["case_id"]: row for row in results}
    cases = []
    for case in dataset_cases:
        if not case.get("answerable"):
            continue
        result = by_id.get(case["id"])
        if result is None:
            continue
        cases.append({
            "id": case["id"],
            "query": case["query"],
            "answer": result.get("answer") or "",
            "expected_concepts": list(case.get("expected_concepts") or []),
            "correctness": None,
            "notes": "",
        })
    return {
        "schema_version": 1,
        "status": "PENDING HUMAN REVIEW",
        "labels": sorted(HUMAN_LABELS),
        "run_variant": RUN_VARIANT,
        "cases": cases,
    }


def aggregate_human_annotations(annotation: dict[str, Any], answerable_total: int | None = None) -> dict[str, Any]:
    cases = annotation.get("cases") or []
    total = answerable_total if answerable_total is not None else len(cases)
    labeled = [case for case in cases if case.get("correctness") in HUMAN_LABELS]
    pending = total - len(labeled)
    if pending > 0 or len(labeled) != total:
        return {
            "status": "PENDING HUMAN REVIEW",
            "strict_accuracy": None,
            "acceptable_rate": None,
            "labeled": len(labeled),
            "answerable_total": total,
            "counts": dict(Counter(case.get("correctness") for case in labeled)),
        }
    correct = sum(case["correctness"] == "correct" for case in labeled)
    partial = sum(case["correctness"] == "partial" for case in labeled)
    return {
        "status": "COMPLETE",
        "strict_accuracy": round(correct / total, 6) if total else None,
        "acceptable_rate": round((correct + partial) / total, 6) if total else None,
        "labeled": len(labeled),
        "answerable_total": total,
        "counts": dict(Counter(case["correctness"] for case in labeled)),
    }


def build_report(dataset, results, settings, started, stateless_ablation) -> dict[str, Any]:
    latencies = latency_summary(results)
    sources = source_hit_metrics(results)
    memory = memory_metrics(results)
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_variant": RUN_VARIANT,
        "future_comparison_variant": "retrieval_repair",
        "dataset": {
            "path": str(DATASET),
            "case_count": len(dataset["cases"]),
            "distribution": dict(Counter(case["category"] for case in dataset["cases"])),
        },
        "execution": {
            "provider": settings.ai_provider,
            "model": settings.openai_model if settings.ai_provider.lower() == "openai" else settings.ollama_model,
            "mock_fallback": False,
            "stateless_ablation": stateless_ablation,
        },
        "metrics": {
            "answer_correctness": {
                "status": "PENDING HUMAN REVIEW",
                "strict_accuracy": None,
                "acceptable_rate": None,
            },
            "single_document_source_hit": sources["single_document"],
            "cross_document_all_source_hit": sources["cross_document"],
            "memory": memory,
            "latency": latencies,
        },
        "diagnostics": {
            "runtime_success_rate": _rate(row.get("runtime_success") is True for row in results),
            "provider_failure_count": sum(row.get("provider_failure") is True for row in results),
            "agent_stage_failure_count": sum(row.get("agent_stage_failure") is True for row in results),
            "draft_validation_failure_count": sum(row.get("draft_validation_failure") is True for row in results),
            "draft_repair_attempt_count": sum(int(row.get("draft_repair_attempts") or 0) for row in results),
            "draft_repair_success_count": sum(row.get("draft_repair_success") is True for row in results),
            "evidence_insufficient_count": sum(row.get("evidence_insufficient") is True for row in results),
            "fallback_count": sum(row.get("fallback_used") is True for row in results),
            "draft_validation_reason_counts": dict(Counter(
                row.get("draft_validation_reason")
                for row in results
                if row.get("draft_validation_reason")
            )),
            "total_prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in results),
            "total_completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in results),
            "total_tokens": sum(int(row.get("total_tokens") or 0) for row in results),
            "estimated_cost": _sum_costs(results),
            "latency_by_stage": latency_by_stage(_flatten_traces(results)),
        },
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "results": results,
    }


def apply_human_metrics(report: dict[str, Any], human: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(report.get("metrics") or {})
    metrics["answer_correctness"] = {
        "status": human["status"],
        "strict_accuracy": human["strict_accuracy"],
        "acceptable_rate": human["acceptable_rate"],
        "counts": human.get("counts") or {},
    }
    updated = dict(report)
    updated["metrics"] = metrics
    return updated


def report_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    correctness = metrics["answer_correctness"]
    single = metrics["single_document_source_hit"]
    cross = metrics["cross_document_all_source_hit"]
    memory = metrics["memory"]
    latency = metrics["latency"]
    diag = report.get("diagnostics") or {}
    if correctness.get("strict_accuracy") is None:
        correctness_cell = "Pending / 人工标注后计算"
    else:
        correctness_cell = (
            f"Strict {percent(correctness['strict_accuracy'])}; "
            f"Acceptable {percent(correctness['acceptable_rate'])}"
        )
    same = memory["same_session"]["hierarchical"]
    cross_mem = memory["cross_session"]["hierarchical"]
    avg_s = None if latency["avg_latency_ms"] is None else round(latency["avg_latency_ms"] / 1000, 3)
    median_s = None if latency["median_latency_ms"] is None else round(latency["median_latency_ms"] / 1000, 3)
    lines = [
        "# AgentEvidence E2E Baseline",
        "",
        f"run_variant: `{report['run_variant']}`",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Answer Correctness | {correctness_cell} |",
        f"| Single-doc Source Hit | {ratio_cell(single)} |",
        f"| Cross-doc All-Source Hit | {ratio_cell(cross)} |",
        f"| Same-session Memory | {count_cell(same)} |",
        f"| Cross-session Memory | {count_cell(cross_mem)} |",
        f"| Avg Latency | {avg_s if avg_s is not None else 'N/A'} s |",
        f"| Median Latency | {median_s if median_s is not None else 'N/A'} s |",
        "",
        "Answer Correctness is filled only after human annotation. Stateless memory ablation is diagnostic, not a resume headline.",
        "",
        f"Same-session stateless: {count_cell(memory['same_session']['stateless'])}",
        f"Cross-session stateless: {count_cell(memory['cross_session']['stateless'])}",
        "",
        "## Harness diagnostics",
        "",
        f"- provider_failure_count: {diag.get('provider_failure_count', 0)}",
        f"- agent_stage_failure_count: {diag.get('agent_stage_failure_count', 0)}",
        f"- draft_validation_failure_count: {diag.get('draft_validation_failure_count', 0)}",
        f"- draft_repair_attempt_count: {diag.get('draft_repair_attempt_count', 0)}",
        f"- draft_repair_success_count: {diag.get('draft_repair_success_count', 0)}",
        f"- evidence_insufficient_count: {diag.get('evidence_insufficient_count', 0)}",
        f"- total_tokens: {diag.get('total_tokens', 0)}",
        f"- estimated_cost: {diag.get('estimated_cost')}",
        "",
    ]
    return "\n".join(lines)


def annotation_markdown(annotation: dict[str, Any]) -> str:
    lines = [
        "# AgentEvidence E2E Baseline Human Annotation",
        "",
        "Fill `correctness` in the JSON with exactly one of: `correct`, `partial`, `incorrect`.",
        "",
    ]
    for case in annotation["cases"]:
        lines += [
            f"## {case['id']}",
            "",
            "Query:",
            case["query"],
            "",
            "Expected concepts:",
            ", ".join(case["expected_concepts"]),
            "",
            "Answer:",
            case["answer"] or "(empty)",
            "",
            "correctness: pending",
            "notes:",
            "",
        ]
    return "\n".join(lines)


def write_outputs(paths: dict[str, Path], report: dict[str, Any], annotation: dict[str, Any]) -> None:
    _write_json(paths["report_json"], report)
    paths["report_md"].write_text(report_markdown(report), encoding="utf-8")
    _write_json(paths["annotation_json"], annotation)
    paths["annotation_md"].write_text(annotation_markdown(annotation), encoding="utf-8")


def write_aggregated_report(paths: dict[str, Path]) -> int:
    if not paths["annotation_json"].is_file() or not paths["report_json"].is_file():
        raise FileNotFoundError("baseline report or human annotation JSON is missing; run the benchmark first")
    report = _read_json(paths["report_json"])
    annotation = _read_json(paths["annotation_json"])
    answerable_total = sum(1 for row in report.get("results", []) if row.get("answerable"))
    human = aggregate_human_annotations(annotation, answerable_total)
    updated = apply_human_metrics(report, human)
    _write_json(paths["report_json"], updated)
    paths["report_md"].write_text(report_markdown(updated), encoding="utf-8")
    print(json.dumps(human, ensure_ascii=False, indent=2))
    return 0 if human["status"] == "COMPLETE" else 0


def print_summary(report: dict[str, Any]) -> None:
    print("AgentEvidence E2E Baseline")
    print(f"run_variant: {report['run_variant']}")
    print("Answer Correctness: PENDING HUMAN REVIEW")
    metrics = report["metrics"]
    print(f"Single-doc Source Hit: {ratio_cell(metrics['single_document_source_hit'])}")
    print(f"Cross-doc All-Source Hit: {ratio_cell(metrics['cross_document_all_source_hit'])}")
    print(f"Avg Latency ms: {metrics['latency']['avg_latency_ms']}")
    diagnostics = report.get("diagnostics") or {}
    print(f"provider_failure_count: {diagnostics.get('provider_failure_count', 0)}")
    print(f"draft_validation_failure_count: {diagnostics.get('draft_validation_failure_count', 0)}")
    print(f"evidence_insufficient_count: {diagnostics.get('evidence_insufficient_count', 0)}")


def _flatten_traces(results: list[dict[str, Any]]):
    from app.research_harness.harness import LlmCallTrace

    traces = []
    for row in results:
        for payload in row.get("llm_traces") or []:
            traces.append(LlmCallTrace(**{key: payload[key] for key in LlmCallTrace.__dataclass_fields__ if key in payload}))
    return traces


def _sum_costs(results: list[dict[str, Any]]) -> float | None:
    costs = [row.get("estimated_cost") for row in results if row.get("estimated_cost") is not None]
    return round(sum(costs), 8) if costs else None


def ratio_cell(payload: dict[str, Any]) -> str:
    if not payload or payload.get("total") in {0, None}:
        return "N/A"
    return f"{payload['hits']}/{payload['total']} ({percent(payload['rate'])})"


def count_cell(payload: dict[str, Any]) -> str:
    if not payload or payload.get("total") in {0, None}:
        return "N/A"
    return f"{payload['hits']}/{payload['total']}"


def percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def _rate(values) -> float:
    values = list(values)
    return round(sum(bool(value) for value in values) / len(values), 6) if values else 0.0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
