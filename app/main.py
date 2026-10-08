from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies import get_app_settings
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.database import Base, engine
from app.models import ResearchDocument  # noqa: F401 - registers SQLAlchemy metadata


logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, init_database: bool = True) -> FastAPI:
    configured = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if init_database:
            Base.metadata.create_all(bind=engine)
        yield

    application = FastAPI(
        title=configured.app_name,
        version=configured.app_version,
        lifespan=lifespan,
    )
    if settings is not None:
        application.dependency_overrides[get_app_settings] = lambda: configured
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.include_router(router, prefix=configured.api_v1_prefix)

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                },
                "details": [
                    {"location": list(error.get("loc", ())), "message": error.get("msg", "invalid value")}
                    for error in exc.errors()
                ],
            },
        )

    @application.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail)}},
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception):
        logger.exception("unhandled API exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An internal server error occurred.",
                }
            },
        )

    return application


app = create_app()
