import unittest

from app.agents.research_agent import MAX_QUERIES_PER_TASK, ResearchAgent
from app.agents.research_types import EvidencePool, ResearchSourceType, ResearchTask, ResearchTaskType
from app.services.knowledge import SearchResult


class FakeKnowledgeService:
    def __init__(self, results=None, failures=None):
        self.results = results or {}
        self.failures = set(failures or [])
        self.calls = []

    def retrieve(self, query, top_k=None, corpus=None):
        self.calls.append((query, top_k, corpus))
        if query in self.failures:
            raise RuntimeError(f"retrieval failed for {query}")
        return list(self.results.get(query, []))[:top_k]


def task(task_type=ResearchTaskType.FACT_LOOKUP, questions=None, query="fallback query", expected_source_types=None, entities=None):
    return ResearchTask(
        task_id="research-task-test",
        query=query,
        task_type=task_type,
        entities=entities or [],
        research_questions=questions or [],
        expected_source_types=expected_source_types or [],
    )


def result(chunk_id, source, content=None, score=0.8, metadata=None):
    return SearchResult(
        chunk_id=chunk_id,
        source=source,
        content=content or f"content-{chunk_id}",
        score=score,
        metadata=metadata or {},
    )


class ResearchAgentTests(unittest.TestCase):
    def test_fact_lookup_returns_evidence_with_query_and_round(self):
        question = "mini-SWE-agent 的核心 Agent loop 是什么？"
        service = FakeKnowledgeService({question: [
            result(1, "mini_swe_agent.md"),
            result(2, "mini_swe_agent.md"),
        ]})

        pool = ResearchAgent(service).research(task(questions=[question]))

        self.assertIsInstance(pool, EvidencePool)
        self.assertEqual(len(pool), 2)
        self.assertTrue(all(item.query_used == question for item in pool.items))
        self.assertTrue(all(item.retrieval_round == 1 for item in pool.items))

    def test_fact_lookup_uses_only_first_research_question(self):
        service = FakeKnowledgeService({"first question": [result(1, "source.md")]})

        ResearchAgent(service).research(task(questions=["first question", "extra question"]))

        self.assertEqual(service.calls, [("first question", 8, "research")])

    def test_comparison_preserves_evidence_from_multiple_questions(self):
        react_query = "ReAct 如何利用执行反馈？"
        reflexion_query = "Reflexion 如何利用执行反馈？"
        service = FakeKnowledgeService({
            react_query: [result(1, "react")],
            reflexion_query: [result(2, "reflexion")],
        })

        pool = ResearchAgent(service).research(
            task(ResearchTaskType.CROSS_DOCUMENT_COMPARISON, [react_query, reflexion_query])
        )

        self.assertEqual(pool.source_ids(), ["react", "reflexion"])

    def test_duplicate_chunk_is_kept_once_with_first_query(self):
        service = FakeKnowledgeService({
            "query A": [result(1, "react")],
            "query B": [result(1, "react")],
        })

        pool = ResearchAgent(service).research(
            task(ResearchTaskType.MULTI_HOP_RESEARCH, ["query A", "query B"])
        )

        matching = [item for item in pool.items if item.evidence_id == "react:1"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].query_used, "query A")

    def test_max_evidence_uses_round_robin_across_queries(self):
        service = FakeKnowledgeService({
            "query A": [result(index, "react") for index in range(1, 6)],
            "query B": [result(index, "reflexion") for index in range(10, 15)],
        })

        pool = ResearchAgent(service, top_k=5, max_evidence_items=3).research(
            task(ResearchTaskType.CROSS_DOCUMENT_COMPARISON, ["query A", "query B"])
        )

        self.assertEqual(len(pool), 3)
        self.assertIn("react", pool.source_ids())
        self.assertIn("reflexion", pool.source_ids())

    def test_one_query_failure_keeps_other_results(self):
        service = FakeKnowledgeService(
            {"query B": [result(2, "reflexion")]},
            failures={"query A"},
        )

        pool = ResearchAgent(service).research(
            task(ResearchTaskType.MULTI_HOP_RESEARCH, ["query A", "query B"])
        )

        self.assertEqual(pool.source_ids(), ["reflexion"])

    def test_all_query_failures_return_empty_pool(self):
        service = FakeKnowledgeService(failures={"query A", "query B"})

        pool = ResearchAgent(service).research(
            task(ResearchTaskType.MULTI_HOP_RESEARCH, ["query A", "query B"])
        )

        self.assertEqual(pool, EvidencePool())

    def test_empty_research_questions_use_task_query(self):
        service = FakeKnowledgeService({"original query": [result(1, "source.md")]})

        pool = ResearchAgent(service).research(task(query="original query"))

        self.assertEqual(service.calls, [("original query", 8, "research")])
        self.assertEqual(pool.items[0].query_used, "original query")

    def test_retrieval_round_is_preserved(self):
        service = FakeKnowledgeService({"query A": [result(1, "react")]})

        pool = ResearchAgent(service).research(task(questions=["query A"]), retrieval_round=2)

        self.assertTrue(all(item.retrieval_round == 2 for item in pool.items))

    def test_missing_chunk_id_uses_deterministic_content_digest(self):
        service = FakeKnowledgeService({"query A": [result(None, "react", "same content")]})
        agent = ResearchAgent(service)

        first = agent.research(task(questions=["query A"]))
        second = agent.research(task(questions=["query A"]))

        self.assertEqual(first.items[0].evidence_id, second.items[0].evidence_id)

    def test_query_count_is_guarded(self):
        questions = [f"query {index}" for index in range(10)]
        service = FakeKnowledgeService()

        ResearchAgent(service).research(task(ResearchTaskType.MULTI_HOP_RESEARCH, questions))

        self.assertEqual(len(service.calls), MAX_QUERIES_PER_TASK)

    def test_memory_wrapper_is_stripped_from_retrieval_queries(self):
        wrapped = (
            "Use the supplied conversation memory only to resolve references in the current research question.\n\n"
            "Stable research context:\nentity: scaled attention\n\n"
            "Current research question:\nHow does Widget interleave steps?"
        )
        service = FakeKnowledgeService({"How does Widget interleave steps?": [result(1, "research:widget_pdf")]})
        ResearchAgent(service).research(task(query=wrapped, questions=[wrapped]))
        self.assertEqual(service.calls[0][0], "How does Widget interleave steps?")

    def test_expected_paper_sources_are_preferred_over_demo_noise(self):

        query = "Why is scaled dot-product attention divided by sqrt(d_k)?"
        service = FakeKnowledgeService({query: [
            result(1, "research:sampleproject_demo", metadata={"source_type": "repository"}),
            result(2, "research:attention_pdf", metadata={"source_type": "paper"}),
            result(3, "research:attention_pdf", metadata={"source_type": "paper"}),
            result(4, "research:attention_pdf", metadata={"source_type": "paper"}),
            result(5, "research:attention_pdf", metadata={"source_type": "paper"}),
        ]})

        pool = ResearchAgent(service, max_evidence_items=4).research(task(
            questions=[query],
            expected_source_types=[ResearchSourceType.PAPER],
        ))

        self.assertEqual(pool.source_ids(), ["research:attention_pdf"])
        self.assertEqual(len(pool), 4)

    def test_named_entity_sources_are_preferred(self):
        query = "How does Widget interleave steps?"
        service = FakeKnowledgeService({query: [
            result(1, "research:other_pdf", metadata={"source_type": "paper", "source_title": "Other"}),
            result(2, "research:widget_pdf", metadata={"source_type": "paper", "source_title": "Widget Paper"}),
            result(3, "research:widget_pdf", metadata={"source_type": "paper", "source_title": "Widget Paper"}),
            result(4, "research:widget_pdf", metadata={"source_type": "paper", "source_title": "Widget Paper"}),
        ]})

        pool = ResearchAgent(service, max_evidence_items=4).research(task(
            questions=[query],
            expected_source_types=[ResearchSourceType.PAPER],
            entities=["Widget"],
        ))

        self.assertEqual(pool.source_ids(), ["research:widget_pdf"])


if __name__ == "__main__":
    unittest.main()
