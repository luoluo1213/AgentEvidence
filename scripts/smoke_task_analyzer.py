from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings, settings_for_research_llm
from app.research_harness.harness import ResearchHarness
from app.services.ai import AiClient


settings = Settings()

client = AiClient(settings_for_research_llm(settings))

harness = ResearchHarness.from_settings(settings)
harness.begin_case("task-analyzer-smoke")

analyzer = TaskAnalyzerAgent(
    harness.wrap_client(
        client,
        stage="analysis",
        agent="TaskAnalyzer",
    )
)

task = analyzer.analyze(
    "How does ReAct interleave reasoning and acting?"
)

print("\n=== ResearchTask ===")
print(task.model_dump_json(indent=2))

print("\n=== Harness Trace ===")
for trace in harness.diagnostics.traces:
    print(trace)

queries = [
    "Compare self-attention and cross-attention mechanisms within this paper.",
    "Compare the ReAct paper with the Reflexion paper using evidence from both papers.",
]

for query in queries:
    task = analyzer.analyze(query)
    print("\nQUERY:", query)
    print(task.model_dump_json(indent=2))