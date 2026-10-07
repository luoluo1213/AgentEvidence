# AgentEvidence E2E Baseline

run_variant: `baseline`

| Metric | Result |
|---|---:|
| Answer Correctness | Pending / 人工标注后计算 |
| Single-doc Source Hit | N/A |
| Cross-doc All-Source Hit | 1/1 (100.00%) |
| Same-session Memory | N/A |
| Cross-session Memory | N/A |
| Avg Latency | 39.615 s |
| Median Latency | 39.615 s |

Answer Correctness is filled only after human annotation. Stateless memory ablation is diagnostic, not a resume headline.

Same-session stateless: N/A
Cross-session stateless: N/A

## Harness diagnostics

- provider_failure_count: 0
- agent_stage_failure_count: 1
- draft_validation_failure_count: 1
- draft_repair_attempt_count: 1
- draft_repair_success_count: 0
- evidence_insufficient_count: 0
- total_tokens: 14536
- estimated_cost: None
