"""
Unit tests for LLM abstraction layer.

All provider calls are mocked — no real API calls, no boto3 dependency.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.base import LLMProvider
from app.llm.client import LLMClient
from app.llm.schemas import (
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    UsageInfo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockProvider(LLMProvider):
    """Minimal in-memory provider for unit tests."""

    def __init__(self, response: LLMResponse | None = None) -> None:
        self._response = response or LLMResponse(
            content="Test response",
            usage=UsageInfo(input_tokens=10, output_tokens=5),
            model="mock-model",
            finish_reason="end_turn",
        )

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_id(self) -> str:
        return "mock-model-v1"

    async def generate(self, messages, *, tools=None, temperature=0.0, max_tokens=4096):
        return self._response

    async def generate_structured(self, messages, output_schema, *, temperature=0.0, max_tokens=4096):
        return output_schema()

    async def stream(self, messages, *, temperature=0.0, max_tokens=4096):
        async def _gen() -> AsyncGenerator[str, None]:
            yield "Hello "
            yield "world"
        return _gen()


@pytest.fixture
def mock_provider():
    return MockProvider()


@pytest.fixture
def llm_client(mock_provider):
    return LLMClient(mock_provider)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_message_roles():
    m = Message(role=MessageRole.USER, content="hello")
    assert m.role == MessageRole.USER


def test_usage_total_tokens():
    u = UsageInfo(input_tokens=100, output_tokens=50)
    assert u.total_tokens == 150


def test_llm_response_is_final_answer():
    r = LLMResponse(content="done", tool_calls=[], finish_reason="end_turn")
    assert r.is_final_answer is True
    assert r.has_tool_calls is False


def test_llm_response_has_tool_calls():
    r = LLMResponse(
        content=None,
        tool_calls=[ToolCall(id="1", name="calculate_tax", arguments={"income": 500000})],
    )
    assert r.has_tool_calls is True
    assert r.is_final_answer is False


# ---------------------------------------------------------------------------
# LLMClient tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_generate_returns_response(llm_client):
    messages = [Message(role=MessageRole.USER, content="What is my tax?")]
    response = await llm_client.generate(messages)
    assert isinstance(response, LLMResponse)
    assert response.content == "Test response"


@pytest.mark.asyncio
async def test_client_passes_tools_to_provider(mock_provider):
    mock_provider.generate = AsyncMock(return_value=LLMResponse(content="ok"))
    client = LLMClient(mock_provider)
    tools = [ToolDefinition(name="calc", description="calc", input_schema={})]
    await client.generate([Message(role=MessageRole.USER, content="hi")], tools=tools)
    mock_provider.generate.assert_called_once()
    _, kwargs = mock_provider.generate.call_args
    assert kwargs["tools"] == tools


def test_client_exposes_provider_name(llm_client):
    assert llm_client.provider_name == "mock"


def test_client_exposes_model_id(llm_client):
    assert llm_client.model_id == "mock-model-v1"


# ---------------------------------------------------------------------------
# get_llm_client factory tests
# ---------------------------------------------------------------------------


def test_get_llm_client_raises_without_provider():
    from app.llm.client import get_llm_client

    get_llm_client.cache_clear()
    with patch("app.llm.client.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(llm_provider=None)
        with pytest.raises(RuntimeError, match="LLM_PROVIDER is not configured"):
            get_llm_client()
    get_llm_client.cache_clear()


def test_get_llm_client_raises_for_unknown_provider():
    from app.llm.client import get_llm_client

    get_llm_client.cache_clear()
    with patch("app.llm.client.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(llm_provider="unknown_provider")
        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
            get_llm_client()
    get_llm_client.cache_clear()
