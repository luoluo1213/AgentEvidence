# Step 11A — Code Retrieval Baseline: BM25 vs Hybrid

Cases: 7

| Metric | BM25-only | Hybrid |
|---|---:|---:|
| symbol_hit_at_1 | 0.00% | 0.00% |
| symbol_hit_at_3 | 0.00% | 0.00% |
| symbol_hit_at_5 | 0.00% | 0.00% |
| any_expected_symbol_hit_at_5 | 0.00% | 0.00% |
| all_expected_symbols_hit_at_5 | 0.00% | 0.00% |
| mrr | 0.00% | 0.00% |

- Hybrid recovered: none
- Hybrid remaining misses: single-mini-architecture, session-mini-action, session-mini-environment, cross-mini-agent-loop, cross-mini-actions, cross-mini-history, cross-mini-environment
- Vector introduced noise: single-mini-architecture, session-mini-action, session-mini-environment, cross-mini-agent-loop, cross-mini-actions, cross-mini-history, cross-mini-environment

## Per-case first expected-symbol rank

| Case | BM25 | Hybrid | Recovered | Vector noise |
|---|---:|---:|---|---|
| single-mini-architecture | miss | miss | False | True |
| session-mini-action | miss | miss | False | True |
| session-mini-environment | miss | miss | False | True |
| cross-mini-agent-loop | miss | miss | False | True |
| cross-mini-actions | miss | miss | False | True |
| cross-mini-history | miss | miss | False | True |
| cross-mini-environment | miss | miss | False | True |

## Validation

- BM25 vector disabled: True
- Hybrid Chroma used for every case: True
- Hybrid fallback used: False
