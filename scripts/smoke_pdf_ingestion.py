from app.core.config import Settings
from app.core.database import Base, SessionLocal, engine
from app.services.knowledge import KnowledgeService
from app.services.source_ingestion import (
    ResearchSourceIngestionService,
    SourceIngestionRequest,
    IngestionSourceType,
)


Base.metadata.create_all(bind=engine)

settings = Settings()
db = SessionLocal()

try:
    knowledge = KnowledgeService(db, settings)

    ingestion = ResearchSourceIngestionService(
        knowledge
    )

    request = SourceIngestionRequest(
        source_type=IngestionSourceType.PAPER,
        source_id="research:reflexion",
        location="data/research_raw/reflexion/raw.pdf",
    )

    result = ingestion.ingest(request)

    print("\n=== PDF Ingestion Result ===")
    print(result.model_dump_json(indent=2))

finally:
    db.close()