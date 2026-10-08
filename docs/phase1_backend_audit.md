# Phase 1 Backend Audit

## Clean-project baseline

`AgentEvidence-clean` already contained the working research core: the custom
`EventDrivenCoordinator`, immutable `CollaborationBlackboard`, dependency-driven
research workers, `ResearchEventDrivenRuntime`, Research Harness, OpenAI-compatible
chat client, SQLite/SQLAlchemy chunk storage, PyMuPDF ingestion, BM25 + Chroma
hybrid retrieval, reranking, and the Evidence Verification Gate. The existing
runtime regression test passed before Phase 1 work (`1 test`, `OK`).

The checkout is **not a Git worktree** (`git status` reports that it is not a Git
repository), so there was no Git status or commit history to preserve. Existing
`.env`, databases, Chroma data, source PDFs, and experiment artifacts were not
overwritten.

## Missing backend capabilities

- No FastAPI entrypoint or versioned API.
- No stable JSON/SSE response contracts.
- No request-safe runtime composition root.
- No managed PDF upload registry, size validation, listing, detail, or deletion API.
- No dependency declaration, placeholder environment file, API documentation, or
  backend README.
- Only one fake runtime test; no HTTP, SSE, or document lifecycle tests.

## Old-project review

The read-only `mind-py` project provided useful patterns in `app/main.py`,
`app/api/routes.py`, and `app/services/research_chat.py`: router registration,
`StreamingResponse`, and runtime assembly. These patterns were reimplemented
against the clean contracts rather than copied.

The old authentication/user/session psychology APIs, MindBridge business models,
tool-worker routes, static HTML/JavaScript hosting, admin endpoints, and its generic
filename-keyed upload endpoint are tightly coupled to the old product and were not
migrated. The old SSE service also performed synchronous work in the async path and
was not reused directly.

## Dependency and configuration findings

The environment already had the runtime packages, but the clean checkout had no
dependency manifest. `requirements.txt` now declares only packages imported by the
backend. Chat and embedding configuration were already independently configurable
through `OPENAI_*` and `EMBEDDING_*`; that separation is preserved.

## Decisions and risks

- Keep existing module paths and custom runtime; add a narrow `app/api` layer.
- Build a fresh Harness/runtime per request so Blackboard and trace state are not
  shared concurrently.
- Run the synchronous runtime and PDF ingestion in worker threads from async routes.
- Emit stage-level SSE only from observed Blackboard events/artifacts. Token-level
  streaming is not available.
- Register API-managed PDFs in one additional SQLAlchemy table. Their chunks stay in
  `knowledge_chunks`; vectors stay in the existing Chroma collection.
- Duplicate uploads are idempotent by SHA-256 checksum.
- SQLite and Chroma cannot share an atomic transaction. Delete quarantines the file,
  deletes Chroma + SQL source data, commits the SQL registry transaction, and
  attempts vector-index repair on a SQL failure. A repair failure is reported as an
  explicit consistency error, never as success.
- Retrieval Repair remains present only as unfinished core code. It is not wired into
  the Phase 1 API and diagnostics report the attempt count as unavailable.
