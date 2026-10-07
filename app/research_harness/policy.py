from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class ExecutionPolicy:
    max_provider_retries: int = 2
    max_draft_repairs: int = 1
    max_retrieval_repairs: int = 0
    max_total_llm_calls: int = 24
    request_timeout_seconds: float = 120.0
    retry_backoff_seconds: float = 0.4
    prompt_token_price_usd: float = 0.0
    completion_token_price_usd: float = 0.0

    @classmethod
    def from_settings(cls, settings: Settings) -> "ExecutionPolicy":
        return cls(
            max_provider_retries=int(getattr(settings, "research_max_provider_retries", 2)),
            max_draft_repairs=int(getattr(settings, "research_max_draft_repairs", 1)),
            max_retrieval_repairs=int(getattr(settings, "research_max_retrieval_repairs", 0)),
            max_total_llm_calls=int(getattr(settings, "research_max_total_llm_calls", 24)),
            request_timeout_seconds=float(getattr(settings, "ai_timeout_seconds", 120.0)),
            retry_backoff_seconds=float(getattr(settings, "research_retry_backoff_seconds", 0.4)),
            prompt_token_price_usd=float(getattr(settings, "research_prompt_token_price_usd", 0.0)),
            completion_token_price_usd=float(getattr(settings, "research_completion_token_price_usd", 0.0)),
        )
