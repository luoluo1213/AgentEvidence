from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "artifacts" / "results" / "agentevidence-step9-baseline-results.json"
DEFAULT_JSON = ROOT / "artifacts" / "results" / "agentevidence-failure-diagnosis.json"
DEFAULT_MARKDOWN = ROOT / "artifacts" / "results" / "agentevidence-failure-diagnosis.md"

CATEGORY_NAMES = {
    "A": "Retrieval miss",
    "B": "Evidence present, synthesis miss",
    "C": "Draft supported, verifier rejection",
    "D": "Evaluation checker mismatch",
    "E": "Genuine insufficient evidence",
    "F": "Other",
}

# Human-reviewed attribution after inspecting the exact evidence, draft and
# verification records. This belongs to evaluation diagnostics, not production.
ATTRIBUTION = {
    "single-react-mechanism": ("B", None, "Mechanism chunks from the expected source contain all expected concepts, but Draft is the empty conservative fallback."),
    "single-react-feedback": ("B", None, "Feedback evidence from the expected source is present, but Draft contains no claims."),
    "single-reflexion-mechanism": ("B", None, "The expected method section contains reflection, feedback and memory, but Draft is empty."),
    "single-reflexion-components": ("B", None, "Actor/Evaluator/Self-Reflection evidence is present, but Draft contains no claims."),
    "single-mini-architecture": ("A", "B", "The mini-SWE source is hit, but no history/code-loop chunk is retrieved; the remaining architecture evidence is also not synthesized."),
    "single-mini-action-execution": ("D", None, "LocalEnvironment.execute is present as evidence symbol metadata and in the supported Draft, while the checker scans evidence body text only."),
    "session-mini-action": ("A", None, "Context resolves the entity, but top evidence contains README/general chunks rather than DefaultAgent.execute_actions."),
    "session-react-observation": ("B", None, "Expected method chunks contain observation and reasoning, but Draft is empty."),
    "session-reflexion-memory": ("B", None, "Expected reflection/memory evidence is present, but Draft is empty."),
    "session-mini-environment": ("A", "B", "DefaultAgent.execute_actions is retrieved, but LocalEnvironment.execute/returncode evidence is absent; the answer mentions them without claim-level citations."),
    "cross-mini-agent-loop": ("A", None, "The source is hit, but retrieved README motivation chunks do not cover the requested agent-loop mechanism."),
    "cross-mini-actions": ("A", None, "The source is hit, but DefaultAgent.execute_actions is not among retrieved chunks."),
    "cross-mini-history": ("A", None, "The source is hit, but DefaultAgent.add_messages is not among retrieved chunks."),
    "cross-mini-environment": ("A", None, "The source is hit, but LocalEnvironment.execute is not among retrieved chunks."),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Attribute failures in the AgentEvidence small benchmark.")
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--output", default=str(DEFAULT_JSON))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args(argv)

    results_path = Path(args.results).resolve()
    report = json.loads(results_path.read_text(encoding="utf-8"))
    failed_ids = [item["case_id"] for item in report["failures"]]
    if set(failed_ids) != set(ATTRIBUTION):
        raise ValueError("benchmark failures changed; attribution requires a fresh human review")
    by_id = {item["case_id"]: item for item in report["results"]}
    rows = [_diagnose(by_id[case_id], *ATTRIBUTION[case_id]) for case_id in failed_ids]
    counts = Counter(row["primary_failure_category"][0] for row in rows)
    aggregate = {CATEGORY_NAMES[key]: counts.get(key, 0) for key in CATEGORY_NAMES}
    fixes = _fixes()
    diagnosis = {
        "schema_version": 1,
        "source_results": str(results_path),
        "failed_cases": len(rows),
        "aggregate_counts": aggregate,
        "diagnoses": rows,
        "top_fixes": fixes,
        "constraints": {
            "production_behavior_changed": False,
            "benchmark_expectations_changed": False,
            "verifier_thresholds_changed": False,
        },
    }
    output_path = Path(args.output).resolve()
    markdown_path = Path(args.markdown).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(diagnosis), encoding="utf-8")
    print("AgentEvidence Failure Attribution")
    for name, count in aggregate.items():
        print(f"{name}: {count}")
    print(f"JSON: {output_path}")
    print(f"Markdown: {markdown_path}")
    return 0


def _diagnose(item, primary, secondary, short_reason):
    evidence = item.get("evidence_pool", [])
    draft = item.get("draft") or {"answer": "", "claims": []}
    verification = item.get("verification") or {}
    missing = [name for name, hit in item.get("expected_concept_hits", {}).items() if not hit]
    cited = {evidence_id for claim in draft.get("claims", []) for evidence_id in claim.get("evidence_ids", [])}
    expected = list(item.get("expected_concept_hits", {}))
    expected_sources = set(item.get("expected_source_ids", []))
    relevant_unused = []
    for evidence_item in evidence:
        searchable = " ".join(str(evidence_item.get(field) or "") for field in ("content", "section", "symbol", "file_path"))
        if (
            evidence_item.get("source_id") in expected_sources
            and any(concept.casefold() in searchable.casefold() for concept in expected)
            and evidence_item["evidence_id"] not in cited
        ):
            relevant_unused.append(evidence_item["evidence_id"])
    draft_text = draft.get("answer", "") + "\n" + "\n".join(claim.get("text", "") for claim in draft.get("claims", []))
    checker_issue = ""
    if primary == "D":
        checker_issue = "Checker scans canonical evidence body only; the expected qualified symbol appears in metadata and Draft."
    draft_issue = ""
    if primary == "B" or secondary == "B":
        draft_issue = "Draft returned no usable claims despite relevant retrieved evidence."
    elif primary == "A" and draft.get("claims"):
        draft_issue = "Draft cannot cite the missing target chunk; any uncited answer wording is not claim-level support."
    verifier_issue = ""
    if not verification.get("sufficient", False):
        verifier_issue = (
            "Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection."
        )
    retrieval_status = (
        "Expected source_id was retrieved, but the required chunk/symbol was absent."
        if primary == "A"
        else "Relevant expected evidence is present in EvidencePool."
    )
    if primary == "D":
        retrieval_status = "Required evidence is present; qualified symbol is carried in section/symbol metadata."
    context = item.get("context") or {}
    return {
        "case_id": item["case_id"],
        "primary_failure_category": f"{primary}. {CATEGORY_NAMES[primary]}",
        "secondary_category": f"{secondary}. {CATEGORY_NAMES[secondary]}" if secondary else None,
        "retrieval_status": retrieval_status,
        "expected_concepts_missing": missing,
        "evidence_present_but_unused": relevant_unused,
        "draft_issue": draft_issue,
        "verifier_issue": verifier_issue,
        "checker_issue": checker_issue,
        "short_reason": short_reason,
        "inspection": {
            "query": context.get("original_query", ""),
            "contextualized_query": context.get("contextualized_query", ""),
            "expected_source_ids": item.get("expected_source_ids", []),
            "actual_source_ids": item.get("actual_source_ids", []),
            "expected_concept_check": item.get("expected_concept_hits", {}),
            "top_evidence": [
                {
                    "evidence_id": evidence_item.get("evidence_id"),
                    "source_id": evidence_item.get("source_id"),
                    "section": evidence_item.get("section"),
                    "symbol": evidence_item.get("symbol"),
                    "file_path": evidence_item.get("file_path"),
                }
                for evidence_item in evidence
            ],
            "draft_answer": draft.get("answer", ""),
            "draft_claims": draft.get("claims", []),
            "draft_contains_expected_concepts": {
                concept: concept.casefold() in draft_text.casefold() for concept in expected
            },
            "verification": verification,
        },
    }


def _fixes():
    return [
        {
            "rank": 1,
            "fix": "Replace the narrow deterministic draft demo adapter with a generic evidence-grounded deterministic synthesis fixture, or evaluate with the configured production provider.",
            "affected_failure_cases": [
                "single-react-mechanism", "single-react-feedback", "single-reflexion-mechanism",
                "single-reflexion-components", "session-react-observation", "session-reflexion-memory",
            ],
            "expected_benefit": "Allows the already-retrieved relevant evidence to produce claims; addresses 6/14 failures without changing retrieval.",
            "implementation_risk": "Medium: a deterministic fixture must remain generic and must not encode per-case success; a live provider reduces reproducibility.",
            "changes_production_behavior": False,
            "suitable_for_minimal_step_9_2": True,
        },
        {
            "rank": 2,
            "fix": "Produce a concise resolved research query from conversation context before retrieval, instead of passing the full memory transcript as the retrieval question.",
            "affected_failure_cases": [
                "session-mini-action", "session-mini-environment", "cross-mini-agent-loop",
                "cross-mini-actions", "cross-mini-history", "cross-mini-environment",
            ],
            "expected_benefit": "Improves chunk/symbol targeting for 6 memory cases whose entity was resolved but whose top evidence was dominated by broad README chunks.",
            "implementation_risk": "Medium: query rewriting can drop relevant context and would alter runtime behavior even if ranking remains unchanged.",
            "changes_production_behavior": True,
            "suitable_for_minimal_step_9_2": False,
        },
        {
            "rank": 3,
            "fix": "Make the evaluation concept checker inspect evidence section/symbol/file metadata in addition to canonical body text.",
            "affected_failure_cases": ["single-mini-action-execution"],
            "expected_benefit": "Corrects the demonstrated qualified-symbol false negative without loosening verifier behavior or changing expected concepts.",
            "implementation_risk": "Low: evaluation-only deterministic matching change, gated to existing provenance metadata.",
            "changes_production_behavior": False,
            "suitable_for_minimal_step_9_2": True,
        },
    ]


def _markdown(diagnosis):
    lines = [
        "# AgentEvidence Failure Diagnosis",
        "",
        "No production component, verifier threshold, or benchmark expectation was changed.",
        "",
        "## Aggregate attribution",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in diagnosis["aggregate_counts"].items())
    lines.extend(("", "## Per-case diagnosis", ""))
    for row in diagnosis["diagnoses"]:
        lines.extend((
            f"### `{row['case_id']}` — {row['primary_failure_category']}",
            "",
            f"- Retrieval: {row['retrieval_status']}",
            f"- Missing concepts: {', '.join(row['expected_concepts_missing']) or 'none'}",
            f"- Evidence present but unused: {', '.join(row['evidence_present_but_unused']) or 'none'}",
            f"- Draft: {row['draft_issue'] or 'no primary Draft defect'}",
            f"- Verifier: {row['verifier_issue'] or 'no independent verifier defect'}",
            f"- Checker: {row['checker_issue'] or 'no checker defect'}",
            f"- Reason: {row['short_reason']}",
            "",
        ))
    lines.extend(("## Top 3 highest-leverage fixes", ""))
    for fix in diagnosis["top_fixes"]:
        lines.extend((
            f"### {fix['rank']}. {fix['fix']}",
            "",
            f"- Affected: {', '.join(fix['affected_failure_cases'])}",
            f"- Benefit: {fix['expected_benefit']}",
            f"- Risk: {fix['implementation_risk']}",
            f"- Changes production behavior: {'YES' if fix['changes_production_behavior'] else 'NO'}",
            f"- Minimal Step 9.2: {'YES' if fix['suitable_for_minimal_step_9_2'] else 'NO'}",
            "",
        ))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
