from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.services.document_service import ResearchDocumentService
from app.services.research_execution import ResearchExecutionService


def get_app_settings() -> Settings:
    return get_settings()


def get_research_execution_service(
    settings: Settings = Depends(get_app_settings),
) -> ResearchExecutionService:
    return ResearchExecutionService(settings)


def get_research_document_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ResearchDocumentService:
    return ResearchDocumentService(db, settings)
