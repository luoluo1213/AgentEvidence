from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.models.entities import ChatMessage, ChatSession, ResearchLongTermMemory, UserAccount
from app.services.ai import AiClient
from app.services.knowledge import KnowledgeService
from app.services.memory import RedisShortTermMemoryStore
from app.services.research_memory import ConversationContext, ResearchMemoryService
from app.services.research_runtime import ResearchEventDrivenRuntime
from app.services.source_ingestion import ResearchSourceIngestionService, SourceIngestionRequest


DATASET = ROOT / "app" / "research_eval" / "research-e2e-benchmark.json"
RESULTS_DIR = ROOT / "artifacts" / "results"
RESULTS_JSON = RESULTS_DIR / "research-e2e-results.json"
ABLATION_JSON = RESULTS_DIR / "research-e2e-memory-ablation.json"
ANNOTATION_JSON = RESULTS_DIR / "research-e2e-human-annotation.json"
ANNOTATION_MD = RESULTS_DIR / "research-e2e-human-annotation.md"
REPORT_MD = RESULTS_DIR / "research-e2e-report.md"
FALLBACK_ANSWER = "无法基于当前证据可靠生成回答"


class ObservedAiClient:
    """Transparent production-client observer; it never substitutes a response."""

    def __init__(self, settings):
        self.client = AiClient(settings)
        self.calls: list[dict[str, Any]] = []

    def complete(self, messages):
        started = time.perf_counter()
        record = {"latency_ms": None, "success": False, "error_type": None,
                  "input_tokens": None, "output_tokens": None, "total_tokens": None}
        try:
            value = self.client.complete(messages)
            record["success"] = True
            return value
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            raise
        finally:
            record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
            self.calls.append(record)


class StatelessEvaluationMemory:
    def build_context(self, user_id, session_id, query):
        return ConversationContext(original_query=query, contextualized_query=query)

    def update(self, user_id, session_id, turn_id, query, result):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the real-provider AgentEvidence E2E benchmark.")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--aggregate-human-annotations", action="store_true")
    parser.add_argument("--keep-data", action="store_true")
    args = parser.parse_args(argv)
    if args.aggregate_human_annotations:
        aggregate = aggregate_human_annotations(_read_json(ANNOTATION_JSON))
        print(json.dumps(aggregate, ensure_ascii=False, indent=2))
        return 0

    dataset_path = Path(args.dataset).resolve()
    dataset = _read_json(dataset_path)
    validate_dataset(dataset)
    settings = get_settings()
    if settings.ai_provider.lower() not in {"openai", "ollama"}:
        raise RuntimeError("Step 12 requires a real configured provider, not mock")

    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
    redis_store = RedisShortTermMemoryStore(settings)
    if redis_store.client is None or not redis_store.client.ping():
        raise RuntimeError("live Redis is required for Step 12 memory evaluation")

    knowledge_engine = create_engine("sqlite://")
    Base.metadata.create_all(knowledge_engine)
    knowledge_db = sessionmaker(bind=knowledge_engine)()
    results: list[dict] = []
    ablations: list[dict] = []
    errors: list[dict] = []
    live_db = SessionLocal()
    created_users: list[int] = []
    redis_sessions: set[str] = set()
    run_id = uuid.uuid4().hex[:10]
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="research-e2e-ingestion-", ignore_cleanup_errors=True) as directory:
            # Isolate benchmark vectors while keeping the production embedding,
            # fusion, reranking, top-k, and candidate-k configuration unchanged.
            settings = settings.model_copy(update={
                "chroma_persist_dir": str(Path(directory) / "chroma"),
                "chroma_snapshot_dir": str(Path(directory) / "snapshots"),
                "chroma_collection_name": f"research_e2e_{run_id}",
            })
            knowledge = KnowledgeService(knowledge_db, settings)
            ingestion = ResearchSourceIngestionService(knowledge, Path(directory))
            corpus = ingest_documents(ingestion, dataset["documents"])
            for index, case in enumerate(dataset["cases"], start=1):
                print(f"[{index:02d}/{len(dataset['cases'])}] {case['case_id']}", flush=True)
                case_started = time.perf_counter()
                try:
                    if case["case_type"] in {"same_session", "cross_session"}:
                        user, session_a, session_b = create_case_identity(
                            live_db, run_id, index, case["case_type"] == "cross_session"
                        )
                        created_users.append(user.id)
                        redis_sessions.update(x for x in (session_a.public_id, session_b.public_id if session_b else "") if x)
                        baseline = run_context_case(case, settings, knowledge, StatelessEvaluationMemory())
                        memory = ResearchMemoryService(live_db, settings, redis_store)
                        hierarchical = run_context_case(
                            case, settings, knowledge, memory, user.id,
                            session_a.public_id, session_b.public_id if session_b else None,
                        )
                        record = result_record(case, hierarchical["final"], case_started)
                        ablation = {
                            "case_id": case["case_id"], "case_type": case["case_type"],
                            "stateless": context_score(case, baseline["final"]),
                            "hierarchical_memory": context_score(case, hierarchical["final"]),
                        }
                        record["memory_ablation"] = ablation
                        ablations.append(ablation)
                    else:
                        outcome = run_turn(case["query"], settings, knowledge, StatelessEvaluationMemory())
                        record = result_record(case, outcome, case_started)
                    results.append(record)
                except Exception as exc:
                    live_db.rollback()
                    errors.append({"case_id": case["case_id"], "error_type": type(exc).__name__, "reason": sanitize(str(exc))})
    finally:
        knowledge_db.close()
        knowledge_engine.dispose()
        if not args.keep_data:
            cleanup(live_db, created_users, redis_store, redis_sessions)
        live_db.close()

    report = build_report(dataset_path, dataset, corpus, settings, results, errors, started)
    annotation = build_annotation(dataset, results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(RESULTS_JSON, report)
    _write_json(ABLATION_JSON, {"schema_version": 1, "cases": ablations, "metrics": ablation_metrics(ablations)})
    _write_json(ANNOTATION_JSON, annotation)
    ANNOTATION_MD.write_text(annotation_markdown(annotation), encoding="utf-8")
    REPORT_MD.write_text(report_markdown(report), encoding="utf-8")
    print_summary(report)
    return 0 if len(results) == len(dataset["cases"]) and not errors else 1


def build_runtime(settings, knowledge, memory, observer):
    return ResearchEventDrivenRuntime(
        TaskAnalyzerAgent(observer),
        ResearchAgent(knowledge, top_k=settings.research_retrieval_top_k,
                      max_evidence_items=settings.research_max_evidence_items),
        ResearchDraftGenerator(observer), EvidenceVerifier(observer), settings, memory,
    )


def run_turn(query, settings, knowledge, memory, user_id=None, session_id=""):
    observer = ObservedAiClient(settings)
    started = time.perf_counter()
    run = build_runtime(settings, knowledge, memory, observer).run(query, user_id=user_id, session_id=session_id)
    context_artifact = run.board.latest_artifact("conversation_context")
    context = context_artifact.payload.get("value") if context_artifact else None
    return {"run": run, "context": context, "calls": observer.calls,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


def run_context_case(case, settings, knowledge, memory, user_id=None, session_a="", session_b=None):
    prior_calls = []
    prior_latency = 0.0
    for query in case["prior_turns"]:
        prior = run_turn(query, settings, knowledge, memory, user_id, session_a)
        prior_calls.extend(prior["calls"])
        prior_latency += prior["latency_ms"]
    target_session = session_b if case["case_type"] == "cross_session" else session_a
    final = run_turn(case["query"], settings, knowledge, memory, user_id, target_session or "")
    final["conversation_llm_calls"] = prior_calls + final["calls"]
    final["conversation_latency_ms"] = round(prior_latency + final["latency_ms"], 3)
    return {"final": final}


def result_record(case, outcome, case_started):
    run = outcome["run"]
    final = run.final_result
    evidence = list(final.evidence_pool.items[:5]) if final else []
    anchor_hits = anchor_match(case.get("expected_evidence_anchors", []), evidence)
    actual_sources = list(dict.fromkeys(item.source_id for item in evidence))
    source_hit = all(source in actual_sources for source in case.get("expected_source_ids", []))
    evidence_hit = source_hit and all(anchor_hits.values()) if anchor_hits else source_hit
    context = context_snapshot(outcome.get("context"))
    context_pass = context_resolution(case, context)
    conservative = is_conservative(final)
    observed_calls = outcome.get("conversation_llm_calls", outcome["calls"])
    return {
        "case_id": case["case_id"], "case_type": case["case_type"], "query": case["query"],
        "task_id": final.task.task_id if final else None,
        "runtime_success": final is not None,
        "provider_failure": any(not call["success"] for call in observed_calls),
        "latency_ms": round((time.perf_counter() - case_started) * 1000, 3),
        "llm_calls": len(observed_calls), "llm_call_metrics": observed_calls,
        "retrieved_evidence_count": len(final.evidence_pool.items) if final else 0,
        "runtime_event_count": len(run.board.events),
        "expected_source_ids": case.get("expected_source_ids", []), "actual_top5_source_ids": actual_sources,
        "evidence_anchor_hits": anchor_hits, "evidence_hit_at_5": evidence_hit,
        "context_resolution": context_pass if case.get("requires_context_resolution") else None,
        "cross_session_memory_recall": context_pass if case["case_type"] == "cross_session" else None,
        "insufficient_handling": conservative if case.get("expected_insufficient") else None,
        "conversation_context": context,
        "final_answer": final.answer if final else "",
        "claims": [claim.model_dump() for claim in final.draft.claims] if final else [],
        "retrieved_evidence": [evidence_record(item) for item in (final.evidence_pool.items if final else [])],
        "verification": final.verification.model_dump() if final else None,
    }


def evidence_record(item):
    page = item.metadata.get("page")
    if page is None and item.section and item.section.startswith("Page "):
        try:
            page = int(item.section.split()[-1])
        except ValueError:
            page = None
    return {"evidence_id": item.evidence_id, "source_id": item.source_id,
            "document_title": item.metadata.get("document_title") or item.metadata.get("source_title") or item.source_title,
            "page": page, "section": item.section, "text": item.canonical_content or item.content}


def anchor_match(anchors, evidence):
    text_value = "\n".join((item.canonical_content or item.content) for item in evidence).casefold()
    return {anchor: normalize(anchor) in normalize(text_value) for anchor in anchors}


def context_snapshot(context):
    if context is None:
        return None
    return {"original_query": context.original_query, "contextualized_query": context.contextualized_query,
            "recent_messages": [message.model_dump() for message in context.recent_messages],
            "session_summary": context.session_summary, "long_term_memories": context.long_term_memories}


def context_resolution(case, context):
    if not context:
        return False
    searchable = "\n".join([context.get("contextualized_query", ""), context.get("session_summary", ""),
                             *context.get("long_term_memories", []),
                             *(m.get("content", "") for m in context.get("recent_messages", []))]).casefold()
    expected = str(case.get("expected_referent") or case.get("expected_memory_fact") or "").casefold()
    terms = [term for term in re.split(r"\s*(?:与|和|、|/|and)\s*", expected) if term]
    return bool(terms) and all(term in searchable for term in terms)


def context_score(case, outcome):
    context = context_snapshot(outcome.get("context"))
    return {"runtime_success": outcome["run"].final_result is not None,
            "resolved": context_resolution(case, context), "context": context}


def is_conservative(final):
    if final is None:
        return False
    lowered = final.answer.casefold()
    marker = any(x in lowered for x in ("证据不足", "信息不足", "无法基于", "没有提供", "insufficient", "does not provide"))
    return marker and not final.draft.claims


def build_report(dataset_path, dataset, corpus, settings, results, errors, started):
    relevant = [row for row in results if row["evidence_anchor_hits"] or row["expected_source_ids"]]
    same = [row for row in results if row["case_type"] == "same_session"]
    cross = [row for row in results if row["case_type"] == "cross_session"]
    insufficient = [row for row in results if row["case_type"] == "insufficient"]
    successful = [row for row in results if row["runtime_success"]]
    verifier = Counter(
        "sufficient" if row.get("verification", {}).get("sufficient") else "insufficient"
        for row in successful
    )
    return {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {"path": str(dataset_path), "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                    "case_count": len(dataset["cases"]), "distribution": dict(Counter(x["case_type"] for x in dataset["cases"])),
                    "documents": corpus},
        "execution": {"provider": settings.ai_provider, "model": provider_model(settings),
                      "real_ai_client": True, "mock_fallback": False,
                      "redis": "LIVE VERIFIED", "mysql": "LIVE VERIFIED", "retrieval": "production hybrid"},
        "automatic_metrics": {
            "runtime_success": rate(row["runtime_success"] for row in results),
            "provider_failure_rate": rate(row["provider_failure"] for row in results),
            "provider_failure_count": sum(row["provider_failure"] for row in results),
            "evidence_hit_at_5": rate(row["evidence_hit_at_5"] for row in relevant),
            "same_session_context_resolution": rate(row["context_resolution"] for row in same),
            "cross_session_memory_recall": rate(row["cross_session_memory_recall"] for row in cross),
            "insufficient_evidence_handling": rate(row["insufficient_handling"] for row in insufficient),
            "average_total_latency_ms": average(row["latency_ms"] for row in results),
            "average_llm_input_tokens": None, "average_llm_output_tokens": None, "average_total_tokens": None,
            "average_retrieved_evidence_count": average(row["retrieved_evidence_count"] for row in results),
            "average_runtime_event_count": average(row["runtime_event_count"] for row in results),
            "verifier_summary": dict(verifier),
        },
        "pending_human_metrics": {"fully_correct_answer_rate": None, "partial_answer_rate": None,
                                  "incorrect_answer_rate": None, "supported_claim_rate": None,
                                  "verifier_human_agreement": None, "status": "PENDING HUMAN REVIEW"},
        "memory_ablation": ablation_metrics([row["memory_ablation"] for row in results if "memory_ablation" in row]),
        "extracted_factual_claims": sum(len(row["claims"]) for row in results),
        "failures": failure_records(results, errors), "errors": errors,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3), "results": results,
    }


def build_annotation(dataset, results):
    by_id = {row["case_id"]: row for row in results}
    cases = []
    for case in dataset["cases"]:
        result = by_id.get(case["case_id"], {})
        claims = [{**claim, "human_supported": None, "human_note": ""} for claim in result.get("claims", [])]
        cases.append({"case_id": case["case_id"], "case_type": case["case_type"], "query": case["query"],
                      "reference_answer_points": case["reference_answer_points"],
                      "final_answer": result.get("final_answer", ""),
                      "retrieved_evidence": result.get("retrieved_evidence", []), "claims": claims,
                      "evidence_verifier": result.get("verification"),
                      "answer_correctness": None, "human_note": "", "context_resolution": None,
                      "cross_session_memory_recall": None, "insufficient_handling": None})
    return {"schema_version": 1, "status": "PENDING HUMAN REVIEW", "cases": cases}


def aggregate_human_annotations(annotation):
    cases = annotation.get("cases", [])
    labels = Counter(case.get("answer_correctness") for case in cases if case.get("answer_correctness") in {"FULL", "PARTIAL", "INCORRECT"})
    claims = [claim for case in cases for claim in case.get("claims", []) if claim.get("human_supported") is not None]
    supported = sum(claim.get("human_supported") is True for claim in claims)
    comparisons = Counter()
    for case in cases:
        label = case.get("answer_correctness")
        verifier = (case.get("evidence_verifier") or {}).get("sufficient")
        if label in {"FULL", "PARTIAL", "INCORRECT"} and verifier is not None:
            human_supported = label in {"FULL", "PARTIAL"}
            comparisons[f"verifier_{'sufficient' if verifier else 'insufficient'}__human_{'supported' if human_supported else 'unsupported'}"] += 1
    completed = sum(labels.values())
    agreement = sum(value for key, value in comparisons.items() if key in {
        "verifier_sufficient__human_supported", "verifier_insufficient__human_unsupported"})
    return {"annotation_status": "COMPLETE" if completed == len(cases) else "PENDING",
            "annotated_answers": completed, "pending_answers": len(cases) - completed,
            "answer_correctness": {name: {"count": labels[name], "rate": labels[name] / completed if completed else None}
                                   for name in ("FULL", "PARTIAL", "INCORRECT")},
            "supported_claim_rate": supported / len(claims) if claims else None,
            "annotated_claims": len(claims), "verifier_confusion": dict(comparisons),
            "verifier_agreement_rate": agreement / sum(comparisons.values()) if comparisons else None,
            "same_session_context_pass_rate": optional_rate(cases, "context_resolution", "same_session"),
            "cross_session_memory_recall_rate": optional_rate(cases, "cross_session_memory_recall", "cross_session"),
            "insufficient_handling_pass_rate": optional_rate(cases, "insufficient_handling", "insufficient")}


def annotation_markdown(annotation):
    lines = ["# AgentEvidence E2E Human Annotation", "", "Status: **PENDING HUMAN REVIEW**", ""]
    for case in annotation["cases"]:
        lines += [f"## Case: {case['case_id']}", "", "Query:", case["query"], "", "Reference Answer Points:"]
        lines += [f"- {point}" for point in case["reference_answer_points"]]
        lines += ["", "Final Answer:", case["final_answer"] or "(runtime produced no answer)", "", "Retrieved Evidence:"]
        for index, item in enumerate(case["retrieved_evidence"], start=1):
            lines += [f"{index}. [{item['source_id']} / page {item['page']} / {item['section']}]", f"   {item['text']}"]
        if not case["retrieved_evidence"]:
            lines.append("(none)")
        lines += ["", "Claims:", ""]
        for index, claim in enumerate(case["claims"], start=1):
            lines += [f"Claim {index}:", claim["text"], f"Evidence: {', '.join(claim['evidence_ids'])}",
                      "[ ] Supported", "[ ] Unsupported", ""]
        lines += ["Answer Correctness:", "[ ] FULL", "[ ] PARTIAL", "[ ] INCORRECT", "",
                  "Context Resolution:", "[ ] PASS", "[ ] FAIL", "[ ] N/A", "",
                  "Cross-session Memory Recall:", "[ ] PASS", "[ ] FAIL", "[ ] N/A", "",
                  "Insufficient-evidence Handling:", "[ ] PASS", "[ ] FAIL", "[ ] N/A", "",
                  "Human Notes:", "", "--------------------------------------------------", ""]
    return "\n".join(lines)


def report_markdown(report):
    m = report["automatic_metrics"]
    a = report["memory_ablation"]
    lines = ["# AgentEvidence Real-Provider E2E Evaluation", "",
             f"Provider/model: `{report['execution']['provider']} / {report['execution']['model']}`", "",
             "## Automatic metrics", "",
             f"- Runtime Success: {percent(m['runtime_success'])}", f"- Evidence Hit@5: {percent(m['evidence_hit_at_5'])}",
             f"- Provider failure cases: {m.get('provider_failure_count', 0)} ({percent(m.get('provider_failure_rate', 0.0))})",
             f"- Same-session Context Resolution: {percent(m['same_session_context_resolution'])}",
             f"- Cross-session Memory Recall: {percent(m['cross_session_memory_recall'])}",
             f"- Insufficient-evidence Handling: {percent(m['insufficient_evidence_handling'])}",
             f"- Average latency: {m['average_total_latency_ms']} ms", f"- Average retrieved evidence: {m['average_retrieved_evidence_count']}",
             f"- Average runtime events: {m['average_runtime_event_count']}", "- Token usage: unavailable from the current AiClient response interface", "",
             "## Memory ablation", "", "| Scope | Stateless | Hierarchical |", "|---|---:|---:|",
             f"| Same session | {percent(a['same_session']['stateless'])} | {percent(a['same_session']['hierarchical_memory'])} |",
             f"| Cross session | {percent(a['cross_session']['stateless'])} | {percent(a['cross_session']['hierarchical_memory'])} |", "",
             "## Internal EvidenceVerifier", "", f"- {json.dumps(m['verifier_summary'], ensure_ascii=False)}", "",
             "## Pending human metrics", "", "- Answer Correctness: **PENDING HUMAN REVIEW**",
             "- Supported Claim Rate: **PENDING HUMAN REVIEW**", "- Verifier-vs-human agreement: **PENDING HUMAN REVIEW**", "",
             "## Failures", ""]
    lines += [f"- `{x['case_id']}`: {x['reason']}" for x in report["failures"]] or ["- None"]
    return "\n".join(lines) + "\n"


def validate_dataset(dataset):
    cases = dataset.get("cases", [])
    expected = {"single_turn": 8, "cross_document": 4, "same_session": 4, "cross_session": 2, "insufficient": 2}
    actual = Counter(case.get("case_type") for case in cases)
    if len(cases) != 20 or dict(actual) != expected:
        raise ValueError(f"invalid case distribution: {dict(actual)}")
    required = {"case_id", "case_type", "query", "expected_source_ids", "expected_evidence_anchors",
                "reference_answer_points", "expected_insufficient", "requires_context_resolution"}
    for case in cases:
        missing = required - case.keys()
        if missing or not case["reference_answer_points"]:
            raise ValueError(f"invalid benchmark case {case.get('case_id')}: {sorted(missing)}")
        if case["case_type"] in {"same_session", "cross_session"} and not case.get("prior_turns"):
            raise ValueError(f"context case lacks prior_turns: {case['case_id']}")


def ingest_documents(service, documents):
    rows = []
    for document in documents:
        path = (ROOT / document["location"]).resolve()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != document["sha256"]:
            raise ValueError(f"document digest mismatch: {document['source_id']}")
        result = service.ingest(SourceIngestionRequest(source_type="paper", source_id=document["source_id"], location=str(path)))
        if result.status not in {"completed", "unchanged"} or result.errors:
            raise RuntimeError(f"ingestion failed: {document['source_id']}")
        rows.append({"source_id": document["source_id"], "title": document["title"], "sha256": digest,
                     "chunks": result.chunks_total})
    return rows


def create_case_identity(db, token, index, cross_session):
    user = UserAccount(username=f"e2e-{token}-{index}", display_name="E2E Evaluation", password_hash="evaluation-only")
    db.add(user); db.flush()
    first = ChatSession(public_id=f"e2e-{token}-{index}-a", user_id=user.id, title="E2E A")
    db.add(first)
    second = ChatSession(public_id=f"e2e-{token}-{index}-b", user_id=user.id, title="E2E B") if cross_session else None
    if second: db.add(second)
    db.commit()
    return user, first, second


def cleanup(db, user_ids, redis_store, session_ids):
    if user_ids:
        db.query(ChatMessage).filter(ChatMessage.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(ResearchLongTermMemory).filter(ResearchLongTermMemory.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(UserAccount).filter(UserAccount.id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
    if redis_store.client:
        keys = [key for session in session_ids for key in (f"mindbridge:short-term-memory:{session}",
                                                             f"mindbridge:research-session-summary:{session}")]
        if keys: redis_store.client.delete(*keys)


def ablation_metrics(rows):
    same = [row for row in rows if row["case_type"] == "same_session"]
    cross = [row for row in rows if row["case_type"] == "cross_session"]
    return {"same_session": {"stateless": rate(row["stateless"]["resolved"] for row in same),
                             "hierarchical_memory": rate(row["hierarchical_memory"]["resolved"] for row in same)},
            "cross_session": {"stateless": rate(row["stateless"]["resolved"] for row in cross),
                              "hierarchical_memory": rate(row["hierarchical_memory"]["resolved"] for row in cross)}}


def failure_records(results, errors):
    failures = list(errors)
    for row in results:
        reasons = []
        if not row["runtime_success"]: reasons.append("runtime/provider did not produce FinalResearchResult")
        if row["provider_failure"]: reasons.append("one or more real provider calls failed")
        if not row["evidence_hit_at_5"] and row["case_type"] != "insufficient": reasons.append("verified evidence not found in top 5")
        if row["case_type"] != "insufficient" and not row["claims"] and row["final_answer"] == FALLBACK_ANSWER:
            reasons.append("production Draft returned the conservative fallback with no grounded claims")
        if row["context_resolution"] is False: reasons.append("context referent not resolved")
        if row["insufficient_handling"] is False: reasons.append("insufficient-evidence answer was not conservative")
        if reasons: failures.append({"case_id": row["case_id"], "reason": "; ".join(reasons)})
    return failures


def optional_rate(cases, field, case_type):
    values = [case[field] for case in cases if case.get("case_type") == case_type and case.get(field) is not None]
    return rate(values) if values else None


def rate(values):
    values = list(values)
    return round(sum(value is True for value in values) / len(values), 6) if values else 0.0


def average(values):
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 3) if values else None


def normalize(value):
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def provider_model(settings):
    return settings.openai_model if settings.ai_provider.lower() == "openai" else settings.ollama_model


def sanitize(value):
    text_value = re.sub(r"(?i)(bearer\s+)[^\s]+", r"\1[REDACTED]", str(value))
    text_value = re.sub(r"(?i)(api[_-]?key[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text_value)
    text_value = re.sub(r"(?i)reasoning_content\s*[:=]\s*[^,}\n]+", "reasoning_content=[REDACTED]", text_value)
    return text_value[:1000]


def percent(value):
    return "N/A" if value is None else f"{value:.2%}"


def print_summary(report):
    print("AgentEvidence Real LLM E2E Benchmark")
    print(f"Provider/model: {report['execution']['provider']} / {report['execution']['model']}")
    for key, value in report["automatic_metrics"].items():
        if isinstance(value, (int, float)) or value is None: print(f"{key}: {value}")
    print(f"Failures: {len(report['failures'])}")
    print("Answer Correctness: PENDING HUMAN REVIEW")
    print("Supported Claim Rate: PENDING HUMAN REVIEW")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
