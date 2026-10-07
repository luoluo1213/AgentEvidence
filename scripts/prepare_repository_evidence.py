from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_METADATA = PROJECT_ROOT / "data" / "research_corpus" / "mini_swe_agent" / "source.json"
RAW_REPOSITORY = PROJECT_ROOT / "data" / "research_raw" / "mini_swe_agent" / "repository"
FILES = (
    "src/minisweagent/agents/default.py",
    "src/minisweagent/environments/local.py",
)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MindBridge-repository-evidence/1.0"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=90, context=context) as response:
        return response.read()


def main() -> int:
    metadata = json.loads(SOURCE_METADATA.read_text(encoding="utf-8"))
    commit = metadata["commit"]
    repository_url = metadata["repository_url"].rstrip("/")
    records = []
    for file_path in FILES:
        url = f"https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/{commit}/{file_path}"
        raw = download(url)
        destination = RAW_REPOSITORY / file_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        records.append({
            "file_path": file_path,
            "raw_file": destination.relative_to(PROJECT_ROOT).as_posix(),
            "content_type": "source_code",
            "language": "python",
            "repository_url": repository_url,
            "commit": commit,
            "source_url": url,
        })
        print(f"READY {file_path} ({len(raw)} bytes)")
    metadata["repository_files"] = records
    SOURCE_METADATA.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
