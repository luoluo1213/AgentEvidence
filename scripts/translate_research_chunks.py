from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import Settings
from app.services.ai import AiClient
from app.services.research_corpus import ResearchCorpusLoader, section_aware_chunks
from app.services.research_translation import translate_chunks


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Translate normalized research chunks into cached Chinese auxiliary text.")
    parser.add_argument("--source", action="append", help="Translate only this source_id (repeatable).")
    args = parser.parse_args(argv)

    settings = Settings(ai_temperature=0.0, ai_max_tokens=max(1536, Settings().ai_max_tokens))
    client = AiClient(settings)
    provider = settings.ai_provider.lower()
    model = settings.ollama_model if provider == "ollama" else settings.openai_model
    selected = set(args.source or [])
    totals = {"total": 0, "cached": 0, "translated": 0, "failed": 0}
    samples = []

    print("=== Research Translation ===")
    loader = ResearchCorpusLoader(PROJECT_ROOT / "data" / "research_corpus")
    for metadata, document_path in loader.discover():
        if selected and metadata.source_id not in selected:
            continue
        chunks = section_aware_chunks(document_path.read_text(encoding="utf-8"), settings.knowledge_chunk_size)
        cache_path = PROJECT_ROOT / "data" / "research_translations" / metadata.source_id / "chunks.json"
        entries, stats = translate_chunks(
            metadata.source_id,
            chunks,
            client,
            cache_path,
            method="ai_client_faithful_technical_translation",
            provider=provider,
            model=model,
        )
        for key in totals:
            totals[key] += stats[key]
        print(f"{metadata.source_id}: total={stats['total']} cached={stats['cached']} translated={stats['translated']} failed={stats['failed']}")
        samples.extend(entry for entry in entries if entry.translation_status == "success" and entry.content_zh)

    print(f"\nTotal: {totals['total']}")
    print(f"Cached: {totals['cached']}")
    print(f"Translated: {totals['translated']}")
    print(f"Failed: {totals['failed']}")
    print(f"Provider: {provider}")
    print(f"Model: {model}")
    print("Translation verified: false")
    print("\n=== Translation Spot Check (not human-verified) ===")
    if samples:
        indexes = sorted({0, len(samples) // 4, len(samples) // 2, (3 * len(samples)) // 4, len(samples) - 1})
        for entry in [samples[index] for index in indexes[:5]]:
            print(f"\nSource: {entry.source_id}\nSection: {entry.section}")
            print(f"English: {' '.join(entry.content_en.split())[:240]}")
            print(f"Chinese: {' '.join((entry.content_zh or '').split())[:240]}")
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
