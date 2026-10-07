# AgentEvidence Failure Diagnosis

No production component, verifier threshold, or benchmark expectation was changed.

## Aggregate attribution

| Category | Count |
|---|---:|
| Retrieval miss | 7 |
| Evidence present, synthesis miss | 6 |
| Draft supported, verifier rejection | 0 |
| Evaluation checker mismatch | 1 |
| Genuine insufficient evidence | 0 |
| Other | 0 |

## Per-case diagnosis

### `single-react-mechanism` — B. Evidence present, synthesis miss

- Retrieval: Relevant expected evidence is present in EvidencePool.
- Missing concepts: none
- Evidence present but unused: research:react:50, research:react:60, research:react:51, research:react:111, research:react:133, research:react:55, research:react:95, research:react:62
- Draft: Draft returned no usable claims despite relevant retrieved evidence.
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: Mechanism chunks from the expected source contain all expected concepts, but Draft is the empty conservative fallback.

### `single-react-feedback` — B. Evidence present, synthesis miss

- Retrieval: Relevant expected evidence is present in EvidencePool.
- Missing concepts: none
- Evidence present but unused: research:react:115, research:react:100
- Draft: Draft returned no usable claims despite relevant retrieved evidence.
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: Feedback evidence from the expected source is present, but Draft contains no claims.

### `single-reflexion-mechanism` — B. Evidence present, synthesis miss

- Retrieval: Relevant expected evidence is present in EvidencePool.
- Missing concepts: none
- Evidence present but unused: research:reflexion:192, research:reflexion:195, research:reflexion:162, research:reflexion:196, research:reflexion:197, research:reflexion:167, research:reflexion:191
- Draft: Draft returned no usable claims despite relevant retrieved evidence.
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: The expected method section contains reflection, feedback and memory, but Draft is empty.

### `single-reflexion-components` — B. Evidence present, synthesis miss

- Retrieval: Relevant expected evidence is present in EvidencePool.
- Missing concepts: none
- Evidence present but unused: research:reflexion:196, research:reflexion:184, research:reflexion:185, research:reflexion:188, research:reflexion:182, research:reflexion:190, research:reflexion:195
- Draft: Draft returned no usable claims despite relevant retrieved evidence.
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: Actor/Evaluator/Self-Reflection evidence is present, but Draft contains no claims.

### `single-mini-architecture` — A. Retrieval miss

- Retrieval: Expected source_id was retrieved, but the required chunk/symbol was absent.
- Missing concepts: history
- Evidence present but unused: research:mini_swe_agent:2, research:mini_swe_agent:4, research:mini_swe_agent:1, research:mini_swe_agent:12, research:mini_swe_agent:5, research:mini_swe_agent:9
- Draft: Draft returned no usable claims despite relevant retrieved evidence.
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: The mini-SWE source is hit, but no history/code-loop chunk is retrieved; the remaining architecture evidence is also not synthesized.

### `single-mini-action-execution` — D. Evaluation checker mismatch

- Retrieval: Required evidence is present; qualified symbol is carried in section/symbol metadata.
- Missing concepts: LocalEnvironment.execute
- Evidence present but unused: research:mini_swe_agent:23
- Draft: no primary Draft defect
- Verifier: no independent verifier defect
- Checker: Checker scans canonical evidence body only; the expected qualified symbol appears in metadata and Draft.
- Reason: LocalEnvironment.execute is present as evidence symbol metadata and in the supported Draft, while the checker scans evidence body text only.

### `session-mini-action` — A. Retrieval miss

- Retrieval: Expected source_id was retrieved, but the required chunk/symbol was absent.
- Missing concepts: execute_actions
- Evidence present but unused: none
- Draft: no primary Draft defect
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: Context resolves the entity, but top evidence contains README/general chunks rather than DefaultAgent.execute_actions.

### `session-react-observation` — B. Evidence present, synthesis miss

- Retrieval: Relevant expected evidence is present in EvidencePool.
- Missing concepts: none
- Evidence present but unused: research:react:82, research:react:110, research:react:143
- Draft: Draft returned no usable claims despite relevant retrieved evidence.
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: Expected method chunks contain observation and reasoning, but Draft is empty.

### `session-reflexion-memory` — B. Evidence present, synthesis miss

- Retrieval: Relevant expected evidence is present in EvidencePool.
- Missing concepts: none
- Evidence present but unused: research:reflexion:191, research:reflexion:187, research:reflexion:194, research:reflexion:240
- Draft: Draft returned no usable claims despite relevant retrieved evidence.
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: Expected reflection/memory evidence is present, but Draft is empty.

### `session-mini-environment` — A. Retrieval miss

- Retrieval: Expected source_id was retrieved, but the required chunk/symbol was absent.
- Missing concepts: LocalEnvironment.execute, returncode
- Evidence present but unused: none
- Draft: Draft returned no usable claims despite relevant retrieved evidence.
- Verifier: no independent verifier defect
- Checker: no checker defect
- Reason: DefaultAgent.execute_actions is retrieved, but LocalEnvironment.execute/returncode evidence is absent; the answer mentions them without claim-level citations.

### `cross-mini-agent-loop` — A. Retrieval miss

- Retrieval: Expected source_id was retrieved, but the required chunk/symbol was absent.
- Missing concepts: loop
- Evidence present but unused: research:mini_swe_agent:8, research:mini_swe_agent:5, research:mini_swe_agent:9, research:mini_swe_agent:7, research:mini_swe_agent:12, research:mini_swe_agent:6, research:mini_swe_agent:13
- Draft: no primary Draft defect
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: The source is hit, but retrieved README motivation chunks do not cover the requested agent-loop mechanism.

### `cross-mini-actions` — A. Retrieval miss

- Retrieval: Expected source_id was retrieved, but the required chunk/symbol was absent.
- Missing concepts: execute_actions
- Evidence present but unused: research:mini_swe_agent:7
- Draft: no primary Draft defect
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: The source is hit, but DefaultAgent.execute_actions is not among retrieved chunks.

### `cross-mini-history` — A. Retrieval miss

- Retrieval: Expected source_id was retrieved, but the required chunk/symbol was absent.
- Missing concepts: add_messages
- Evidence present but unused: research:mini_swe_agent:5, research:mini_swe_agent:6, research:mini_swe_agent:13
- Draft: no primary Draft defect
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: The source is hit, but DefaultAgent.add_messages is not among retrieved chunks.

### `cross-mini-environment` — A. Retrieval miss

- Retrieval: Expected source_id was retrieved, but the required chunk/symbol was absent.
- Missing concepts: LocalEnvironment
- Evidence present but unused: research:mini_swe_agent:12
- Draft: no primary Draft defect
- Verifier: Verifier rejection is downstream of an empty/unsupported Draft, not an independent false rejection.
- Checker: no checker defect
- Reason: The source is hit, but LocalEnvironment.execute is not among retrieved chunks.

## Top 3 highest-leverage fixes

### 1. Replace the narrow deterministic draft demo adapter with a generic evidence-grounded deterministic synthesis fixture, or evaluate with the configured production provider.

- Affected: single-react-mechanism, single-react-feedback, single-reflexion-mechanism, single-reflexion-components, session-react-observation, session-reflexion-memory
- Benefit: Allows the already-retrieved relevant evidence to produce claims; addresses 6/14 failures without changing retrieval.
- Risk: Medium: a deterministic fixture must remain generic and must not encode per-case success; a live provider reduces reproducibility.
- Changes production behavior: NO
- Minimal Step 9.2: YES

### 2. Produce a concise resolved research query from conversation context before retrieval, instead of passing the full memory transcript as the retrieval question.

- Affected: session-mini-action, session-mini-environment, cross-mini-agent-loop, cross-mini-actions, cross-mini-history, cross-mini-environment
- Benefit: Improves chunk/symbol targeting for 6 memory cases whose entity was resolved but whose top evidence was dominated by broad README chunks.
- Risk: Medium: query rewriting can drop relevant context and would alter runtime behavior even if ranking remains unchanged.
- Changes production behavior: YES
- Minimal Step 9.2: NO

### 3. Make the evaluation concept checker inspect evidence section/symbol/file metadata in addition to canonical body text.

- Affected: single-mini-action-execution
- Benefit: Corrects the demonstrated qualified-symbol false negative without loosening verifier behavior or changing expected concepts.
- Risk: Low: evaluation-only deterministic matching change, gated to existing provenance metadata.
- Changes production behavior: NO
- Minimal Step 9.2: YES
