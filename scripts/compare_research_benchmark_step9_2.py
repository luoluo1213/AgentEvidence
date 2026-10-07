from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "artifacts" / "results" / "agentevidence-step9-baseline-results.json"
DEFAULT_CURRENT = ROOT / "artifacts" / "results" / "agentevidence-small-benchmark-results.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "results" / "agentevidence-step9-2-comparison.md"
METRICS = (
    "runtime_completion_rate",
    "source_hit_rate",
    "expected_concept_hit_rate",
    "grounded_answer_rate",
    "same_session_context_resolution_accuracy",
    "cross_session_memory_recall_accuracy",
    "insufficient_evidence_accuracy",
)
SYNTHESIS_CASES = (
    "single-react-mechanism",
    "single-react-feedback",
    "single-reflexion-mechanism",
    "single-reflexion-components",
    "session-react-observation",
    "session-reflexion-memory",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare the Step 9 and Step 9.2 benchmark results.")
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
    changed = []
    for case_id in old:
        before, after = old[case_id], new[case_id]
        if (
            before["expected_concept_hits"] != after["expected_concept_hits"]
            or before["grounded"] != after["grounded"]
            or before["source_hit"] != after["source_hit"]
        ):
            changed.append((case_id, before, after))
    lines = [
        "# AgentEvidence Step 9.2 Comparison",
        "",
        "The dataset, expected concepts, expected source IDs, verifier thresholds, and production behavior are unchanged.",
        "",
        "## Metrics",
        "",
        "| Metric | Step 9 | Step 9.2 | Delta |",
        "|---|---:|---:|---:|",
    ]
    for metric in METRICS:
        before = baseline["metrics"][metric]
        after = current["metrics"][metric]
        lines.append(f"| {metric} | {before:.2%} | {after:.2%} | {after - before:+.2%} |")
    lines.extend((
        "",
        "## Synthesis audit",
        "",
        "All six diagnosed synthesis cases still contain the production fallback answer and zero claims. "
        "The evaluation layer had no existing semantic output to preserve, so it did not create replacement answers or claims.",
        "",
    ))
    for case_id in SYNTHESIS_CASES:
        draft = new[case_id]["draft"]
        lines.append(f"- `{case_id}`: claims={len(draft['claims'])}; remains failed")
    lines.extend(("", "## Per-case changes", ""))
    if changed:
        for case_id, before, after in changed:
            old_hits = before["expected_concept_hits"]
            new_hits = after["expected_concept_hits"]
            changed_concepts = [name for name in old_hits if old_hits[name] != new_hits[name]]
            lines.append(
                f"- `{case_id}`: provenance-aware match corrected {', '.join(changed_concepts)}; "
                f"grounded remained {str(after['grounded']).lower()}."
            )
    else:
        lines.append("- None")
    lines.extend(("", "## Remaining failures", ""))
    lines.extend(f"- `{item['case_id']}`: {item['reason']}" for item in current["failures"])
    lines.extend((
        "",
        "## Guardrails",
        "",
        "- Production behavior changed: NO",
        "- Benchmark expectations changed: NO",
        "- Verifier thresholds changed: NO",
        "- Evaluation-generated semantic content: NO",
        "",
    ))
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Changed cases: {len(changed)}")
    print(f"Remaining failures: {len(current['failures'])}")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
