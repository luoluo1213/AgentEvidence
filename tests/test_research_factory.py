from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.services.research_factory import build_research_runtime


class ResearchFactoryTest(unittest.TestCase):
    def test_factory_builds_isolated_real_runtime_bundles(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'factory.db'}")
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            settings = Settings(
                knowledge_vector_enabled=False,
                database_url=f"sqlite:///{Path(directory) / 'factory.db'}",
            )
            with Session() as first_db, Session() as second_db:
                first = build_research_runtime(first_db, settings, run_id="run-one")
                second = build_research_runtime(second_db, settings, run_id="run-two")
            self.assertIsNot(first.runtime, second.runtime)
            self.assertIsNot(first.harness, second.harness)
            self.assertEqual(first.harness.run_id, "run-one")
            worker_names = {
                agent.profile.name
                for agent in first.runtime.coordinator.registry.agents
            }
            self.assertEqual(worker_names, {
                "MemoryAgent", "TaskAnalyzer", "ResearchAgent", "DraftAgent", "EvidenceVerifier"
            })
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
