from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings
from app.services.ai import AiClient


class DemoMockAiClient:
    def complete(self, messages) -> str:
        query = messages[-1].content
        lowered = query.lower()
        if ("论文" in lowered or "paper" in lowered) and any(
            term in lowered for term in ("github", "repo", "repository", "实现", "代码", "readme")
        ):
            payload = {
                "task_type": "PAPER_REPO_ANALYSIS",
                "entities": ["mini-SWE-agent"] if "mini-swe-agent" in lowered else [],
                "research_questions": [
                    "论文如何描述核心 agent loop？",
                    "仓库实现中的哪些组件对应这一循环？",
                    "论文描述与实现之间有哪些一致或不同之处？",
                ],
                "expected_source_types": ["paper", "repository"],
                "requires_comparison": False,
                "requires_multiple_sources": True,
            }
        elif any(term in lowered for term in ("比较", "compare", " vs ", "versus", "差异", "区别")):
            entities = [name for name in ("ReAct", "Reflexion") if name.lower() in lowered]
            payload = {
                "task_type": "CROSS_DOCUMENT_COMPARISON",
                "entities": entities,
                "research_questions": [
                    "ReAct 如何使用 observation 或 environment feedback？",
                    "Reflexion 如何生成并利用 reflection 或 feedback？",
                    "两者在反馈使用时机和作用方式上有哪些差异？",
                ],
                "expected_source_types": ["paper"],
                "requires_comparison": True,
                "requires_multiple_sources": True,
            }
        else:
            payload = {
                "task_type": "FACT_LOOKUP",
                "entities": ["mini-SWE-agent"] if "mini-swe-agent" in lowered else [],
                "research_questions": [query],
                "expected_source_types": ["paper", "repository"] if "mini-swe-agent" in lowered else [],
                "requires_comparison": False,
                "requires_multiple_sources": False,
            }
        return json.dumps(payload, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze one AgentEvidence research query.")
    parser.add_argument("query")
    parser.add_argument("--mock", action="store_true", help="Use the deterministic local demo provider.")
    args = parser.parse_args(argv)

    settings = Settings()
    client = DemoMockAiClient() if args.mock or settings.ai_provider.lower() == "mock" else AiClient(settings)
    task = TaskAnalyzerAgent(client).analyze(args.query)

    print(f"Task ID:\n{task.task_id}\n")
    print(f"Task Type:\n{task.task_type.value}\n")
    print("Entities:")
    print("\n".join(f"- {item}" for item in task.entities) or "- none")
    print("\nResearch Questions:")
    print("\n".join(f"{index}. {item}" for index, item in enumerate(task.research_questions, start=1)))
    print("\nExpected Sources:")
    print("\n".join(f"- {item.value}" for item in task.expected_source_types) or "- none")
    print(f"\nRequires Comparison:\n{str(task.requires_comparison).lower()}")
    print(f"\nRequires Multiple Sources:\n{str(task.requires_multiple_sources).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
