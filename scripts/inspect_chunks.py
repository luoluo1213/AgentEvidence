import json
import statistics

from app.core.database import SessionLocal
from app.models.entities import KnowledgeChunk


SOURCE = "research:react_pdf_dynamic_v6"

db = SessionLocal()

try:
    rows = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.source == SOURCE)
        .order_by(KnowledgeChunk.source_index)
        .all()
    )

    lengths = [len(row.content) for row in rows]

    print("=== Chunk Statistics ===")
    print("count  =", len(rows))
    print("min    =", min(lengths))
    print("median =", int(statistics.median(lengths)))
    print("mean   =", round(statistics.mean(lengths), 1))
    print("max    =", max(lengths))

    print("\n=== First 5 Chunks ===")

    for row in rows[:5]:
        metadata = json.loads(row.metadata_json or "{}")

        print("\n----------------------------")
        print("index =", row.source_index)
        print("chars =", len(row.content))
        print("page  =", metadata.get("page"))
        print("section =", metadata.get("section"))
        print(row.content[:600])

finally:
    db.close()