# Step 2 — Research Domain Contracts

## Step 2 Goal

Add typed AgentEvidence research-domain contracts and disabled-by-default runtime settings without wiring them into the existing MindBridge runtime.

## Files Added

- `app/agents/research_types.py`
- `app/agents/research_artifacts.py`
- `tests/test_research_types.py`
- `REFACTOR_STEP2.md`

## Files Modified

- `app/core/config.py`
- `.env.example`

## New Domain Models

- `ResearchTaskType`
- `ResearchSourceType`
- `ResearchTask`
- `EvidenceItem`
- `EvidencePool`
- `EvidenceVerificationResult`
- `ResearchRunMetrics`

## New Artifact Kinds

`TASK_ANALYSIS`, `RETRIEVAL_QUERY`, `EVIDENCE_BUNDLE`, `EVIDENCE_VERIFICATION`, `RETRIEVAL_REPAIR`, `RESPONSE_DRAFT`, and `FINAL_RESPONSE`.

## New Settings

- `research_mode_enabled = False`
- `research_max_retrieval_rounds = 2`
- `research_retrieval_top_k = 8`
- `research_max_evidence_items = 12`

## Tests Added

Unit coverage for ResearchTask serialization, EvidenceItem fields, EvidencePool deduplication/source and round helpers, EvidenceVerificationResult serialization, RESPONSE_DRAFT, and default settings.

## Future Structure

```text
ResearchTask
    ↓
EvidencePool
    ↓
Verification
    ↓
Response Draft

Not wired into runtime yet
```

## Runtime Behaviour Changed?

**NO.** The existing chat route still uses `MindBridgeAgentHarness` and `EventDrivenAgentRuntimeService`. The new research setting is an unused, disabled-by-default placeholder.
