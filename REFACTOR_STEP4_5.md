# Step 4.5 — Research Corpus Bootstrap with Source Provenance

## Goal

Bootstrap a real, provenance-backed P0 research corpus for ReAct, Reflexion, and mini-SWE-agent, isolate it from the existing psychology corpus in both retrieval paths, and validate the Step 3/4 research flow without wiring a new runtime.

## Sources Acquired

All three P0 sources were acquired from primary public sources on 2026-10-01. Every generated `source.json` has `verified: false`. No model-authored factual text was added to `content.md`.

## Canonical URLs

- ReAct: https://arxiv.org/abs/2210.03629
- Reflexion: https://arxiv.org/abs/2303.11366
- mini-SWE-agent: https://github.com/SWE-agent/mini-swe-agent

## Raw Source Locations

- `data/research_raw/react/raw.pdf`
- `data/research_raw/reflexion/raw.pdf`
- `data/research_raw/mini_swe_agent/raw_README.md`

## Processed Corpus Locations

- `data/research_corpus/react/content.md`
- `data/research_corpus/reflexion/content.md`
- `data/research_corpus/mini_swe_agent/content.md`

## Corpus Metadata

Each processed source has a colocated `source.json` validated by `ResearchCorpusSource`. Paper text is a mechanical `pypdf` extraction with page markers. The repository document is an exact copy of the README pinned to commit `04d809ceab9df28f9adaed044884180159172930`.

## Ingestion Path

`ResearchCorpusLoader` discovers and validates metadata, reads `content.md`, assigns `research:<source_id>`, and calls `KnowledgeService.ensure_source`. Existing chunking, embedding, database, Chroma, BM25, fusion, reranking, and expansion remain shared.

## Research Isolation Strategy

- BM25 selects database candidates by the `research:` source prefix for `corpus="research"`, and excludes that prefix for `corpus="psychology"`.
- Chroma chunks carry exact `corpus` metadata and filtered queries use `where={"corpus": ...}`.
- `corpus=None` retains the pre-change unfiltered behavior.
- `ResearchAgent` defaults to `corpus="research"`.
- The existing MindBridge `ContextAgent` explicitly requests `corpus="psychology"`.

## KnowledgeService Changes

`KnowledgeService.retrieve` gained the optional, backward-compatible `corpus` argument. No ranking weights, candidate scoring, fusion, reranker, chunking, embedding, or context expansion logic changed.

## ResearchAgent Changes

The constructor gained an optional `corpus` argument defaulting to `research`; the existing query strategy, cap, round-robin merge, deduplication, evidence limit, and failure handling are unchanged.

## Bootstrap Results

SQLite integration bootstrap completed twice (idempotence is also unit tested):

- `research:mini_swe_agent`: 25 chunks
- `research:react`: 247 chunks
- `research:reflexion`: 133 chunks
- Total: 3 sources / 405 chunks

The configured MySQL service was not listening on `127.0.0.1:3306`, and Chroma is unavailable in this environment. Therefore production MySQL/Chroma indexing is not claimed; the local integration used SQLite and the real BM25 fallback. The bootstrap script will rebuild Chroma when the configured vector store is available.

## Retrieval Results

- mini-SWE-agent query: all top 8 raw results were `research:mini_swe_agent`.
- ReAct query: all top 8 raw results were `research:react`.
- Reflexion query: all top 8 raw results were `research:reflexion`.
- Comparison: 12 merged evidence items; final source IDs included both `research:react` and `research:reflexion`.
- Comparison diagnostics: question 1 returned 8 raw results (ReAct and Reflexion); question 2 returned 8 Reflexion results; the source-neutral Chinese-only comparison question returned 0. The merged pool retained both target sources, so there is no merge/dedup loss for Reflexion.

No psychology source appeared in these runs.

## Tests

`python -m unittest discover -s tests`: 63 tests passed. New coverage includes metadata parsing, namespace generation, idempotence, research-only and psychology-only BM25 filtering, unfiltered backward compatibility, ResearchAgent isolation, and Chroma filter propagation.

## Manual Verification Required

All sources remain `verified: false`. Complete the unchecked checklist in `RESEARCH_SOURCES.md` before changing any source to verified.

## Runtime Wiring

NOT YET
