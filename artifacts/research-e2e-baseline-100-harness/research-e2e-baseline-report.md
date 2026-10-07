# AgentEvidence E2E Baseline

run_variant: `baseline`

| Metric | Result |
|---|---:|
| Answer Correctness | Pending / 人工标注后计算 |
| Single-doc Source Hit | 45/45 (100.00%) |
| Cross-doc All-Source Hit | 22/25 (88.00%) |
| Same-session Memory | 10/10 |
| Cross-session Memory | 10/10 |
| Avg Latency | 26.598 s |
| Median Latency | 20.35 s |

Answer Correctness is filled only after human annotation. Stateless memory ablation is diagnostic, not a resume headline.

Same-session stateless: 0/10
Cross-session stateless: 0/10

## Harness diagnostics

- provider_failure_count: 0
- agent_stage_failure_count: 16
- draft_validation_failure_count: 20
- draft_repair_attempt_count: 20
- draft_repair_success_count: 4
- evidence_insufficient_count: 0
- total_tokens: 1175139
- estimated_cost: None
