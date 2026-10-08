from app.core.config import Settings
from app.core.database import SessionLocal
from app.services.knowledge import KnowledgeService


TEST_SOURCES = [
    "research:react",
    "research:react_pdf_dynamic",
    "research:react_pdf_dynamic_v2",
    "research:react_pdf_dynamic_v3",
    "research:react_pdf_dynamic_v4",
    "research:react_pdf_dynamic_v5",
    "research:react_pdf_dynamic_v6",
]


db = SessionLocal()

try:
    knowledge = KnowledgeService(db, Settings())

    for source in TEST_SOURCES:
        print("deleting:", source)
        knowledge.delete_source(source)

    print("done")

finally:
    db.close()