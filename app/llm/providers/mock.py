from typing import Any
from collections.abc import AsyncGenerator
import json
from app.llm.base import LLMProvider
from app.llm.schemas import LLMResponse, Message, ToolDefinition, Usage

class MockProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_id(self) -> str:
        return "mock-model"

    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return LLMResponse(
            text="This is a mock LLM response because AWS credentials (Bedrock) are not configured.",
            tool_calls=[],
            usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0),
            raw_response={},
        )

    async def generate_structured(
        self,
        messages: list[Message],
        output_schema: type,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        return output_schema()

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        yield "This is a mock LLM response."
