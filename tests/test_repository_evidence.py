import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.research_agent import ResearchAgent
from app.agents.research_types import ResearchTask, ResearchTaskType
from app.core.config import Settings
from app.core.database import Base
from app.services.knowledge import KnowledgeService
from app.services.repository_evidence import code_aware_chunks
from app.services.research_corpus import ResearchCorpusLoader


COMMIT = "04d809ceab9df28f9adaed044884180159172930"
FILE_PATH = "src/minisweagent/agents/default.py"
CODE = '''class DefaultAgent:\n    def run(self):\n        while True:\n            self.step()\n\n    def step(self):\n        return self.execute_actions(self.query())\n\n    def execute_actions(self, message):\n        output = self.env.execute(message)\n        self.messages.append(output)\n        return output\n'''


class RepositoryEvidenceTests(unittest.TestCase):
    def test_code_chunking_preserves_symbols_and_exact_source(self):
        chunks = code_aware_chunks(CODE, file_path=FILE_PATH, commit=COMMIT, repository_url="https://github.com/SWE-agent/mini-swe-agent")
        by_symbol = {chunk.symbol: chunk for chunk in chunks}
        self.assertIn("DefaultAgent.run", by_symbol)
        self.assertIn("while True:", by_symbol["DefaultAgent.run"].content)
        self.assertEqual(by_symbol["DefaultAgent.run"].file_path, FILE_PATH)
        self.assertEqual(by_symbol["DefaultAgent.run"].content_type, "source_code")
        self.assertEqual(by_symbol["DefaultAgent.run"].commit, COMMIT)

    def test_loader_keeps_readme_and_code_in_one_source_with_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            corpus = project / "data/research_corpus/mini_swe_agent"
            normalized = project / "data/research_normalized/mini_swe_agent"
            raw = project / "data/research_raw/mini_swe_agent/repository" / FILE_PATH
            corpus.mkdir(parents=True)
            normalized.mkdir(parents=True)
            raw.parent.mkdir(parents=True)
            (corpus / "content.md").write_text("README raw", encoding="utf-8")
            (normalized / "document.md").write_text("# mini-SWE-agent\n\nREADME minimal agent documentation.", encoding="utf-8")
            raw.write_text(CODE, encoding="utf-8")
            (corpus / "source.json").write_text(json.dumps({
                "source_id": "mini_swe_agent", "title": "mini-SWE-agent", "source_type": "repository",
                "source_url": "https://github.com/SWE-agent/mini-swe-agent", "retrieved_at": "2026-10-01",
                "original_format": "markdown", "conversion_method": "exact_readme_copy", "verified": False,
                "repository_url": "https://github.com/SWE-agent/mini-swe-agent", "branch": "main", "commit": COMMIT,
                "raw_file": "data/research_raw/mini_swe_agent/raw_README.md", "processed_file": "content.md",
                "normalized_file": "data/research_normalized/mini_swe_agent/document.md",
                "normalization_method": "structure_preserving_cleanup",
                "normalized_from": "data/research_corpus/mini_swe_agent/content.md",
                "repository_files": [{
                    "file_path": FILE_PATH, "raw_file": f"data/research_raw/mini_swe_agent/repository/{FILE_PATH}",
                    "content_type": "source_code", "language": "python",
                    "repository_url": "https://github.com/SWE-agent/mini-swe-agent", "commit": COMMIT,
                    "source_url": f"https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/{COMMIT}/{FILE_PATH}",
                }],
            }), encoding="utf-8")
            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            db = sessionmaker(bind=engine)()
            try:
                service = KnowledgeService(db, Settings(knowledge_vector_enabled=False))
                loader = ResearchCorpusLoader(project / "data/research_corpus")
                metadata, _ = loader.discover()[0]
                self.assertEqual(metadata.commit, COMMIT)
                loader.bootstrap(service, include_translations=False)
                service.ingest("psychology.md", "psychology support only")

                code_results = service.retrieve("DefaultAgent execute_actions messages", 8, corpus="research")
                code = [item for item in code_results if item.metadata.get("content_type") == "source_code"]
                self.assertTrue(code)
                self.assertTrue(all(item.source == "research:mini_swe_agent" for item in code))
                self.assertTrue(any(item.metadata.get("file_path") == FILE_PATH for item in code))
                self.assertTrue(any(item.metadata.get("symbol") == "DefaultAgent.execute_actions" for item in code))
                self.assertTrue(all(item.content_zh is None for item in code))
                self.assertTrue(all(item.translation_status == "skipped_source_code" for item in code))

                loop_results = service.retrieve("mini-SWE-agent 的核心 Agent loop 是如何执行的？", 8, corpus="research")
                self.assertTrue(any(
                    item.metadata.get("symbol", "").startswith("DefaultAgent.run.while_loop")
                    for item in loop_results
                ))

                action_results = service.retrieve(
                    "mini-SWE-agent 如何执行 action，并把执行结果加入 history？", 8, corpus="research"
                )
                action_symbols = {item.metadata.get("symbol") for item in action_results}
                self.assertIn("DefaultAgent.execute_actions", action_symbols)

                readme = service.retrieve("README minimal documentation", 8, corpus="research")
                self.assertTrue(any(item.metadata.get("content_type") == "documentation" for item in readme))
                self.assertEqual(service.retrieve("psychology support", 4, corpus="psychology")[0].source, "psychology.md")

                task = ResearchTask(task_id="repo", query="DefaultAgent execute_actions messages", task_type=ResearchTaskType.FACT_LOOKUP)
                pool = ResearchAgent(service).research(task)
                keys = [(item.metadata.get("file_path"), item.metadata.get("symbol"), item.chunk_id) for item in pool.items]
                self.assertEqual(len(keys), len(set(keys)))
            finally:
                db.close()
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
