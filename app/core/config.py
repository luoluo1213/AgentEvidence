from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---------- API ----------
    app_name: str = "AgentEvidence"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------- Uploads ----------
    research_upload_dir: str = "data/uploads"
    research_pdf_max_bytes: int = 20 * 1024 * 1024

    # ---------- Multi-Agent Runtime ----------
    agent_max_rounds: int = 8
    agent_max_claims_per_round: int = 4
    agent_max_claims_per_agent: int = 8
    agent_final_acceptance_min_confidence: float = 0.6

    # ---------- LLM ----------
    ai_provider: str = "openai"
    ai_temperature: float = 0.35
    ai_max_tokens: int = 8192
    ai_timeout_seconds: float = 120.0

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "deepseek-chat"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""

    # ---------- Research ----------
    research_retrieval_top_k: int = 5
    research_max_evidence_items: int = 6
    research_ai_max_tokens: int = 8192

    # ---------- Harness ----------
    research_max_provider_retries: int = 2
    research_max_draft_repairs: int = 1
    research_max_retrieval_repairs: int = 0
    research_max_total_llm_calls: int = 24
    research_retry_backoff_seconds: float = 0.4

    research_prompt_token_price_usd: float = 0.0
    research_completion_token_price_usd: float = 0.0

    # ---------- Database ----------
    database_url: str = "sqlite:///./data/agentevidence.db"

    # ---------- Retrieval / RAG ----------
    knowledge_top_k: int = 4
    knowledge_candidate_k: int = 16
    knowledge_chunk_size: int = 1800
    knowledge_chunk_overlap: int = 250

    knowledge_hybrid_vector_weight: float = 0.65
    knowledge_hybrid_bm25_weight: float = 0.35
    knowledge_rerank_enabled: bool = True

    knowledge_vector_enabled: bool = True
    knowledge_vector_required: bool = False

    chroma_persist_dir: str = "data/chroma"
    chroma_collection_name: str = "agentevidence_knowledge"
    chroma_snapshot_dir: str = "data/chroma-snapshots"
    chroma_snapshot_keep: int = 5

    embedding_base_url: str = ""
    embedding_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_timeout_seconds: float = 30.0
    embedding_batch_size: int = 64
    embedding_max_input_chars: int = 12000

    # ---------- Memory ----------
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_memory_ttl_seconds: int = 86400
    redis_memory_max_messages: int = 40
    redis_socket_timeout_seconds: float = 2.0

    memory_compaction_enabled: bool = True
    memory_compaction_recent_messages: int = 8
    memory_summary_max_chars: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def resolved_embedding_base_url(self) -> str:
        return (self.embedding_base_url or self.openai_base_url).rstrip("/")

    @property
    def resolved_embedding_api_key(self) -> str:
        return str(
            self.embedding_api_key or self.openai_api_key or ""
        ).strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def settings_for_research_llm(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "ai_max_tokens": max(
                int(settings.ai_max_tokens),
                int(settings.research_ai_max_tokens),
            )
        }
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
