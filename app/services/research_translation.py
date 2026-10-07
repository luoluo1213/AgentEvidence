from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from app.schemas.dtos import AiMessage


TRANSLATION_SYSTEM_PROMPT = """You are a faithful technical translator from English to Chinese.
Translate the supplied text faithfully. Do not summarize, explain, add background, omit details, or change facts.
Preserve all numbers, experimental results, method names, code, variables, function/class names, file paths, URLs, JSON, and shell commands.
Keep domain-specific names and technical terms accurate; natural Chinese with an English term in parentheses is allowed when useful.
Return only the translated text, with no commentary or wrapper."""


class Translator(Protocol):
    def complete(self, messages: list[AiMessage]) -> str:
        ...


@dataclass
class ResearchTranslation:
    logical_chunk_id: str
    source_id: str
    source_index: int
    section: str | None
    content_hash: str
    content_en: str
    content_zh: str | None
    canonical_language: str = "en"
    translation_status: str = "pending"
    translation_method: str | None = None
    translation_provider: str | None = None
    translation_model: str | None = None
    translation_verified: bool = False
    error: str | None = None

    @classmethod
    def from_dict(cls, value: dict) -> "ResearchTranslation":
        return cls(**value)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def logical_chunk_id(source_id: str, source_index: int, content: str) -> str:
    return f"research:{source_id}:{source_index:04d}:{content_hash(content)[:16]}"


def load_translation_cache(path: Path) -> list[ResearchTranslation]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ResearchTranslation.from_dict(item) for item in data.get("chunks", [])]


def save_translation_cache(path: Path, entries: list[ResearchTranslation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "chunks": [asdict(entry) for entry in entries]}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def translate_chunks(
    source_id: str,
    chunks: list[str],
    translator: Translator,
    cache_path: Path,
    *,
    method: str,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[list[ResearchTranslation], dict[str, int]]:
    cached_by_key = {
        (entry.source_index, entry.content_hash): entry
        for entry in load_translation_cache(cache_path)
        if entry.translation_status == "success" and entry.content_zh
    }
    results: list[ResearchTranslation] = []
    stats = {"total": len(chunks), "cached": 0, "translated": 0, "failed": 0}
    for index, content_en in enumerate(chunks):
        digest = content_hash(content_en)
        cached = cached_by_key.get((index, digest))
        if cached is not None and cached.content_en == content_en:
            results.append(cached)
            stats["cached"] += 1
            continue
        entry = ResearchTranslation(
            logical_chunk_id=logical_chunk_id(source_id, index, content_en),
            source_id=f"research:{source_id}",
            source_index=index,
            section=_section(content_en),
            content_hash=digest,
            content_en=content_en,
            content_zh=None,
            translation_method=method,
            translation_provider=provider,
            translation_model=model,
        )
        try:
            translated = translator.complete([
                AiMessage(role="system", content=TRANSLATION_SYSTEM_PROMPT),
                AiMessage(role="user", content=content_en),
            ]).strip()
            if not translated:
                raise ValueError("translator returned empty content")
            entry.content_zh = translated
            entry.translation_status = "success"
            stats["translated"] += 1
        except Exception as exc:
            entry.translation_status = "failed"
            entry.error = f"{type(exc).__name__}: {exc}"
            stats["failed"] += 1
        results.append(entry)
        save_translation_cache(cache_path, results)
    save_translation_cache(cache_path, results)
    return results, stats


def _section(content: str) -> str | None:
    first = content.splitlines()[0].strip() if content else ""
    return first.lstrip("#").strip() if first.startswith("#") else None
