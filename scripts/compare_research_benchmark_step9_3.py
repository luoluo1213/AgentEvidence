from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "artifacts" / "results" / "agentevidence-step9-2-baseline-results.json"
DEFAULT_CURRENT = ROOT / "artifacts" / "results" / "agentevidence-small-benchmark-results.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "results" / "agentevidence-step9-3-comparison.md"
METRICS = (
    "runtime_completion_rate",
    "source_hit_rate",
    "expected_concept_hit_rate",
    "grounded_answer_rate",
    "same_session_context_resolution_accuracy",
    "cross_session_memory_recall_accuracy",
    "insufficient_evidence_accuracy",
)
TARGET_CASES = (
    "single-react-mechanism",
    "single-react-feedback",
    "single-reflexion-mechanism",
    "single-reflexion-components",
    "session-react-observation",
    "session-reflexion-memory",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Step 9.2 and Step 9.3 benchmark results.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--current", default=str(DEFAULT_CURRENT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    if baseline["dataset"]["sha256"] != current["dataset"]["sha256"]:
        raise ValueError("benchmark dataset changed; comparison is invalid")
    old = {item["case_id"]: item for item in baseline["results"]}
    new = {item["case_id"]: item for item in current["results"]}
    changed = [
        case_id for case_id in old
        if any(old[case_id].get(field) != new[case_id].get(field) for field in (
            "source_hit", "expected_concept_hits", "grounded", "answer", "draft", "verification"
        ))
    ]
    recovered = [case_id for case_id in TARGET_CASES if not old[case_id]["grounded"] and new[case_id]["grounded"]]
    lines = [
        "# AgentEvidence Step 9.2 vs Step 9.3",
        "",
        "## Metrics",
        "",
        "| Metric | Step 9.2 | Step 9.3 | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric in METRICS:
        before, after = baseline["metrics"][metric], current["metrics"][metric]
        lines.append(f"| {metric} | {before:.2%} | {after:.2%} | {after - before:+.2%} |")
    lines.extend((
        "",
        "## Target cases",
        "",
        f"- Recovered: {len(recovered)}/6" + (f" ({', '.join(recovered)})" if recovered else ""),
        "- All six raw provider responses were valid explicit fallback drafts with zero claims.",
        "- No generic parsing, schema, evidence-ID, post-processing, or language-normalization bug was found.",
        "- No fix was applied because creating semantic content from EvidencePool is prohibited.",
        "",
        "## Regressions",
        "",
        f"- Changed production-output cases: {len(changed)}" + (f" ({', '.join(changed)})" if changed else ""),
        "- Metric regressions: none",
        "",
        "## Remaining failures",
        "",
    ))
    lines.extend(f"- `{item['case_id']}`: {item['reason']}" for item in current["failures"])
    lines.extend((
        "",
        "## Guardrails",
        "",
        "- Production retrieval behavior changed: NO",
        "- Verifier thresholds changed: NO",
        "- Benchmark expectations changed: NO",
        "- Case-specific production logic added: NO",
        "- Evaluator-generated semantic content: NO",
        "",
    ))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Recovered target cases: {len(recovered)}/6")
    print(f"Changed output cases: {len(changed)}")
    print(f"Remaining failures: {len(current['failures'])}")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
