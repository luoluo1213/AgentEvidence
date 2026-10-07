# AgentEvidence Step 9.2 Comparison

The dataset, expected concepts, expected source IDs, verifier thresholds, and production behavior are unchanged.

## Metrics

| Metric | Step 9 | Step 9.2 | Delta |
|---|---:|---:|---:|
| runtime_completion_rate | 100.00% | 100.00% | +0.00% |
| source_hit_rate | 100.00% | 100.00% | +0.00% |
| expected_concept_hit_rate | 55.56% | 61.11% | +5.56% |
| grounded_answer_rate | 30.00% | 30.00% | +0.00% |
| same_session_context_resolution_accuracy | 100.00% | 100.00% | +0.00% |
| cross_session_memory_recall_accuracy | 100.00% | 100.00% | +0.00% |
| insufficient_evidence_accuracy | 100.00% | 100.00% | +0.00% |

## Synthesis audit

All six diagnosed synthesis cases still contain the production fallback answer and zero claims. The evaluation layer had no existing semantic output to preserve, so it did not create replacement answers or claims.

- `single-react-mechanism`: claims=0; remains failed
- `single-react-feedback`: claims=0; remains failed
- `single-reflexion-mechanism`: claims=0; remains failed
- `single-reflexion-components`: claims=0; remains failed
- `session-react-observation`: claims=0; remains failed
- `session-reflexion-memory`: claims=0; remains failed

## Per-case changes

- `single-mini-action-execution`: provenance-aware match corrected LocalEnvironment.execute; grounded remained true.

## Remaining failures

- `single-react-mechanism`: verifier.sufficient=false
- `single-react-feedback`: verifier.sufficient=false
- `single-reflexion-mechanism`: verifier.sufficient=false
- `single-reflexion-components`: verifier.sufficient=false
- `single-mini-architecture`: missing expected concepts: history; verifier.sufficient=false
- `session-mini-action`: missing expected concepts: execute_actions; verifier.sufficient=false
- `session-react-observation`: verifier.sufficient=false
- `session-reflexion-memory`: verifier.sufficient=false
- `session-mini-environment`: missing expected concepts: LocalEnvironment.execute, returncode
- `cross-mini-agent-loop`: missing expected concepts: loop; verifier.sufficient=false
- `cross-mini-actions`: missing expected concepts: execute_actions; verifier.sufficient=false
- `cross-mini-history`: missing expected concepts: add_messages; verifier.sufficient=false
- `cross-mini-environment`: missing expected concepts: LocalEnvironment; verifier.sufficient=false

## Guardrails

- Production behavior changed: NO
- Benchmark expectations changed: NO
- Verifier thresholds changed: NO
- Evaluation-generated semantic content: NO
