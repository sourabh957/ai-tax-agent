"""
LLMClient — the single entry point for all LLM operations in the application.

Usage:
    from app.llm.client import get_llm_client

    client = get_llm_client()
    response = await client.generate(messages)

The client reads LLM_PROVIDER from settings and instantiates the correct provider.
New providers can be added to _build_provider() without changing any agent code.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.schemas import LLMResponse, Message, ToolDefinition

logger = logging.getLogger(__name__)


def _build_provider(provider_name: str) -> LLMProvider:
    if provider_name == "bedrock":
        from app.llm.providers.bedrock import BedrockProvider
        return BedrockProvider()

    if provider_name == "langchain_bedrock":
        from app.llm.providers.langchain_bedrock import LangChainBedrockProvider
        return LangChainBedrockProvider()

    if provider_name == "mock":
        from app.llm.providers.mock import MockProvider
        return MockProvider()

    # Future providers:
    # if provider_name == "openai":
    #     from app.llm.providers.openai import OpenAIProvider
    #     return OpenAIProvider()

    raise ValueError(
        f"Unknown LLM_PROVIDER='{provider_name}'. "
        "Supported values: bedrock, langchain_bedrock. "
        "Add a new provider under app/llm/providers/ to extend."
    )


class LLMClient:
    """
    Provider-agnostic LLM client.

    The agent depends on this class — never on a concrete provider directly.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        logger.info(
            "LLMClient initialized [provider=%s model=%s]",
            provider.provider_name,
            provider.model_id,
        )

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    @property
    def model_id(self) -> str:
        return self._provider.model_id

    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        logger.debug(
            "LLM generate [provider=%s messages=%d tools=%d]",
            self.provider_name,
            len(messages),
            len(tools) if tools else 0,
        )
        return await self._provider.generate(
            messages, tools=tools, temperature=temperature, max_tokens=max_tokens
        )

    async def generate_structured(
        self,
        messages: list[Message],
        output_schema: type,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        return await self._provider.generate_structured(
            messages, output_schema, temperature=temperature, max_tokens=max_tokens
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        return self._provider.stream(
            messages, temperature=temperature, max_tokens=max_tokens
        )


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """
    Returns the singleton LLMClient.

    Raises:
        RuntimeError: If LLM_PROVIDER is not configured.
        ValueError: If an unsupported provider is specified.
    """
    settings = get_settings()
    if not settings.llm_provider:
        raise RuntimeError(
            "LLM_PROVIDER is not configured. "
            "Set LLM_PROVIDER in .env (e.g. LLM_PROVIDER=bedrock)."
        )
    provider = _build_provider(settings.llm_provider)
    return LLMClient(provider)
