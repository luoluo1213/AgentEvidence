import unittest

from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.agents.research_types import ResearchSourceType, ResearchTask, ResearchTaskType


class FakeAiClient:
    def __init__(self, response: str = "", error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.response


class TaskAnalyzerAgentTests(unittest.TestCase):
    def test_fact_lookup_returns_typed_research_task(self):
        client = FakeAiClient(
            """```json
{
  "task_type": "FACT_LOOKUP",
  "entities": ["mini-SWE-agent"],
  "research_questions": ["mini-SWE-agent 的核心 Agent loop 是什么？"],
  "expected_source_types": ["paper", "repository"],
  "requires_comparison": false,
  "requires_multiple_sources": false
}
```"""
        )

        task = TaskAnalyzerAgent(client).analyze("mini-SWE-agent 的核心 Agent loop 是什么？")

        self.assertIsInstance(task, ResearchTask)
        self.assertEqual(task.task_type, ResearchTaskType.FACT_LOOKUP)
        self.assertEqual(task.entities, ["mini-SWE-agent"])
        self.assertTrue(task.task_id.startswith("research-task-"))
        self.assertEqual(len(client.calls), 1)

    def test_cross_document_comparison_enforces_flags(self):
        client = FakeAiClient(
            """Here is the result:
{"task_type":"CROSS_DOCUMENT_COMPARISON","entities":["ReAct","Reflexion"],
"research_questions":["How does each method use feedback?"],"expected_source_types":["paper"],
"requires_comparison":false,"requires_multiple_sources":false}"""
        )

        task = TaskAnalyzerAgent(client).analyze("比较 ReAct 和 Reflexion 如何利用执行反馈。")

        self.assertEqual(task.task_type, ResearchTaskType.CROSS_DOCUMENT_COMPARISON)
        self.assertTrue(task.requires_comparison)
        self.assertTrue(task.requires_multiple_sources)

    def test_paper_repo_analysis_has_both_source_types(self):
        client = FakeAiClient(
            """{"task_type":"PAPER_REPO_ANALYSIS","entities":["mini-SWE-agent"],
"research_questions":["How does the paper loop map to the implementation?"],
"expected_source_types":["paper"],"requires_comparison":false,"requires_multiple_sources":true}"""
        )

        task = TaskAnalyzerAgent(client).analyze("分析 mini-SWE-agent 论文描述的 agent loop 与 GitHub 实现如何对应。")

        self.assertEqual(task.task_type, ResearchTaskType.PAPER_REPO_ANALYSIS)
        self.assertIn(ResearchSourceType.PAPER, task.expected_source_types)
        self.assertIn(ResearchSourceType.REPOSITORY, task.expected_source_types)

    def test_invalid_json_returns_fallback(self):
        task = TaskAnalyzerAgent(FakeAiClient("this is not json")).analyze(
            "比较 ReAct 和 Reflexion 如何利用执行反馈。"
        )

        self.assertIsInstance(task, ResearchTask)
        self.assertEqual(task.task_type, ResearchTaskType.CROSS_DOCUMENT_COMPARISON)
        self.assertEqual(task.research_questions, [task.query])

    def test_provider_exception_returns_fallback(self):
        task = TaskAnalyzerAgent(FakeAiClient(error=RuntimeError("provider unavailable"))).analyze(
            "分析 mini-SWE-agent 论文中的 agent loop 与 GitHub 实现如何对应。"
        )

        self.assertEqual(task.task_type, ResearchTaskType.PAPER_REPO_ANALYSIS)
        self.assertIn(ResearchSourceType.PAPER, task.expected_source_types)
        self.assertIn(ResearchSourceType.REPOSITORY, task.expected_source_types)

    def test_empty_query_raises_without_calling_provider(self):
        client = FakeAiClient("{}")

        with self.assertRaisesRegex(ValueError, "query must not be empty"):
            TaskAnalyzerAgent(client).analyze("   ")

        self.assertEqual(client.calls, [])

    def test_each_analysis_gets_a_unique_task_id(self):
        client = FakeAiClient(error=RuntimeError("offline"))
        analyzer = TaskAnalyzerAgent(client)

        first = analyzer.analyze("What is ReAct?")
        second = analyzer.analyze("What is Reflexion?")

        self.assertNotEqual(first.task_id, second.task_id)


if __name__ == "__main__":
    unittest.main()
