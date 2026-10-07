from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from datetime import date
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
import certifi


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "research_raw"
CORPUS_ROOT = PROJECT_ROOT / "data" / "research_corpus"

PAPERS = (
    ("react", "ReAct: Synergizing Reasoning and Acting in Language Models", "https://arxiv.org/abs/2210.03629", "https://arxiv.org/pdf/2210.03629"),
    ("reflexion", "Reflexion: Language Agents with Verbal Reinforcement Learning", "https://arxiv.org/abs/2303.11366", "https://arxiv.org/pdf/2303.11366"),
)
REPOSITORY_URL = "https://github.com/SWE-agent/mini-swe-agent"


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MindBridge-research-corpus-bootstrap/1.0"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=90, context=context) as response:
        return response.read()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_paper(source_id: str, title: str, canonical_url: str, pdf_url: str) -> None:
    raw_dir = RAW_ROOT / source_id
    corpus_dir = CORPUS_ROOT / source_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    raw = download(pdf_url)
    raw_path = raw_dir / "raw.pdf"
    raw_path.write_bytes(raw)
    reader = PdfReader(BytesIO(raw))
    pages = [f"[Page {index}]\n\n{page.extract_text() or ''}" for index, page in enumerate(reader.pages, 1)]
    (corpus_dir / "content.md").write_text("\n\n".join(pages), encoding="utf-8")
    write_json(corpus_dir / "source.json", {
        "source_id": source_id, "title": title, "source_type": "paper",
        "source_url": canonical_url, "retrieved_at": date.today().isoformat(),
        "original_format": "pdf", "conversion_method": "pypdf_extract_text_with_page_markers",
        "verified": False, "raw_file": f"data/research_raw/{source_id}/raw.pdf",
        "processed_file": "content.md",
    })


def prepare_repository() -> None:
    repo_data = json.loads(download("https://api.github.com/repos/SWE-agent/mini-swe-agent").decode("utf-8"))
    branch = repo_data["default_branch"]
    commit_data = json.loads(download(f"https://api.github.com/repos/SWE-agent/mini-swe-agent/commits/{branch}").decode("utf-8"))
    commit = commit_data["sha"]
    readme_url = f"https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/{commit}/README.md"
    raw = download(readme_url)
    raw_dir = RAW_ROOT / "mini_swe_agent"
    corpus_dir = CORPUS_ROOT / "mini_swe_agent"
    raw_dir.mkdir(parents=True, exist_ok=True)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "raw_README.md").write_bytes(raw)
    (corpus_dir / "content.md").write_bytes(raw)
    write_json(corpus_dir / "source.json", {
        "source_id": "mini_swe_agent", "title": "mini-SWE-agent", "source_type": "repository",
        "source_url": REPOSITORY_URL, "retrieved_at": date.today().isoformat(),
        "original_format": "markdown", "conversion_method": "exact_readme_copy",
        "verified": False, "repository_url": REPOSITORY_URL, "branch": branch,
        "commit": commit, "tag": None,
        "raw_file": "data/research_raw/mini_swe_agent/raw_README.md", "processed_file": "content.md",
    })


def main() -> int:
    failures = []
    for source in PAPERS:
        try:
            prepare_paper(*source)
            print(f"READY {source[0]}")
        except Exception as exc:
            failures.append((source[0], source[2], f"{type(exc).__name__}: {exc}"))
    try:
        prepare_repository()
        print("READY mini_swe_agent")
    except Exception as exc:
        failures.append(("mini_swe_agent", REPOSITORY_URL, f"{type(exc).__name__}: {exc}"))
    pending = PROJECT_ROOT / "SOURCES_PENDING.md"
    if failures:
        lines = ["# Sources Pending", ""]
        for source_id, url, reason in failures:
            lines.extend([f"## {source_id}", "", f"Canonical URL: {url}", "Status: SOURCE_REQUIRES_MANUAL_DOWNLOAD", f"Reason: {reason}", "Suggested manual action: download the canonical source and rerun preparation.", ""])
        pending.write_text("\n".join(lines), encoding="utf-8")
        return 1
    if pending.exists():
        pending.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
