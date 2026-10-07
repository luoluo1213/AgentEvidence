from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CheckpointStore:
    path: Path

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": 1, "updated_at": None, "results": [], "traces": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def completed_records(self) -> dict[str, dict[str, Any]]:
        payload = self.load()
        return {row["case_id"]: row for row in payload.get("results") or [] if row.get("case_id")}

    def save(self, results: list[dict[str, Any]], traces: list[dict[str, Any]] | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "results": results,
            "traces": traces or [],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
