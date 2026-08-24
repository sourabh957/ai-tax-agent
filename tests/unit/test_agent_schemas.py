"""
Unit tests for agent decision schemas (structured output).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.schemas import (
    DecisionType,
    FinalAnswer,
    ToolCallDecision,
    parse_agent_decision,
)


def test_final_answer_parses():
    d = parse_agent_decision({"type": "final_answer", "answer": "Your tax is ₹50,000."})
    assert isinstance(d, FinalAnswer)
    assert d.type == DecisionType.FINAL_ANSWER
    assert "₹50,000" in d.answer


def test_tool_call_decision_parses():
    d = parse_agent_decision(
        {
            "type": "tool_call",
            "tool_name": "calculate_tax",
            "arguments": {"income": 1000000},
        }
    )
    assert isinstance(d, ToolCallDecision)
    assert d.tool_name == "calculate_tax"
    assert d.arguments["income"] == 1000000


def test_final_answer_requires_answer():
    with pytest.raises(ValidationError):
        FinalAnswer(answer="")  # min_length=1


def test_tool_call_requires_tool_name():
    with pytest.raises(ValidationError):
        ToolCallDecision(tool_name="")  # min_length=1


def test_tool_name_strips_whitespace():
    d = ToolCallDecision(tool_name="  calculate_tax  ", arguments={})
    assert d.tool_name == "calculate_tax"


def test_tool_name_rejects_internal_spaces():
    with pytest.raises(ValidationError):
        ToolCallDecision(tool_name="calculate tax", arguments={})


def test_parse_raises_on_unknown_type():
    with pytest.raises((ValidationError, Exception)):
        parse_agent_decision({"type": "unknown", "data": "x"})


def test_final_answer_citations_default_empty():
    d = FinalAnswer(answer="Tax is ₹0")
    assert d.citations == []
