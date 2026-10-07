from enum import Enum


class ResearchArtifactKind(str, Enum):
    TASK_ANALYSIS = "research_task_analysis"
    RETRIEVAL_QUERY = "research_retrieval_query"
    EVIDENCE_BUNDLE = "research_evidence_bundle"
    EVIDENCE_VERIFICATION = "research_evidence_verification"
    RETRIEVAL_REPAIR = "research_retrieval_repair"
    RESPONSE_DRAFT = "research_response_draft"
    FINAL_RESPONSE = "research_final_response"
