from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    agent_framework: str = "event_driven_multi_agent"
    agent_max_rounds: int = 8
    agent_max_claims_per_round: int = 4
    agent_max_claims_per_agent: int = 3
    agent_final_acceptance_min_confidence: float = 0.6
    research_mode_enabled: bool = False
    research_max_retrieval_rounds: int = 2
    research_retrieval_top_k: int = 8
    research_max_evidence_items: int = 12
    research_ai_max_tokens: int = 8192
    research_max_provider_retries: int = 2
    research_max_draft_repairs: int = 1
    research_max_retrieval_repairs: int = 0
    research_max_total_llm_calls: int = 24
    research_retry_backoff_seconds: float = 0.4
    research_prompt_token_price_usd: float = 0.0
    research_completion_token_price_usd: float = 0.0
    agent_model_default_provider: str = ""
    agent_model_default_model: str = ""
    agent_model_coordinator_provider: str = ""
    agent_model_coordinator_model: str = ""
    agent_model_understanding_provider: str = ""
    agent_model_understanding_model: str = ""
    agent_model_safety_provider: str = ""
    agent_model_safety_model: str = ""
    agent_model_context_provider: str = ""
    agent_model_context_model: str = ""
    agent_model_response_provider: str = ""
    agent_model_response_model: str = ""
    ai_provider: str = "ollama"
    ai_temperature: float = 0.35
    ai_max_tokens: int = 512
    ai_timeout_seconds: float = 120.0
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mindbridge-qwen2.5-7b-ft:latest"
    finetuned_model_name: str = "mindbridge-qwen2.5-7b-ft:latest"
    finetuned_model_dir: str = "models/mindbridge-qwen2.5-7b-ft"
    finetuned_model_file: str = "mindbridge-qwen2.5-7b-ft-q4_k_m.gguf"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Embedding can use a different OpenAI-compatible endpoint than chat/Q&A.
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    judge_base_url: str = "https://api.openai.com/v1"
    judge_api_key: str = ""
    judge_model: str = "gpt-4o-mini"
    judge_temperature: float = 0.0
    judge_timeout_seconds: float = 90.0
    database_url: str = "mysql+pymysql://mindbridge:mindbridge@127.0.0.1:3306/mindbridge?charset=utf8mb4"
    chat_history_limit: int = 10
    knowledge_top_k: int = 4
    knowledge_candidate_k: int = 16
    knowledge_chunk_size: int = 512
    knowledge_chunk_overlap: int = 64
    knowledge_hybrid_vector_weight: float = 0.65
    knowledge_hybrid_bm25_weight: float = 0.35
    knowledge_rerank_enabled: bool = True
    knowledge_vector_enabled: bool = True
    knowledge_vector_required: bool = False
    chroma_persist_dir: str = "data/chroma"
    chroma_collection_name: str = "mindbridge_knowledge"
    chroma_snapshot_dir: str = "data/chroma-snapshots"
    chroma_snapshot_keep: int = 5
    embedding_timeout_seconds: float = 30.0
    embedding_batch_size: int = 64
    # ChatAnywhere/OpenAI embedding limit is 8192 tokens; keep a conservative char budget.
    embedding_max_input_chars: int = 12000
    rag_eval_dataset: str = "app/rag_eval/mindbridge-rag-eval.json"
    rag_eval_output: str = "target/rag-eval-report.json"
    rag_eval_enabled: bool = False
    rag_eval_exit_after_run: bool = False
    answer_eval_dataset: str = "app/evaluation/mindbridge-response-eval.jsonl"
    answer_eval_output: str = "target/answer-quality-eval-report.json"
    agent_eval_output: str = "target/multi-agent-comparison-report.json"
    excel_path: str = "data/mindbridge-risk-ledger.xlsx"
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_memory_ttl_seconds: int = 86400
    redis_memory_max_messages: int = 40
    redis_socket_timeout_seconds: float = 2.0
    memory_compaction_enabled: bool = True
    memory_compaction_recent_messages: int = 8
    memory_summary_max_chars: int = 500
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: float = 10.0
    alert_email_delivery_mode: str = "log"
    alert_email_from: str = ""
    alert_email_to: str = ""
    alert_email_subject_prefix: str = "[MindBridge 高风险预警]"
    tool_queue_enabled: bool = True
    tool_queue_poll_interval_seconds: float = 1.0
    tool_queue_batch_size: int = 10
    tool_queue_max_attempts: int = 3
    tool_queue_retry_delay_seconds: float = 15.0
    tool_queue_excel_workers: int = 1
    tool_queue_email_workers: int = 2
    alert_email_rate_limit_per_minute: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def resolved_embedding_base_url(self) -> str:
        return (self.embedding_base_url or self.openai_base_url).rstrip("/")

    @property
    def resolved_embedding_api_key(self) -> str:
        return str(self.embedding_api_key or self.openai_api_key or "").strip()


def settings_for_research_llm(settings: Settings) -> Settings:
    return settings.model_copy(update={
        "ai_max_tokens": max(int(settings.ai_max_tokens), int(settings.research_ai_max_tokens)),
    })


@lru_cache
def get_settings() -> Settings:
    return Settings()
