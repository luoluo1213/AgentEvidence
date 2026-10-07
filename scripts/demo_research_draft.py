from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings
from app.services.ai import AiClient
from scripts.demo_research_agent import build_local_knowledge_service
from scripts.demo_task_analyzer import DemoMockAiClient


class DemoGroundedDraftClient:
    """Deterministic demo provider that cites IDs from the real retrieved pool."""

    def complete(self, messages) -> str:
        payload = json.loads(messages[-1].content)
        query = payload["task"]["query"]
        items = payload["evidence"]
        if "比较" in query and "ReAct" in query and "Reflexion" in query:
            react = next((item for item in items if item["source_id"] == "research:react"), None)
            reflexion = next((item for item in items if item["source_id"] == "research:reflexion"), None)
            if react and reflexion:
                return json.dumps({
                    "answer": (
                        "ReAct 的机制是把行动后的环境 observation 放回连续的推理—行动轨迹中，使模型能够根据刚得到的反馈调整下一步判断与行动。"
                        "因此，反馈主要在同一次交互过程中即时参与后续决策。\n\n"
                        "Reflexion 的机制则是在一次尝试得到成功或失败反馈后，将经验概括为语言形式的 reflection，并把这种反思保存在记忆中，供后续 trial 使用。"
                        "反馈不只是下一步 observation，还会形成跨尝试可复用的语言经验。\n\n"
                        "两者都让执行反馈影响后续行为，但作用层级不同：ReAct 强调当前轨迹内 observation、reasoning 与 action 的交错，"
                        "Reflexion 强调尝试结束后的反思以及跨 trial 的记忆更新。综合来看，前者偏向即时闭环调整，后者偏向从失败中形成可延续的改进线索。"
                    ),
                    "claims": [
                        {"claim_id": "claim-react", "text": "ReAct 将 observation 作为后续推理和行动的输入。", "evidence_ids": [react["evidence_id"]]},
                        {"claim_id": "claim-reflexion", "text": "Reflexion 根据执行反馈生成语言反思，并在后续尝试中使用。", "evidence_ids": [reflexion["evidence_id"]]},
                        {"claim_id": "claim-comparison", "text": "ReAct 和 Reflexion 都利用反馈，但 ReAct 侧重交错的 observation，Reflexion 侧重跨尝试的反思记忆。", "evidence_ids": [react["evidence_id"], reflexion["evidence_id"]]},
                    ],
                }, ensure_ascii=False)

        execute_actions = _by_symbol(items, "DefaultAgent.execute_actions")
        environment_execute = _by_symbol(items, "LocalEnvironment.execute")
        add_messages = _by_symbol(items, "DefaultAgent.add_messages")
        selected = [item for item in (execute_actions, environment_execute, add_messages) if item]
        if selected:
            claims = []
            if execute_actions:
                claims.append({
                    "claim_id": "claim-action",
                    "text": "DefaultAgent.execute_actions 逐个调用环境执行 action，并把输出格式化为 observation 消息。",
                    "evidence_ids": [execute_actions["evidence_id"]],
                })
            if environment_execute:
                claims.append({
                    "claim_id": "claim-environment",
                    "text": "LocalEnvironment.execute 执行命令并把执行结果组织为字典。",
                    "evidence_ids": [environment_execute["evidence_id"]],
                })
            if add_messages:
                claims.append({
                    "claim_id": "claim-history",
                    "text": "DefaultAgent.add_messages 通过扩展 messages 将新消息加入线性 history。",
                    "evidence_ids": [add_messages["evidence_id"]],
                })
            return json.dumps({
                "answer": (
                    "执行链从 DefaultAgent.step 开始：它先调用 query 获得模型消息，再把该消息交给 execute_actions。"
                    "execute_actions 从消息的 actions 字段读取一个或多个 action，并逐个调用环境的 execute 方法。\n\n"
                    "在本地环境中，LocalEnvironment.execute 取得 command 和工作目录，执行命令后把输出、返回码等信息组织成结果字典，"
                    "再由 agent 按 observation 模板形成新的消息。最后，DefaultAgent.add_messages 使用 messages.extend 将这些 observation 消息追加到线性消息历史中。\n\n"
                    "因此，action 执行与 history 更新不是两个孤立步骤，而是一条连续链路：模型产生 action，环境返回结构化执行结果，"
                    "agent 将结果转换为 observation 并追加到 messages，下一轮 query 随即能够看到此前的执行反馈。"
                ),
                "claims": claims,
            }, ensure_ascii=False)

        return json.dumps({"answer": "无法基于当前证据可靠生成回答", "claims": []}, ensure_ascii=False)


class DemoEvidenceVerifierClient:
    """Deterministic verifier for demonstrating the real draft/evidence wiring."""

    def complete(self, messages) -> str:
        payload = json.loads(messages[-1].content)
        evidence_ids = {item["evidence_id"] for item in payload["evidence"]}
        claims = payload["draft"]["claims"]
        missing = [
            f"{claim['claim_id']} 缺少可用引用。"
            for claim in claims
            if not claim["evidence_ids"] or not set(claim["evidence_ids"]).issubset(evidence_ids)
        ]
        return json.dumps({
            "sufficient": bool(claims) and not missing,
            "supported_points": [claim["text"] for claim in claims if not missing],
            "missing_points": missing,
            "weak_evidence_ids": [],
            "suggested_queries": [payload["task"]["query"]] if missing else [],
            "reason": "所有 demo claim 均引用了本次真实 EvidencePool 中的证据。" if not missing else "存在缺失引用。",
        }, ensure_ascii=False)


def _by_symbol(items: list[dict], symbol: str) -> dict | None:
    return next((item for item in items if item.get("symbol") == symbol), None)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Generate an evidence-grounded ResearchDraft.")
    parser.add_argument("query")
    parser.add_argument("--mock", action="store_true", help="Use deterministic local providers with the real corpus.")
    args = parser.parse_args(argv)

    settings = Settings(knowledge_vector_enabled=False)
    use_mock = args.mock or settings.ai_provider.lower() == "mock"
    analyzer_client = DemoMockAiClient() if use_mock else AiClient(settings)
    draft_client = DemoGroundedDraftClient() if use_mock else AiClient(settings)
    verifier_client = DemoEvidenceVerifierClient() if use_mock else AiClient(settings)
    task = TaskAnalyzerAgent(analyzer_client).analyze(args.query)
    knowledge, db = build_local_knowledge_service(settings)
    try:
        pool = ResearchAgent(
            knowledge,
            top_k=settings.research_retrieval_top_k,
            max_evidence_items=settings.research_max_evidence_items,
        ).research(task)
        draft = ResearchDraftGenerator(draft_client).generate(task, pool)
        verification = EvidenceVerifier(verifier_client).verify(task, draft, pool)
    finally:
        db.close()

    print("=== ResearchDraft ===")
    print(json.dumps(draft.model_dump(), ensure_ascii=False, indent=2))
    print("\n=== Claim -> Evidence IDs ===")
    for claim in draft.claims:
        print(f"{claim.claim_id}: {claim.evidence_ids}")
    print("\n=== Verification ===")
    print(json.dumps(verification.model_dump(), ensure_ascii=False, indent=2))
    print(f"\nsufficient:\n{str(verification.sufficient).lower()}")
    print(f"supported_points:\n{json.dumps(verification.supported_points, ensure_ascii=False)}")
    print(f"missing_points:\n{json.dumps(verification.missing_points, ensure_ascii=False)}")
    print(f"weak_evidence_ids:\n{json.dumps(verification.weak_evidence_ids, ensure_ascii=False)}")
    print(f"suggested_queries:\n{json.dumps(verification.suggested_queries, ensure_ascii=False)}")
    print(f"reason:\n{verification.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
