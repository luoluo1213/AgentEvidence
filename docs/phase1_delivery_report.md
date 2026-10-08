# Phase 1 Delivery Report

## Result

Phase 1 is complete for the clean backend. FastAPI starts, health responds, the
JSON and stage-level SSE endpoints use the actual `ResearchEventDrivenRuntime`, and
the PDF API invokes the existing PyMuPDF/KnowledgeService ingestion path. The old
`mind-py` project was read only and was not modified.

## Files created

- `app/main.py`
- `app/api/__init__.py`
- `app/api/dependencies.py`
- `app/api/routes.py`
- `app/api/schemas.py`
- `app/api/serialization.py`
- `app/api/sse.py`
- `app/services/document_service.py`
- `app/services/research_execution.py`
- `app/services/research_factory.py`
- `tests/test_api.py`
- `tests/test_documents_api.py`
- `tests/test_research_factory.py`
- `scripts/demo_api.ps1`
- `.env.example`
- `requirements.txt`
- `README.md`
- `docs/phase1_backend_audit.md`
- `docs/api_contract.md`
- `docs/phase1_delivery_report.md`

## Files modified

- `app/core/config.py`: API, CORS, upload configuration.
- `app/models/entities.py`: API-managed `ResearchDocument` registry.
- `app/models/__init__.py`: model exports/metadata registration.
- `app/services/knowledge.py`: source deletion can participate in a wider SQL
  transaction and reports the removed-row count.

No `.env`, existing database contents, Chroma collection contents, uploaded source
PDFs, corpus, ranking logic, prompt, Draft, Verifier, or experiment artifact was
overwritten.

## Reuse and migration

Reused from the clean project:

- All custom Coordinator, Blackboard, AgentTask, AgentArtifact, and AgentEvent logic.
- All six existing research runtime workers (including both MemoryAgent tasks).
- TaskAnalyzer, ResearchAgent, DraftGenerator, EvidenceVerifier, Verification Gate.
- Harness retries, validation, repair, trace, token-usage instrumentation.
- AiClient, KnowledgeService, hybrid retrieval, Chroma, and PyMuPDF ingestion.

From the old project, only architectural patterns were used: FastAPI router setup,
`StreamingResponse`, and a centralized runtime assembly concept. No old code file
was copied wholesale. MindBridge authentication, psychology/business models, tool
workers, admin/static UI, chat routes, and old user/session dependencies were not
migrated.

## Endpoints

- `GET /api/v1/health`
- `POST /api/v1/research`
- `POST /api/v1/research/stream`
- `POST /api/v1/documents/upload`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `DELETE /api/v1/documents/{document_id}`

The JSON endpoint distinguishes `success`, `evidence_insufficient`, and `error`.
The SSE endpoint emits only events justified by observed Blackboard events and
artifacts, and always terminates with `run.completed` or `run.failed`.

## Validation actually executed

Baseline before edits:

```text
D:\conda\envs\langgraph_64\python.exe -m unittest discover -s tests -v
1 test passed; OK
```

Final compile and complete test suite:

```text
D:\conda\envs\langgraph_64\python.exe -m compileall -q app tests
D:\conda\envs\langgraph_64\python.exe -m unittest discover -s tests -v
17 tests passed in 0.609s; OK
```

The suite covers import/startup/health, blank request validation, successful and
insufficient research, provider failure, serialization, request isolation, SSE
ordering/success/failure/insufficient terminal behavior, secret exclusion, absence
of fabricated task events, runtime composition isolation, valid/invalid/oversized
PDFs, page provenance, list/detail/duplicate handling, SQLite deletion, and the
vector-aware source deletion call path.

Additional checks:

- `python -m scripts.smoke_verification_gate`: PASS. (The direct
  `python scripts/smoke_verification_gate.py` form does not put the project root on
  `sys.path`; module invocation is the working form.)
- Real Uvicorn process on `127.0.0.1:8765`: application startup completed;
  `GET /api/v1/health` returned HTTP 200 with the expected payload; clean shutdown
  completed.

Not executed:

- Real chat-provider E2E, to avoid an unrequested billable external LLM call.
- Real embedding endpoint or live Chroma mutation. Tests do not claim live external
  vector verification; they cover the production deletion integration contract with
  an enabled vector-aware test double.

## Known limitations

- SSE is stage-level. The current AiClient is not token-streaming, and internal
  Blackboard events become available to the API after the synchronous runtime call
  returns.
- The clean checkout currently has `NullResearchMemory`; `session_id` is preserved,
  and MemoryAgent runs, but Phase 1 does not add persistent conversation memory.
- Retrieval Repair is not wired into the runtime. Its diagnostics field is `null`.
- SQLite and Chroma cannot provide a distributed atomic transaction. Deletion uses
  quarantine/rollback/repair safeguards and returns an explicit error on uncertainty.
- Only PDFs uploaded through the new API are listed as managed documents; fixed
  corpus sources remain queryable but are not deletable through this API.
- Authentication, authorization, rate limits, background ingestion jobs, and a
  frontend are outside Phase 1.
- The clean directory is not a Git repository, so a Git diff/status could not be
  produced.

## Run commands

```powershell
cd D:\experiment\mind-py\AgentEvidence-clean
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
python -m unittest discover -s tests -v
./scripts/demo_api.ps1
```

## Frontend readiness

A React/TypeScript client can immediately integrate health, JSON research, POST SSE,
and the managed PDF lifecycle using the documented stable IDs and Pydantic response
shapes. CORS defaults cover the normal Vite development origins. OpenAPI is exposed
at `/docs`.
