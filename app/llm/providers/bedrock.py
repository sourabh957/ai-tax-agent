"""
Amazon Bedrock LLM provider.

Uses the boto3 Bedrock Runtime converse API — the current recommended
interface for conversational + tool-capable models.

Configuration required:
    LLM_PROVIDER=bedrock
    BEDROCK_MODEL_ID=<model-id>    e.g. anthropic.claude-3-5-sonnet-20241022-v2:0
    AWS_REGION=<region>

AWS credentials are sourced from the standard AWS credential chain:
    - IAM task role (production / ECS)
    - AWS CLI profile (local development)
    - Environment variables (CI)

NEVER hardcode AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY.
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


class BedrockProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()

        if not settings.bedrock_model_id:
            raise RuntimeError(
                "BEDROCK_MODEL_ID is required when LLM_PROVIDER=bedrock. "
                "Example: anthropic.claude-3-5-sonnet-20241022-v2:0"
            )
        if not settings.aws_region:
            raise RuntimeError("AWS_REGION is required when LLM_PROVIDER=bedrock.")

        self._model_id = settings.bedrock_model_id
        self._region = settings.aws_region
        self._client = self._build_client()

    def _build_client(self):
        """
        Build a boto3 Bedrock Runtime client using the AWS credential chain.
        Never passes access keys directly.
        """
        try:
            import boto3

            return boto3.client("bedrock-runtime", region_name=self._region)
        except ImportError:
            raise RuntimeError(
                "boto3 is not installed. Add it to requirements.txt and reinstall."
            )

    @property
    def provider_name(self) -> str:
        return "bedrock"

    @property
    def model_id(self) -> str:
        return self._model_id

    def _build_converse_messages(self, messages: list[Message]) -> list[dict]:
        """Convert our Message schema to Bedrock converse API format."""
        converse_messages = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # System messages are passed separately in the converse API
                continue
            converse_messages.append(
                {
                    "role": msg.role.value,
                    "content": [{"text": msg.content}],
                }
            )
        return converse_messages

    def _extract_system(self, messages: list[Message]) -> list[dict] | None:
        system_parts = [
            {"text": m.content}
            for m in messages
            if m.role == MessageRole.SYSTEM
        ]
        return system_parts if system_parts else None

    def _build_tool_config(
        self, tools: list[ToolDefinition]
    ) -> dict[str, Any] | None:
        if not tools:
            return None
        return {
            "tools": [
                {
                    "toolSpec": {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": {"json": t.input_schema},
                    }
                }
                for t in tools
            ]
        }

    def _parse_converse_response(self, raw: dict) -> LLMResponse:
        """Parse Bedrock converse API response into our LLMResponse schema."""
        usage_raw = raw.get("usage", {})
        usage = UsageInfo(
            input_tokens=usage_raw.get("inputTokens", 0),
            output_tokens=usage_raw.get("outputTokens", 0),
        )
        finish_reason = raw.get("stopReason", "")
        output = raw.get("output", {}).get("message", {})
        content_blocks = output.get("content", [])

        text_parts = []
        tool_calls = []

        for block in content_blocks:
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append(
                    ToolCall(
                        id=tu.get("toolUseId", ""),
                        name=tu.get("name", ""),
                        arguments=tu.get("input", {}),
                    )
                )

        return LLMResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            usage=usage,
            model=self._model_id,
            finish_reason=finish_reason,
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

        converse_messages = self._build_converse_messages(messages)
        system = self._extract_system(messages)

        kwargs: dict[str, Any] = {
            "modelId": self._model_id,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            kwargs["system"] = system
        tool_config = self._build_tool_config(tools or [])
        if tool_config:
            kwargs["toolConfig"] = tool_config

        logger.debug("Calling Bedrock converse [model=%s]", self._model_id)

        # boto3 is synchronous; run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None, lambda: self._client.converse(**kwargs)
        )
        return self._parse_converse_response(raw)

    async def generate_structured(
        self,
        messages: list[Message],
        output_schema: type,
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Any:
        from pydantic import BaseModel, ValidationError

        response = await self.generate(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        if not response.content:
            raise ValueError("LLM returned empty content for structured output request.")

        # Strip markdown code fences if present
        raw_text = response.content.strip()
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            raw_text = "\n".join(lines[1:-1]) if len(lines) > 2 else raw_text

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM returned non-JSON content for structured output: {exc}\n"
                f"Raw content: {response.content[:200]}"
            ) from exc

        if not (isinstance(output_schema, type) and issubclass(output_schema, BaseModel)):
            raise TypeError("output_schema must be a Pydantic BaseModel subclass.")

        try:
            return output_schema.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"LLM output did not match schema {output_schema.__name__}: {exc}"
            ) from exc

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        import asyncio

        converse_messages = self._build_converse_messages(messages)
        system = self._extract_system(messages)

        kwargs: dict[str, Any] = {
            "modelId": self._model_id,
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system:
            kwargs["system"] = system

        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None, lambda: self._client.converse_stream(**kwargs)
        )

        async def _generate():
            stream = raw.get("stream", [])
            for event in stream:
                delta = event.get("contentBlockDelta", {}).get("delta", {})
                text = delta.get("text", "")
                if text:
                    yield text

        return _generate()
