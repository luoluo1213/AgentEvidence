from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.dependencies import (
    get_app_settings,
    get_research_document_service,
    get_research_execution_service,
)
from app.api.schemas import (
    DocumentDeleteResponse,
    DocumentResponse,
    HealthResponse,
    ResearchDiagnosticsResponse,
    ResearchRequest,
    ResearchResponse,
)
from app.api.serialization import research_response
from app.api.sse import SseEnvelopeFactory, encode_sse, observed_runtime_events
from app.core.config import Settings
from app.services.document_service import (
    DocumentConsistencyError,
    DocumentNotFoundError,
    DocumentValidationError,
    ResearchDocumentService,
)
from app.services.research_execution import (
    ResearchExecutionFailure,
    ResearchExecutionService,
)


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)


@router.post("/research", response_model=ResearchResponse)
def research(
    request: ResearchRequest,
    service: ResearchExecutionService = Depends(get_research_execution_service),
):
    try:
        execution = service.execute(request.query, request.session_id)
    except ResearchExecutionFailure as exc:
        body = _failed_research_response(exc, request.session_id)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))
    return research_response(execution, request.session_id)


@router.post("/research/stream")
async def research_stream(
    request: ResearchRequest,
    service: ResearchExecutionService = Depends(get_research_execution_service),
):
    run_id = uuid.uuid4().hex

    async def stream():
        factory = SseEnvelopeFactory(run_id)
        event, payload = factory.make("run.started", {
            "session_id": request.session_id,
            "streaming": "stage",
        })
        yield encode_sse(event, payload)
        try:
            execution = await run_in_threadpool(
                service.execute,
                request.query,
                request.session_id,
                run_id=run_id,
            )
            response = research_response(execution, request.session_id)
            for event, payload in observed_runtime_events(execution, response, factory):
                yield encode_sse(event, payload)
        except ResearchExecutionFailure as exc:
            event, payload = factory.make("run.failed", {
                "status": "error",
                "code": exc.code,
                "message": exc.public_message,
                "diagnostics": exc.diagnostics,
            })
            yield encode_sse(event, payload)
        except Exception:
            event, payload = factory.make("run.failed", {
                "status": "error",
                "code": "runtime_failure",
                "message": "The research runtime failed to complete.",
            })
            yield encode_sse(event, payload)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/documents/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    response: Response,
    file: UploadFile = File(...),
    service: ResearchDocumentService = Depends(get_research_document_service),
    settings: Settings = Depends(get_app_settings),
):
    data = await file.read(settings.research_pdf_max_bytes + 1)
    try:
        result = await run_in_threadpool(
            service.upload,
            file.filename or "",
            file.content_type,
            data,
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response.status_code = 200 if result.duplicate else (422 if result.document.status == "failed" else 201)
    return _document_response(result.document, duplicate=result.duplicate)


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    service: ResearchDocumentService = Depends(get_research_document_service),
):
    return [_document_response(document) for document in service.list_documents()]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    service: ResearchDocumentService = Depends(get_research_document_service),
):
    try:
        return _document_response(service.get(document_id))
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document was not found") from exc


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(
    document_id: str,
    service: ResearchDocumentService = Depends(get_research_document_service),
):
    try:
        result = service.delete(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="document was not found") from exc
    except DocumentConsistencyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return DocumentDeleteResponse(
        document_id=result.document_id,
        source_id=result.source_id,
        status="deleted",
        removed_chunks=result.removed_chunks,
    )


def _document_response(document, *, duplicate: bool = False) -> DocumentResponse:
    return DocumentResponse(
        document_id=document.id,
        source_id=document.source_id,
        filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status,
        chunk_count=document.chunk_count,
        error=document.ingestion_error,
        created_at=document.created_at,
        updated_at=document.updated_at,
        duplicate=duplicate,
    )


def _failed_research_response(
    exc: ResearchExecutionFailure,
    session_id: str | None,
) -> ResearchResponse:
    return ResearchResponse(
        run_id=exc.run_id,
        status="error",
        session_id=session_id,
        diagnostics=ResearchDiagnosticsResponse.model_validate(exc.diagnostics),
        error={"code": exc.code, "message": exc.public_message},
    )
