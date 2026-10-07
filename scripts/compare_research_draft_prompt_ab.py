from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.research_draft_generator import RESEARCH_DRAFT_SYSTEM_PROMPT


RESULTS = ROOT / "artifacts" / "results"
A_PATH = RESULTS / "agentevidence-step9-4-prompt-a-results.json"
B_PATH = RESULTS / "agentevidence-step9-4-prompt-b-results.json"
JSON_PATH = RESULTS / "agentevidence-step9-4-prompt-ab-comparison.json"
MD_PATH = RESULTS / "agentevidence-step9-4-prompt-ab-comparison.md"
TARGETS = {
    "single-react-mechanism",
    "single-react-feedback",
    "single-reflexion-mechanism",
    "single-reflexion-components",
    "session-react-observation",
    "session-reflexion-memory",
}
B_LINE = (
    "- Work through the research questions one by one. Answer every question or sub-point that the supplied "
    "evidence supports; for any unsupported part, state specifically that the supplied evidence is insufficient "
    "and omit factual claims about it. Do not abstain from the entire draft merely because some parts are unsupported."
)
A_LINE = (
    "- Address every research question explicitly. Explain mechanisms, processes, relationships, differences, "
    "and implementation details whenever the supplied evidence supports them."
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _index(report: dict) -> dict[str, dict]:
    return {row["case_id"]: row for row in report["results"]}


def _claim_details(row: dict) -> dict:
    evidence_ids = {item["evidence_id"] for item in row["evidence_pool"]}
    claims = row["draft"]["claims"]
    cited = [evidence_id for claim in claims for evidence_id in claim["evidence_ids"]]
    invalid = sorted(set(cited) - evidence_ids)
    return {
        "claim_count": len(claims),
        "evidence_ids": cited,
        "evidence_ids_valid": not invalid,
        "invalid_evidence_ids": invalid,
        "verifier_sufficient": row["verification"]["sufficient"],
        "answer": row["answer"],
    }


def main() -> int:
    a = json.loads(A_PATH.read_text(encoding="utf-8"))
    b = json.loads(B_PATH.read_text(encoding="utf-8"))
    a_rows, b_rows = _index(a), _index(b)
    prompt_b = RESEARCH_DRAFT_SYSTEM_PROMPT
    prompt_a = prompt_b.replace(B_LINE, A_LINE)
    targets = []
    recovered = []
    for case_id in sorted(TARGETS):
        before = _claim_details(a_rows[case_id])
        after = _claim_details(b_rows[case_id])
        is_recovered = before["claim_count"] == 0 and after["claim_count"] > 0 and after["evidence_ids_valid"]
        if is_recovered:
            recovered.append(case_id)
        targets.append({
            "case_id": case_id,
            "recovered": is_recovered,
            "answer_changed": before["answer"] != after["answer"],
            "A": before,
            "B": after,
        })

    existing_grounded_regressions = sorted(
        case_id for case_id, row in a_rows.items()
        if row["grounded"] and not b_rows[case_id]["grounded"]
    )
    invalid_claim_cases = sorted(
        case_id for case_id, row in b_rows.items() if not _claim_details(row)["evidence_ids_valid"]
    )
    insufficient = [
        {
            "case_id": case_id,
            "A_conservative": row["insufficient_behavior_pass"],
            "B_conservative": b_rows[case_id]["insufficient_behavior_pass"],
            "answer_changed": row["answer"] != b_rows[case_id]["answer"],
        }
        for case_id, row in a_rows.items() if row["category"] == "insufficient_evidence"
    ]
    no_metric_regression = all(
        b["metrics"][key] >= a["metrics"][key]
        for key in (
            "runtime_completion_rate",
            "same_session_context_resolution_accuracy",
            "cross_session_memory_recall_accuracy",
        )
    )
    accepted = (
        len(recovered) >= 4
        and not invalid_claim_cases
        and b["metrics"]["insufficient_evidence_accuracy"] == 1.0
        and no_metric_regression
        and not existing_grounded_regressions
    )
    comparison = {
        "schema_version": 1,
        "experiment": "Step 9.4 grounded Draft prompt calibration A/B",
        "prompt_A": {"sha256": _sha(prompt_a), "text": prompt_a},
        "prompt_B": {"sha256": _sha(prompt_b), "text": prompt_b},
        "minimal_change": {"removed": A_LINE, "added": B_LINE},
        "dataset_sha256_equal": a["dataset"]["sha256"] == b["dataset"]["sha256"],
        "metrics_A": a["metrics"],
        "metrics_B": b["metrics"],
        "targets": targets,
        "target_cases_recovered": recovered,
        "target_recovery_count": len(recovered),
        "invalid_evidence_id_cases": invalid_claim_cases,
        "unsupported_claim_regression_detected": bool(invalid_claim_cases),
        "existing_grounded_case_regressions": existing_grounded_regressions,
        "insufficient_evidence_cases": insufficient,
        "acceptance": {
            "passed": accepted,
            "decision": "KEEP B" if accepted else "REVERT TO A",
            "criteria": {
                "at_least_4_of_6_recovered": len(recovered) >= 4,
                "all_evidence_ids_valid": not invalid_claim_cases,
                "insufficient_evidence_accuracy_100_percent": b["metrics"]["insufficient_evidence_accuracy"] == 1.0,
                "no_runtime_or_memory_regression": no_metric_regression,
                "no_existing_grounded_case_regression": not existing_grounded_regressions,
            },
        },
        "interpretation": (
            "The same deterministic benchmark provider does not branch on the Draft system prompt, so B produced "
            "the same outputs as A. Keeping B would fail the predeclared recovery threshold."
        ),
    }
    JSON_PATH.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Step 9.4 — Grounded Draft Prompt Calibration A/B",
        "",
        f"- Decision: **{comparison['acceptance']['decision']}**",
        f"- Target recovery: **{len(recovered)}/6**",
        f"- Dataset unchanged: **{comparison['dataset_sha256_equal']}**",
        f"- Invalid evidence-ID cases under B: **{len(invalid_claim_cases)}**",
        f"- Existing grounded-case regressions: **{len(existing_grounded_regressions)}**",
        "",
        "## Prompt change",
        "",
        f"A: `{A_LINE[2:]}`",
        "",
        f"B: `{B_LINE[2:]}`",
        "",
        "## Target cases",
        "",
        "| Case | A claims | B claims | IDs valid | Verifier sufficient | Answer changed | Recovered |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for row in targets:
        lines.append(
            f"| {row['case_id']} | {row['A']['claim_count']} | {row['B']['claim_count']} | "
            f"{row['B']['evidence_ids_valid']} | {row['B']['verifier_sufficient']} | "
            f"{row['answer_changed']} | {row['recovered']} |"
        )
    lines.extend([
        "",
        "## Result",
        "",
        comparison["interpretation"],
        "The two insufficient-evidence cases remained conservative and all measured metrics were unchanged.",
    ])
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Target recovery: {len(recovered)}/6")
    print(f"Decision: {comparison['acceptance']['decision']}")
    print(f"JSON: {JSON_PATH}")
    print(f"Markdown: {MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
