# Step 11 — PDF / Document Retrieval Benchmark

Cases: 18  
Distribution: {'lexical': 6, 'paraphrase': 6, 'method': 6}

## Corpus

- Attention Is All You Need (`research:attention_pdf`): 95 chunks, SHA256 `bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697`
- ReAct: Synergizing Reasoning and Acting in Language Models (`research:react_pdf`): 252 chunks, SHA256 `f285b0971ae4a790e402fb93966bed3adde2cf0a04977d08b2b40d6ab0cace69`
- Reflexion: Language Agents with Verbal Reinforcement Learning (`research:reflexion_pdf`): 139 chunks, SHA256 `6059b6f89fea9959bd3dab553fbb97756a3dfb1b15e3cbab2fbf3ab6664333bd`

## Overall metrics

| Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Source Hit@5 |
|---|---:|---:|---:|---:|---:|
| bm25 | 50.00% | 88.89% | 94.44% | 0.6806 | 100.00% |
| vector | 55.56% | 83.33% | 88.89% | 0.7083 | 100.00% |
| hybrid | 66.67% | 94.44% | 94.44% | 0.8056 | 100.00% |

## Metrics by query type

| Type | Mode | Hit@1 | Hit@3 | Hit@5 | MRR | Source Hit@5 |
|---|---|---:|---:|---:|---:|---:|
| lexical | bm25 | 83.33% | 100.00% | 100.00% | 0.8889 | 100.00% |
| lexical | vector | 66.67% | 83.33% | 83.33% | 0.7500 | 100.00% |
| lexical | hybrid | 83.33% | 100.00% | 100.00% | 0.9167 | 100.00% |
| paraphrase | bm25 | 66.67% | 100.00% | 100.00% | 0.8056 | 100.00% |
| paraphrase | vector | 66.67% | 100.00% | 100.00% | 0.8333 | 100.00% |
| paraphrase | hybrid | 50.00% | 100.00% | 100.00% | 0.7500 | 100.00% |
| method | bm25 | 0.00% | 66.67% | 83.33% | 0.3472 | 100.00% |
| method | vector | 33.33% | 66.67% | 83.33% | 0.5417 | 100.00% |
| method | hybrid | 66.67% | 83.33% | 83.33% | 0.7500 | 100.00% |

## Comparison

- Best by query type: `{"lexical": {"best_methods": ["bm25", "hybrid"], "evidence_hit_at_5": 1.0}, "paraphrase": {"best_methods": ["bm25", "vector", "hybrid"], "evidence_hit_at_5": 1.0}, "method": {"best_methods": ["bm25", "vector", "hybrid"], "evidence_hit_at_5": 0.8333333333333334}}`
- Hybrid recovered over BM25: react-dynamic-loop
- Vector semantic-noise cases: attention-label-smoothing, attention-position-order, attention-sinusoidal-encoding, react-four-benchmarks, react-success-improvements, react-hallucination-grounding, react-reason-action-synergy, react-trajectory-components, reflexion-three-models, reflexion-memory-types, reflexion-feedback-conversion
- Missed by all methods: none
- Chunk-boundary failures: none; every label resolved to at least one real chunk before evaluation.

## Backend validation

- bm25_vector_disabled: True
- vector_chroma_used: True
- hybrid_chroma_used: True
- vector_fallback_used: False
- hybrid_fallback_used: False

## Limitations

- This is a small 18-case internal benchmark over three papers.
- Ground truth is deterministic anchor/page matching, not graded answer relevance.
- Chroma telemetry warnings from the installed client do not affect retrieval results.
