from app.agents.evidence_verifier import EvidenceVerificationResult
from app.agents.research_draft_generator import (
    ResearchClaim,
    ResearchDraft,
)
from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    ResearchSourceType,
    ResearchTask,
    ResearchTaskType,
)
from app.research_harness.harness import (
    HarnessEvidenceVerifier,
    ResearchHarness,
)
from app.services.research_pipeline import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    build_final_research_result,
)


class FakeInsufficientVerifier:
    def verify(
        self,
        task,
        draft,
        evidence_pool,
    ):
        return EvidenceVerificationResult(
            sufficient=False,
            supported_points=[],
            missing_points=[
                "Missing direct evidence for the comparison."
            ],
            weak_evidence_ids=[],
            suggested_queries=[
                "direct comparison evidence"
            ],
            reason="Evidence is insufficient.",
        )


def main():
    # --------------------------------------------------
    # 1. 构造一个最小 comparison task
    # --------------------------------------------------
    task = ResearchTask(
        task_id="test-verification-gate",
        query="Compare ReAct and Reflexion.",
        task_type=ResearchTaskType.COMPARISON,
        entities=[
            "ReAct",
            "Reflexion",
        ],
        research_questions=[
            "How does ReAct improve agent behavior?",
            "How does Reflexion improve agent behavior?",
        ],
        expected_source_types=[
            ResearchSourceType.PAPER,
        ],
        requires_comparison=True,
        requires_multiple_sources=True,
    )

    # --------------------------------------------------
    # 2. 构造最小 EvidencePool
    # --------------------------------------------------
    evidence_pool = EvidencePool(
        items=[
            EvidenceItem(
                evidence_id="research:react:test-1",
                source_id="research:react",
                source_title="ReAct",
                source_type=ResearchSourceType.PAPER,
                section="Method",
                content=(
                    "ReAct interleaves reasoning and acting "
                    "during interaction with an environment."
                ),
                query_used="ReAct mechanism",
                retrieval_round=1,
                metadata={},
            ),
            EvidenceItem(
                evidence_id="research:reflexion:test-1",
                source_id="research:reflexion",
                source_title="Reflexion",
                source_type=ResearchSourceType.PAPER,
                section="Method",
                content=(
                    "Reflexion converts environmental feedback "
                    "into verbal reflection for subsequent trials."
                ),
                query_used="Reflexion mechanism",
                retrieval_round=1,
                metadata={},
            ),
        ]
    )

    # --------------------------------------------------
    # 3. 构造一个原本看起来正常的 Draft
    # --------------------------------------------------
    draft = ResearchDraft(
        answer=(
            "ReAct improves behavior through within-trajectory "
            "reasoning and acting, while Reflexion uses verbal "
            "reflection across trials."
        ),
        claims=[
            ResearchClaim(
                claim_id="claim-1",
                text=(
                    "ReAct interleaves reasoning and acting."
                ),
                evidence_ids=[
                    "research:react:test-1"
                ],
            ),
            ResearchClaim(
                claim_id="claim-2",
                text=(
                    "Reflexion uses verbal reflection "
                    "across trials."
                ),
                evidence_ids=[
                    "research:reflexion:test-1"
                ],
            ),
        ],
    )

    # --------------------------------------------------
    # 4. 创建 Harness
    # --------------------------------------------------
    harness = ResearchHarness()
    harness.begin_case(
        "verification-gate-test"
    )

    # --------------------------------------------------
    # 5. 强制 Verifier 返回 insufficient
    # --------------------------------------------------
    verifier = HarnessEvidenceVerifier(
        FakeInsufficientVerifier(),
        harness,
    )

    verification = verifier.verify(
        task,
        draft,
        evidence_pool,
    )

    # --------------------------------------------------
    # 6. 构造 FinalResearchResult
    # --------------------------------------------------
    result = build_final_research_result(
        task.query,
        task,
        evidence_pool,
        draft,
        verification,
    )

    # --------------------------------------------------
    # 7. 输出结果
    # --------------------------------------------------
    print(
        "sufficient =",
        verification.sufficient,
    )

    print(
        "answer =",
        result.answer,
    )

    print(
        "original draft =",
        result.draft.answer,
    )

    print(
        "result_status =",
        harness.diagnostics.result_status,
    )

    print(
        "evidence_insufficient =",
        harness.diagnostics.evidence_insufficient,
    )

    print(
        "fallback_used =",
        harness.diagnostics.fallback_used,
    )

    # --------------------------------------------------
    # 8. 真正验证 Gate
    # --------------------------------------------------
    assert verification.sufficient is False

    assert (
        result.answer
        == INSUFFICIENT_EVIDENCE_ANSWER
    )

    # 原始 draft 必须仍然保留，
    # 后续 Retrieval Repair 会需要它。
    assert (
        result.draft.answer
        != INSUFFICIENT_EVIDENCE_ANSWER
    )

    assert (
        harness.diagnostics.evidence_insufficient
        is True
    )

    assert (
        harness.diagnostics.result_status
        == "evidence_insufficient"
    )

    assert (
        harness.diagnostics.fallback_used
        is False
    )

    print("\nverification gate PASS")


if __name__ == "__main__":
    main()