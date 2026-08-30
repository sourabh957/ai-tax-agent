"""
LangChain LLM client — Milestone 24.

Implements the same LLMProvider interface as BedrockProvider,
but uses LangChain's ChatBedrock internally.

This allows us to swap the LLM backend by changing one line:

    # Raw (Milestone 4):
    LLM_PROVIDER=bedrock

    # LangChain-backed (Milestone 24):
    LLM_PROVIDER=langchain_bedrock

The agent loop, tools, and all application code remain unchanged.

Why LangChain here?
    - ChatBedrock handles boto3 session, retry, streaming, and token counting
    - .with_structured_output() reduces our JSON parsing boilerplate
    - Makes multi-provider switching (bedrock → openai) easier in the future
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.schemas import (
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    UsageInfo,
)

logger = logging.getLogger(__name__)


class LangChainBedrockProvider(LLMProvider):
    """
    LangChain-backed Bedrock provider.

    Internally uses langchain_aws.ChatBedrock.
    Exposes the same LLMProvider interface as BedrockProvider —
    the agent loop cannot tell the difference.
    """

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.bedrock_model_id:
            raise RuntimeError(
                "BEDROCK_MODEL_ID is required when using LangChain Bedrock provider."
            )
        if not settings.aws_region:
            raise RuntimeError("AWS_REGION is required.")

        self._model_id = settings.bedrock_model_id
        self._region = settings.aws_region
        self._llm = self._build_llm()

    def _build_llm(self):
        try:
            from langchain_aws import ChatBedrock
        except ImportError:
            raise RuntimeError(
                "langchain-aws is not installed. Run: pip install langchain-aws"
            )
        return ChatBedrock(
            model_id=self._model_id,
            region_name=self._region,
            model_kwargs={"temperature": 0.0, "max_tokens": 4096},
        )

    @property
    def provider_name(self) -> str:
        return "langchain_bedrock"

    @property
    def model_id(self) -> str:
        return self._model_id

    def _to_lc_messages(self, messages: list[Message]):
        """Convert our Message schema to LangChain message objects."""
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
        )

        lc_messages = []
        for m in messages:
            if m.role == MessageRole.SYSTEM:
                lc_messages.append(SystemMessage(content=m.content))
            elif m.role == MessageRole.USER:
                lc_messages.append(HumanMessage(content=m.content))
            elif m.role == MessageRole.ASSISTANT:
                lc_messages.append(AIMessage(content=m.content))
        return lc_messages

    def _build_lc_tools(self, tools: list[ToolDefinition]):
        """Convert our ToolDefinition list to LangChain tool format."""
        from langchain_core.tools import StructuredTool
        from pydantic import create_model

        lc_tools = []
        for t in tools:
            # Dynamically create a Pydantic model from the JSON schema
            # (simplified — production would use a full JSON schema parser)
            lc_tools.append(
                StructuredTool.from_function(
                    func=lambda **kwargs: kwargs,  # placeholder — not actually called
                    name=t.name,
                    description=t.description,
                )
            )
        return lc_tools

    def _parse_response(self, response) -> LLMResponse:
        """Parse a LangChain AIMessage into our LLMResponse schema."""
        from langchain_core.messages import AIMessage

        content = None
        tool_calls: list[ToolCall] = []

        if isinstance(response, AIMessage):
            content = response.content if isinstance(response.content, str) else None

            # Handle native tool calls from LangChain
            for tc in (response.tool_calls or []):
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("name", ""),
                    arguments=tc.get("args", {}),
                ))

        # Usage metadata (LangChain attaches this to the response)
        usage_meta = getattr(response, "usage_metadata", None) or {}
        usage = UsageInfo(
            input_tokens=usage_meta.get("input_tokens", 0),
            output_tokens=usage_meta.get("output_tokens", 0),
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            model=self._model_id,
            finish_reason=getattr(response, "stop_reason", ""),
        )

    async def generate(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import asyncio

        lc_messages = self._to_lc_messages(messages)

        llm = self._llm
        if tools:
            lc_tools = self._build_lc_tools(tools)
            llm = llm.bind_tools(lc_tools)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: llm.invoke(lc_messages)
        )
        return self._parse_response(response)

    async def generate_structured(
        self,
        messages: list[Message],
        output_schema: type,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        """
        Use LangChain's .with_structured_output() for reliable Pydantic parsing.

        This is one of LangChain's strongest features — it uses the model's
        native function-calling to guarantee structured output instead of
        parsing JSON from the response text.
        """
        import asyncio
        from pydantic import ValidationError

        lc_messages = self._to_lc_messages(messages)
        structured_llm = self._llm.with_structured_output(output_schema)

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, lambda: structured_llm.invoke(lc_messages)
            )
            return result
        except ValidationError as exc:
            raise ValueError(
                f"Structured output validation failed for {output_schema.__name__}: {exc}"
            ) from exc

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        import asyncio

        lc_messages = self._to_lc_messages(messages)

        async def _generate():
            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(
                None, lambda: list(self._llm.stream(lc_messages))
            )
            for chunk in chunks:
                text = chunk.content if isinstance(chunk.content, str) else ""
                if text:
                    yield text

        return _generate()
