"""
Abstract LLM provider interface.

All concrete providers (Bedrock, OpenAI, Local) must implement this.
The agent and all application code depend only on this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from app.llm.schemas import LLMResponse, Message, ToolDefinition


class LLMProvider(ABC):
    """
    Abstract base for all LLM providers.

    Implementations:
        app.llm.providers.bedrock.BedrockProvider
    """

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Send messages to the LLM and return a structured response.

        Args:
            messages: Conversation history including system prompt.
            tools: Tool definitions the LLM may call (optional).
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Maximum tokens in the response.

        Returns:
            LLMResponse with content and/or tool_calls.
        """

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[Message],
        output_schema: type,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        """
        Generate a response and parse it into a Pydantic model.

        Args:
            messages: Conversation history.
            output_schema: A Pydantic BaseModel class.

        Returns:
            An instance of output_schema.

        Raises:
            ValueError: If the LLM output cannot be parsed into the schema.
        """

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """
        Stream text tokens from the LLM.

        Yields:
            Individual text chunks as they arrive.
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name, e.g. 'bedrock' or 'openai'."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """The specific model being used, e.g. the Bedrock model ARN."""
