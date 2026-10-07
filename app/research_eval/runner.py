from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.bootstrap import create_schema
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.models.entities import ChatMessage, ChatSession, ResearchLongTermMemory, UserAccount
from app.services.knowledge import KnowledgeService
from app.services.memory import RedisShortTermMemoryStore
from app.services.research_corpus import ResearchCorpusLoader
from app.services.research_memory import ConversationContext, ResearchMemoryService
from app.services.research_runtime import ResearchEventDrivenRuntime
from scripts.demo_research_draft import DemoEvidenceVerifierClient, DemoGroundedDraftClient
from scripts.demo_task_analyzer import DemoMockAiClient


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = Path(__file__).with_name("agentevidence-small-benchmark.json")
DEFAULT_JSON_OUTPUT = ROOT / "artifacts" / "results" / "agentevidence-small-benchmark-results.json"
DEFAULT_MARKDOWN_OUTPUT = ROOT / "artifacts" / "results" / "agentevidence-small-benchmark-report.md"


class StatelessEvaluationMemory:
    """Evaluation-only ablation that deliberately supplies no prior memory."""

    def build_context(self, user_id, session_id, query):
        return ConversationContext(original_query=query, contextualized_query=query)

    def update(self, user_id, session_id, turn_id, query, result):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the 20-case AgentEvidence internal benchmark.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN_OUTPUT))
    parser.add_argument("--keep-data", action="store_true", help="Keep live MySQL/Redis evaluation records.")
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset).resolve()
    output_path = Path(args.output).resolve()
    markdown_path = Path(args.markdown).resolve()
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset.get("cases", [])
    _validate_cases(cases)

    settings = get_settings().model_copy(update={"knowledge_vector_enabled": False})
    create_schema()
    with engine.connect() as connection:
        if connection.execute(text("SELECT 1")).scalar_one() != 1:
            raise RuntimeError("MySQL live verification failed")
    redis_store = RedisShortTermMemoryStore(settings)
    if redis_store.client is None or not redis_store.client.ping():
        raise RuntimeError("Redis live verification failed; benchmark refuses silent fallback")

    knowledge_engine = create_engine("sqlite://")
    Base.metadata.create_all(knowledge_engine)
    knowledge_db = sessionmaker(bind=knowledge_engine)()
    knowledge = KnowledgeService(knowledge_db, settings)
    ResearchCorpusLoader(ROOT / "data" / "research_corpus").bootstrap(knowledge)

    run_token = uuid.uuid4().hex[:10]
    live_db = SessionLocal()
    created_user_ids: list[int] = []
    redis_session_ids: set[str] = set()
    results = []
    errors = []
    started = time.perf_counter()
    try:
        for index, case in enumerate(cases, start=1):
            case_started = time.perf_counter()
            try:
                category = case["category"]
                if category in {"single_turn", "insufficient_evidence"}:
                    primary = _run_turn(case["query"], settings, knowledge, StatelessEvaluationMemory())
                    record = _score_primary(case, primary)
                else:
                    user, session_a, session_b = _live_case_identity(
                        live_db, run_token, index, cross_session=category == "cross_session_memory"
                    )
                    created_user_ids.append(user.id)
                    redis_session_ids.update(item for item in (session_a.public_id, session_b.public_id if session_b else "") if item)
                    baseline = _run_conversation(case, settings, knowledge, StatelessEvaluationMemory())
                    live_memory = ResearchMemoryService(live_db, settings, redis_store)
                    memory_run = _run_conversation(
                        case,
                        settings,
                        knowledge,
                        live_memory,
                        user_id=user.id,
                        session_a=session_a.public_id,
                        session_b=session_b.public_id if session_b else None,
                    )
                    record = _score_primary(case, memory_run["final"])
                    record["ablation"] = {
                        "stateless": _score_context(case, baseline["final"]),
                        "hierarchical_memory": _score_context(case, memory_run["final"]),
                    }
                record["latency_ms"] = round((time.perf_counter() - case_started) * 1000, 3)
                results.append(record)
            except Exception as exc:
                live_db.rollback()
                errors.append({"case_id": case.get("case_id", f"case-{index}"), "reason": f"{type(exc).__name__}: {exc}"})
    finally:
        knowledge_db.close()
        if not args.keep_data:
            _cleanup_live_data(live_db, created_user_ids, redis_store, redis_session_ids)
        live_db.close()

    failures = _collect_failures(results)
    metrics = summarize_results(results)
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_type": "agentevidence-deterministic-small-benchmark",
        "dataset": {
            "path": str(dataset_path),
            "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
            "cases": len(cases),
        },
        "execution": {
            "provider": "existing deterministic demo providers",
            "llm_judge": False,
            "redis": "LIVE VERIFIED",
            "mysql": "LIVE VERIFIED",
            "knowledge_corpus": "current provenance-backed local research corpus",
        },
        "metric_definitions": {
            "runtime_completion_rate": "cases producing FinalResearchResult / all cases",
            "source_hit_rate": "cases containing every expected source_id / cases with expected source_ids",
            "expected_concept_hit_rate": "cases whose retrieved evidence contains every expected concept / cases with expected concepts",
            "grounded_answer_rate": "cases with verifier.sufficient=true / all cases",
            "same_session_context_resolution_accuracy": "same-session cases containing every expected resolved term",
            "cross_session_memory_recall_accuracy": "cross-session cases containing every expected recalled term",
        },
        "metrics": metrics,
        "failures": failures,
        "errors": errors,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    _print_summary(report, output_path, markdown_path)
    return 0 if len(results) == 20 and not errors else 1


def _runtime(settings, knowledge, memory):
    return ResearchEventDrivenRuntime(
        TaskAnalyzerAgent(DemoMockAiClient()),
        ResearchAgent(
            knowledge,
            top_k=settings.research_retrieval_top_k,
            max_evidence_items=settings.research_max_evidence_items,
        ),
        ResearchDraftGenerator(DemoGroundedDraftClient()),
        EvidenceVerifier(DemoEvidenceVerifierClient()),
        settings,
        memory,
    )


def _run_turn(query, settings, knowledge, memory, user_id=None, session_id=""):
    run = _runtime(settings, knowledge, memory).run(query, user_id=user_id, session_id=session_id)
    context_artifact = run.board.latest_artifact("conversation_context")
    context = context_artifact.payload["value"] if context_artifact else None
    return {"run": run, "context": context}


def _run_conversation(case, settings, knowledge, memory, user_id=None, session_a="", session_b=None):
    if case["category"] == "same_session_multi_turn":
        first_query, final_query = case["turns"]
        _run_turn(first_query, settings, knowledge, memory, user_id, session_a)
        final = _run_turn(final_query, settings, knowledge, memory, user_id, session_a)
    else:
        first_query, final_query = case["session_a"], case["session_b"]
        _run_turn(first_query, settings, knowledge, memory, user_id, session_a)
        final = _run_turn(final_query, settings, knowledge, memory, user_id, session_b or "")
    return {"final": final}


def _score_primary(case, outcome):
    run = outcome["run"]
    final = run.final_result
    completed = final is not None
    source_ids = final.evidence_pool.source_ids() if final else []
    expected_sources = case.get("expected_source_ids", [])
    source_hit = all(source in source_ids for source in expected_sources) if expected_sources else None
    concept_hits = _concept_hits(
        case.get("expected_concepts", []),
        final.evidence_pool.items if final else [],
    )
    concept_hit = all(concept_hits.values()) if concept_hits else None
    sufficient = bool(final and final.verification.sufficient)
    conservative = bool(final and not sufficient and (
        not final.draft.claims
        or any(term in final.answer.casefold() for term in ("无法", "不足", "insufficient", "cannot"))
    ))
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "runtime_completed": completed,
        "expected_source_ids": expected_sources,
        "actual_source_ids": source_ids,
        "source_hit": source_hit,
        "expected_concept_hits": concept_hits,
        "expected_concepts_hit": concept_hit,
        "grounded": sufficient,
        "insufficient_behavior_pass": conservative if case.get("expected_insufficient") else None,
        "answer": final.answer if final else "",
        "research_task": final.task.model_dump(mode="json") if final else None,
        "evidence_pool": [
            {
                "evidence_id": item.evidence_id,
                "source_id": item.source_id,
                "source_title": item.source_title,
                "section": item.section,
                "symbol": item.metadata.get("symbol"),
                "file_path": item.metadata.get("file_path"),
                "content": item.canonical_content or item.content,
            }
            for item in (final.evidence_pool.items if final else [])
        ],
        "draft": final.draft.model_dump() if final else None,
        "verification": final.verification.model_dump() if final else None,
        "context": _context_snapshot(outcome.get("context")),
    }


def _score_context(case, outcome):
    context = outcome.get("context")
    text_value = ""
    if context:
        text_value = context.contextualized_query + "\n" + "\n".join(context.long_term_memories)
    terms = case.get("expected_resolved_terms", [])
    hits = {term: term.casefold() in text_value.casefold() for term in terms}
    run = outcome["run"]
    return {
        "resolved": bool(terms) and all(hits.values()),
        "term_hits": hits,
        "runtime_completed": run.final_result is not None,
        "context": _context_snapshot(context),
    }


def _concept_hits(expected_concepts, evidence_items):
    """Match exact concept text against evidence and safe provenance fields."""
    searchable_parts = []
    safe_metadata_fields = ("symbol", "section", "file_path", "qualified_symbol", "qualified_name")
    for item in evidence_items:
        searchable_parts.append(item.canonical_content or item.content)
        if item.section:
            searchable_parts.append(item.section)
        for field in safe_metadata_fields:
            value = item.metadata.get(field)
            if isinstance(value, str) and value:
                searchable_parts.append(value)
    searchable = "\n".join(searchable_parts).casefold()
    return {concept: concept.casefold() in searchable for concept in expected_concepts}


def _context_snapshot(context):
    if context is None:
        return None
    return {
        "original_query": context.original_query,
        "contextualized_query": context.contextualized_query,
        "recent_message_count": len(context.recent_messages),
        "session_summary": context.session_summary,
        "long_term_memories": context.long_term_memories,
    }


def _live_case_identity(db, token, index, cross_session):
    user = UserAccount(
        username=f"research-eval-{token}-{index}",
        display_name="Research Evaluation",
        password_hash="evaluation-only",
    )
    db.add(user)
    db.flush()
    session_a = ChatSession(
        public_id=f"research-eval-{token}-{index}-a",
        user_id=user.id,
        title="Research evaluation A",
    )
    db.add(session_a)
    session_b = None
    if cross_session:
        session_b = ChatSession(
            public_id=f"research-eval-{token}-{index}-b",
            user_id=user.id,
            title="Research evaluation B",
        )
        db.add(session_b)
    db.commit()
    return user, session_a, session_b


def _cleanup_live_data(db, user_ids, redis_store, session_ids):
    if user_ids:
        db.query(ChatMessage).filter(ChatMessage.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(ResearchLongTermMemory).filter(
            ResearchLongTermMemory.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(UserAccount).filter(UserAccount.id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
    if redis_store.client is not None:
        keys = []
        for session_id in session_ids:
            keys.extend((
                f"mindbridge:short-term-memory:{session_id}",
                f"mindbridge:research-session-summary:{session_id}",
            ))
        if keys:
            redis_store.client.delete(*keys)


def summarize_results(results):
    total = len(results)
    source_cases = [item for item in results if item["source_hit"] is not None]
    concept_cases = [item for item in results if item["expected_concepts_hit"] is not None]
    same = [item for item in results if item["category"] == "same_session_multi_turn"]
    cross = [item for item in results if item["category"] == "cross_session_memory"]
    return {
        "evaluated_cases": total,
        "runtime_completion_rate": _rate(item["runtime_completed"] for item in results),
        "source_hit_rate": _rate(item["source_hit"] for item in source_cases),
        "expected_concept_hit_rate": _rate(item["expected_concepts_hit"] for item in concept_cases),
        "grounded_answer_rate": _rate(item["grounded"] for item in results),
        "same_session_context_resolution_accuracy": _rate(
            item["ablation"]["hierarchical_memory"]["resolved"] for item in same
        ),
        "cross_session_memory_recall_accuracy": _rate(
            item["ablation"]["hierarchical_memory"]["resolved"] for item in cross
        ),
        "insufficient_evidence_accuracy": _rate(
            item["insufficient_behavior_pass"] for item in results
            if item["category"] == "insufficient_evidence"
        ),
        "ablation": {
            "same_session": {
                "stateless": _rate(item["ablation"]["stateless"]["resolved"] for item in same),
                "hierarchical_memory": _rate(
                    item["ablation"]["hierarchical_memory"]["resolved"] for item in same
                ),
            },
            "cross_session": {
                "stateless": _rate(item["ablation"]["stateless"]["resolved"] for item in cross),
                "hierarchical_memory": _rate(
                    item["ablation"]["hierarchical_memory"]["resolved"] for item in cross
                ),
            },
        },
    }


def _collect_failures(results):
    failures = []
    for item in results:
        reasons = []
        if not item["runtime_completed"]:
            reasons.append("runtime did not produce FinalResearchResult")
        if item["source_hit"] is False:
            reasons.append("missing one or more expected source_ids")
        if item["expected_concepts_hit"] is False:
            missing = [name for name, hit in item["expected_concept_hits"].items() if not hit]
            reasons.append("missing expected concepts: " + ", ".join(missing))
        if item["category"] not in {"insufficient_evidence"} and not item["grounded"]:
            reasons.append("verifier.sufficient=false")
        if item["category"] == "insufficient_evidence" and not item["insufficient_behavior_pass"]:
            reasons.append("answer was not conservative under insufficient evidence")
        if "ablation" in item and not item["ablation"]["hierarchical_memory"]["resolved"]:
            reasons.append("hierarchical memory did not resolve all expected terms")
        if reasons:
            failures.append({"case_id": item["case_id"], "reason": "; ".join(reasons)})
    return failures


def _markdown_report(report):
    metrics = report["metrics"]
    lines = [
        "# AgentEvidence Small Benchmark",
        "",
        f"- Cases: {metrics['evaluated_cases']}/20",
        f"- Runtime Completion Rate: {_percent(metrics['runtime_completion_rate'])}",
        f"- Source Hit Rate: {_percent(metrics['source_hit_rate'])}",
        f"- Expected Concept Hit Rate: {_percent(metrics['expected_concept_hit_rate'])}",
        f"- Grounded Answer Rate: {_percent(metrics['grounded_answer_rate'])}",
        f"- Same-session Context Resolution Accuracy: {_percent(metrics['same_session_context_resolution_accuracy'])}",
        f"- Cross-session Memory Recall Accuracy: {_percent(metrics['cross_session_memory_recall_accuracy'])}",
        f"- Insufficient-evidence Accuracy: {_percent(metrics['insufficient_evidence_accuracy'])}",
        "",
        "## Stateless vs Hierarchical Memory",
        "",
        "| Scope | Stateless | Hierarchical memory |",
        "|---|---:|---:|",
        f"| Same session | {_percent(metrics['ablation']['same_session']['stateless'])} | {_percent(metrics['ablation']['same_session']['hierarchical_memory'])} |",
        f"| Cross session | {_percent(metrics['ablation']['cross_session']['stateless'])} | {_percent(metrics['ablation']['cross_session']['hierarchical_memory'])} |",
        "",
        "## Failures",
        "",
    ]
    if report["failures"]:
        lines.extend(f"- `{item['case_id']}`: {item['reason']}" for item in report["failures"])
    else:
        lines.append("- None")
    if report["errors"]:
        lines.extend(("", "## Execution Errors", ""))
        lines.extend(f"- `{item['case_id']}`: {item['reason']}" for item in report["errors"])
    lines.extend((
        "",
        "## Interpretation",
        "",
        "`verifier.sufficient` is used only as the system's internal grounded-answer signal. "
        "No LLM judge or claim of independent factual correctness is made.",
        "",
    ))
    return "\n".join(lines)


def _print_summary(report, output_path, markdown_path):
    metrics = report["metrics"]
    print("AgentEvidence Small Benchmark")
    print(f"Cases: {metrics['evaluated_cases']}/20")
    for name in (
        "runtime_completion_rate",
        "source_hit_rate",
        "grounded_answer_rate",
        "same_session_context_resolution_accuracy",
        "cross_session_memory_recall_accuracy",
    ):
        print(f"{name}: {_percent(metrics[name])}")
    print(f"Failures: {len(report['failures'])}")
    print(f"Errors: {len(report['errors'])}")
    print(f"JSON: {output_path}")
    print(f"Markdown: {markdown_path}")


def _validate_cases(cases):
    if len(cases) != 20:
        raise ValueError(f"benchmark must contain exactly 20 cases, found {len(cases)}")
    ids = [case.get("case_id") for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("case_id values must be unique")
    expected_counts = {
        "single_turn": 8,
        "same_session_multi_turn": 6,
        "cross_session_memory": 4,
        "insufficient_evidence": 2,
    }
    actual = {name: sum(case.get("category") == name for case in cases) for name in expected_counts}
    if actual != expected_counts:
        raise ValueError(f"unexpected category counts: {actual}")


def _rate(values):
    items = list(values)
    return round(sum(bool(item) for item in items) / len(items), 6) if items else 0.0


def _percent(value):
    return f"{value:.2%}"


if __name__ == "__main__":
    raise SystemExit(main())
