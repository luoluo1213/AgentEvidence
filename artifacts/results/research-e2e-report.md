# AgentEvidence Real-Provider E2E Evaluation

Provider/model: `openai / deepseek-v4-pro`

## Automatic metrics

- Runtime Success: 100.00%
- Evidence Hit@5: 38.89%
- Provider failure cases: 1 (5.00%)
- Same-session Context Resolution: 100.00%
- Cross-session Memory Recall: 0.00%
- Insufficient-evidence Handling: 100.00%
- Average latency: 62640.611 ms
- Average retrieved evidence: 8.2
- Average runtime events: 38.0
- Token usage: unavailable from the current AiClient response interface

## Memory ablation

| Scope | Stateless | Hierarchical |
|---|---:|---:|
| Same session | 0.00% | 100.00% |
| Cross session | 0.00% | 0.00% |

## Internal EvidenceVerifier

- {"insufficient": 20}

## Pending human metrics

- Answer Correctness: **PENDING HUMAN REVIEW**
- Supported Claim Rate: **PENDING HUMAN REVIEW**
- Verifier-vs-human agreement: **PENDING HUMAN REVIEW**

## Failures

- `single-attention-scaling`: production Draft returned the conservative fallback with no grounded claims
- `single-attention-position`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `single-attention-heads`: production Draft returned the conservative fallback with no grounded claims
- `single-react-loop`: production Draft returned the conservative fallback with no grounded claims
- `single-react-trajectory`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `single-react-grounding`: production Draft returned the conservative fallback with no grounded claims
- `single-reflexion-memory`: production Draft returned the conservative fallback with no grounded claims
- `single-reflexion-loop`: production Draft returned the conservative fallback with no grounded claims
- `compare-react-reflexion-feedback`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `compare-react-reflexion-memory`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `compare-attention-react-information`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `compare-react-reflexion-components`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `session-attention-why`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `session-react-feedback`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `session-reflexion-why`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `session-method-difference`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims
- `cross-session-react`: production Draft returned the conservative fallback with no grounded claims; context referent not resolved
- `cross-session-reflexion`: verified evidence not found in top 5; production Draft returned the conservative fallback with no grounded claims; context referent not resolved
- `insufficient-training-carbon`: one or more real provider calls failed
