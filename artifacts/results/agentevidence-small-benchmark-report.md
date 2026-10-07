# AgentEvidence Small Benchmark

- Cases: 20/20
- Runtime Completion Rate: 100.00%
- Source Hit Rate: 100.00%
- Expected Concept Hit Rate: 61.11%
- Grounded Answer Rate: 30.00%
- Same-session Context Resolution Accuracy: 100.00%
- Cross-session Memory Recall Accuracy: 100.00%
- Insufficient-evidence Accuracy: 100.00%

## Stateless vs Hierarchical Memory

| Scope | Stateless | Hierarchical memory |
|---|---:|---:|
| Same session | 0.00% | 100.00% |
| Cross session | 0.00% | 100.00% |

## Failures

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

## Interpretation

`verifier.sufficient` is used only as the system's internal grounded-answer signal. No LLM judge or claim of independent factual correctness is made.
