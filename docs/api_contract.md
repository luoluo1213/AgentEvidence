# AgentEvidence API Contract (v0.1.0)

Base URL for local development: `http://127.0.0.1:8000/api/v1`.

All JSON endpoints use UTF-8. API errors use an `error` object with stable `code`
and human-readable `message` fields. Provider credentials, prompts, authorization
headers, and raw provider responses are never part of the contract.

## Health

`GET /health`

```json
{"status":"ok","service":"AgentEvidence","version":"0.1.0"}
```

The health route does not construct an LLM, embedding client, or vector model.

## Research JSON API

`POST /research`

```json
{
  "query": "Compare the reasoning mechanisms of ReAct and Reflexion.",
  "session_id": "session-001"
}
```

`session_id` is optional. In Phase 1 the clean runtime uses its existing null
persistence memory implementation, while the MemoryAgent still runs as a genuine
Blackboard worker. The identifier is preserved for future memory integration.

A grounded response has HTTP 200 and status `success`:

```json
{
  "run_id": "0b3d...",
  "status": "success",
  "session_id": "session-001",
  "answer": "...",
  "sources": [
    {
      "source_id": "research:react_pdf",
      "source_title": "ReAct",
      "source_type": "paper",
      "evidence_ids": ["evidence-..."],
      "sections": ["Method"]
    }
  ],
  "verification": {
    "sufficient": true,
    "supported_points": [],
    "missing_points": [],
    "weak_evidence_ids": [],
    "suggested_queries": [],
    "reason": "..."
  },
  "diagnostics": {
    "result_status": "success",
    "provider_failure": false,
    "draft_validation_failure": false,
    "evidence_insufficient": false,
    "fallback_used": false,
    "draft_repair_attempts": 0,
    "retrieval_repair_attempts": null,
    "total_tokens": null,
    "duration_ms": 1234.5,
    "failure_stage": null,
    "error_type": null,
    "stage_traces": []
  },
  "error": null
}
```

When verification fails, HTTP remains 200, `status` is
`evidence_insufficient`, `verification.sufficient` is false, and `answer` is the
existing Verification Gate's conservative answer. This is not a successful
grounded answer. Provider/runtime failures use HTTP 502/500 with `status: error`, a
safe error object, and any real safe diagnostics collected before failure.

## Research SSE API

`POST /research/stream` accepts the same JSON body and returns
`text/event-stream`. The synchronous runtime runs in a worker thread so it does not
block the FastAPI event loop.

Each event has the same envelope:

```text
event: task.completed
data: {"event":"task.completed","run_id":"...","timestamp":"2026-10-08T...+00:00","sequence":4,"data":{"task_id":"task:research:evidence","agent":"ResearchAgent","status":"completed"}}
```

Event vocabulary:

| Event | Emission condition |
|---|---|
| `run.started` | The API accepted the validated request. |
| `task.started` | A real Blackboard `TASK_CLAIMED` event exists. |
| `task.completed` | A real Blackboard `TASK_CLOSED` event exists. |
| `artifact.created` | A real Blackboard `ARTIFACT_PUBLISHED` event exists. |
| `retrieval.completed` | An `evidence_pool` artifact exists. |
| `draft.completed` | A `research_draft` artifact exists. |
| `verification.completed` | An `evidence_verification` artifact exists. |
| `run.completed` | A final result exists; data contains the full Research response. |
| `run.failed` | Provider/runtime execution failed; data contains a safe error. |

`run.completed` is also used for `evidence_insufficient`; inspect its `status`.
Exactly one terminal `run.completed` or `run.failed` event is emitted. Events become
available after their synchronous stage/run is observable; Phase 1 does not promise
token streaming or fabricated real-time progress.

Browser example:

```ts
const response = await fetch("http://127.0.0.1:8000/api/v1/research/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ query, session_id: sessionId }),
});
// POST-based SSE is consumed from response.body with a small SSE parser;
// native EventSource supports GET only.
```

## PDF documents

### Upload

`POST /documents/upload`, `multipart/form-data`, field name `file`.

Only PDF filenames/content types with PDF magic bytes are accepted. The configured
`RESEARCH_PDF_MAX_BYTES` limit is enforced before ingestion. The server generates
`document_id`, `source_id`, and storage filename; the submitted filename is metadata
only. Ingestion uses the existing PyMuPDF page extraction and retains page provenance
in knowledge-chunk metadata.

```json
{
  "document_id": "doc_...",
  "source_id": "research:upload_...",
  "filename": "paper.pdf",
  "content_type": "application/pdf",
  "size_bytes": 12345,
  "status": "completed",
  "chunk_count": 8,
  "error": null,
  "created_at": "2026-10-08T...",
  "updated_at": "2026-10-08T...",
  "duplicate": false
}
```

The duplicate policy is SHA-256 idempotency: uploading identical bytes returns the
existing record with HTTP 200 and `duplicate: true`; a new upload returns HTTP 201.
Extraction/index failure returns the registered document with status `failed` and
HTTP 422 without exposing a local path or provider detail.

### List and detail

- `GET /documents` returns API-managed documents newest first.
- `GET /documents/{document_id}` returns one document or HTTP 404.

Pre-existing fixed corpus sources not uploaded through this API are not represented
as managed documents and therefore are not listed.

### Delete

`DELETE /documents/{document_id}` removes the source's Chroma vectors, SQLite
`knowledge_chunks`, document registry row, and quarantined upload file. Success:

```json
{
  "document_id": "doc_...",
  "source_id": "research:upload_...",
  "status": "deleted",
  "removed_chunks": 8
}
```

SQLite and Chroma do not support a shared transaction. If deletion cannot complete,
the API returns HTTP 500; it never reports a partial operation as success. The
service restores the quarantined file and attempts vector repair when applicable.

## HTTP/error summary

| Status | Meaning |
|---|---|
| 200 | Health, list/detail, duplicate upload, completed or evidence-insufficient research. |
| 201 | New PDF accepted and ingested. |
| 404 | Managed document does not exist. |
| 422 | Schema/file validation or PDF ingestion failure. |
| 500 | Runtime or document consistency failure. |
| 502 | Chat provider failure. |

## CORS

Origins are an explicit comma-separated `CORS_ORIGINS` setting. Defaults allow Vite
at `http://localhost:5173` and `http://127.0.0.1:5173`. Wildcard origins are not
enabled. Methods are limited to GET, POST, DELETE, and OPTIONS.
