# Phase 2 Frontend Delivery

## Scope

Phase 2 adds a standalone React research workspace to the Phase 1 FastAPI backend.
It consumes only the documented `/api/v1` contract and does not change the research
runtime, retrieval, drafting, verification, memory, persistence, or provider code.

## Frontend structure

```text
frontend/
|-- src/
|   |-- api/                 # shared HTTP, research, document, and SSE clients
|   |-- components/
|   |   |-- common/          # status and empty-state primitives
|   |   |-- layout/          # application shell and page header
|   |   |-- research/        # grounded result and diagnostics
|   |   `-- trace/           # observed agent/task event trace
|   |-- lib/                 # formatting and trace reducers
|   |-- pages/               # Research, Documents, Runs, Settings
|   |-- styles/              # Tailwind layers and responsive application styles
|   |-- test/                # Vitest DOM setup
|   |-- App.tsx
|   `-- main.tsx
|-- .env.example
|-- package.json
|-- tailwind.config.js
|-- tsconfig*.json
`-- vite.config.ts
```

## Pages and components

- **Research** streams a real research run, renders its Markdown answer, sources,
  verification, diagnostics, and only the task/artifact events observed on the
  stream. Cancellation uses `AbortController`; failed streams expose retry and an
  explicit standard-request fallback.
- **Documents** lists the backend-managed corpus, validates and uploads PDFs,
  opens document metadata, and supports confirmed deletion with visible errors.
- **Runs** records completed runs in the current browser session only. No backend
  run-history endpoint exists, so the UI labels this limitation instead of
  presenting browser state as durable history.
- **Settings** displays the configured public API URL and calls the real health
  endpoint. No provider credentials are read or rendered in the browser.
- `ResearchResult`, `DiagnosticsPanel`, and `AgentTrace` keep grounded output,
  machine diagnostics, and observed runtime progress visually separate.

## API integration

The shared client reads `VITE_API_BASE_URL`, defaulting to
`http://127.0.0.1:8000/api/v1`. It integrates:

- `GET /health`
- `POST /research`
- `POST /research/stream` using `fetch`, `ReadableStream`, streaming `TextDecoder`,
  and an SSE parser
- `GET /documents`
- `POST /documents`
- `GET /documents/{document_id}`
- `DELETE /documents/{document_id}`

The SSE parser handles fragmented UTF-8, fragmented CRLF boundaries, multiple
events in one chunk, malformed JSON, provider/run failures, cancellation, network
disconnects, and streams that end without a terminal event. A run becomes
successful only after an observed `run.completed` event.

Null or absent diagnostics are rendered as **Not available**. The frontend does
not infer retrieval repair, token counts, page counts, citations, source titles,
or task progress that the backend did not return.

## Backend changes

None. Phase 2 modified no files under `app/` or `tests/`, and retained the complete
Phase 1 API and runtime behavior.

## Actual interface validation

The Vite application was exercised in a real browser against the running local
FastAPI service at `127.0.0.1:8000`:

1. Settings reported `AgentEvidence` version `0.1.0` as online through `/health`.
2. Documents loaded the real `GeoVIS.pdf` record (1.7 MB, 33 chunks) and opened its
   backend detail. Uploading that same managed PDF exercised the real upload route
   and displayed the backend duplicate-index policy without creating a fake item.
3. Research submitted `GeoViS 的主要方法是什么？` through the POST SSE endpoint.
   The run completed successfully in approximately 25.8 seconds and rendered its
   real Chinese answer, `GeoVIS.pdf` source, sufficient verification, and six
   observed completed tasks: Memory Context, Task Analysis, Evidence Retrieval,
   Draft Generation, Evidence Verification, and Memory Update.
4. Returned diagnostics were rendered without substitution: 12,420 total tokens,
   25,763.105 ms duration, zero draft repairs, no provider/draft/fallback failure,
   and retrieval repair shown as Not available.
5. Runs then showed the one genuine session run. Desktop and narrow mobile layouts
   were inspected; horizontal overflow was corrected in the responsive styles.

No screenshot file was exported. The points above are results from direct browser
interaction with the real local frontend and backend, not mocked component data.

## Validation results

Frontend validation was run with pnpm because this Windows environment did not
provide an `npm` executable:

```powershell
Set-Location frontend
pnpm run test
pnpm run build
```

- Vitest: **12 passed** across 6 files.
- Production build: **passed**; 1,855 modules transformed.
- Output: `dist/index.html`, 23.31 kB CSS, and 352.96 kB JavaScript before gzip.

Backend regression validation:

```powershell
D:\conda\envs\langgraph_64\python.exe -m unittest discover -s tests -v
```

- unittest: **17 passed**.

## Start commands

Backend terminal:

```powershell
Set-Location D:\experiment\mind-py\AgentEvidence-clean
D:\conda\envs\langgraph_64\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend terminal:

```powershell
Set-Location D:\experiment\mind-py\AgentEvidence-clean\frontend
Copy-Item .env.example .env.local
pnpm install
pnpm run dev -- --host 127.0.0.1
```

Then open `http://127.0.0.1:5173/`.

## Known limitations

- Run history is session-only because the backend exposes no run-history API.
- The clean Phase 1 backend currently reports null-persistence memory semantics;
  the UI does not claim durable conversational memory.
- SSE reports stage/task events and a final result, not token-by-token answer text.
- Retrieval repair is not implemented by this backend and is shown as unavailable.
- Document page count is not in the API contract and is not fabricated by the UI.
- Navigation is client state rather than URL-based routing.
- Authentication and authorization are outside Phase 2 scope.
