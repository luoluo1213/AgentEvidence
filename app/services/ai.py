from __future__ import annotations

import httpx

from app.core.config import Settings
from app.schemas.dtos import AiMessage


class AiClient:
    """
    Thin OpenAI-compatible LLM client.

    Provider retry, execution budget and tracing are handled
    by ResearchHarness, not by this client.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_usage: dict = {}

    def complete(self, messages: list[AiMessage]) -> str:
        if self.settings.ai_provider.lower() != "openai":
            raise ValueError(
                f"unsupported ai_provider: {self.settings.ai_provider}"
            )

        response = httpx.post(
            f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization":
                    f"Bearer {self.settings.openai_api_key}"
            },
            json={
                "model": self.settings.openai_model,
                "messages": [
                    message.model_dump()
                    for message in messages
                ],
                "temperature": self.settings.ai_temperature,
                "max_tokens": self.settings.ai_max_tokens,
            },
            timeout=self.settings.ai_timeout_seconds,
        )

        response.raise_for_status()

        payload = response.json()
        self.last_usage = payload.get("usage") or {}

        return payload["choices"][0]["message"]["content"]