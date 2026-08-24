"""
Raw Single-Agent Loop.

This is the core of the AI Tax Agent. It is intentionally implemented
WITHOUT LangChain or LangGraph so the architecture is fully understood
before frameworks are introduced (Milestones 23-26).

Loop:
    1.  Build messages (system prompt + conversation history + observations)
    2.  Call LLM → LLMResponse
    3.  Parse structured AgentDecision from LLM output
    4.  If FinalAnswer   → done
    5.  If ToolCall      → validate → execute → record observation → goto 1
    6.  Safety checks    → terminate if limits exceeded

Safety limits (all configurable via .env):
    MAX_AGENT_ITERATIONS  — hard stop on total loop iterations
    MAX_TOOL_CALLS        — prevent runaway tool usage
    MAX_LLM_CALLS         — control API cost per request

The LLM never directly modifies state or executes tools.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.agents.schemas import (
    AgentDecision,
    FinalAnswer,
    ToolCallDecision,
    parse_agent_decision,
)
from app.agents.state import AgentState
from app.core.config import get_settings
from app.llm.client import LLMClient
from app.llm.schemas import Message, MessageRole
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an AI Tax Agent specialising in Indian income tax.

You help users understand their tax situation, compare tax regimes, \
calculate tax liability, and identify deductions.

You have access to tools. Use them for all calculations — never calculate tax yourself.

At each step you MUST respond with a valid JSON object matching one of these schemas:

1. If you have enough information to answer the user:
{
  "type": "final_answer",
  "answer": "<your complete answer>",
  "reasoning": "<how you arrived at the answer>",
  "citations": ["<source1>", "<source2>"]
}

2. If you need to call a tool first:
{
  "type": "tool_call",
  "tool_name": "<exact tool name>",
  "arguments": { <tool arguments> },
  "reasoning": "<why you need this tool>"
}

Rules:
- Respond ONLY with the JSON object. No preamble, no markdown fences.
- Use tools for ALL tax calculations. Never guess tax numbers.
- If a tool returns an error, explain it to the user clearly.
- Cite your sources when referencing tax rules.
- If the user's question is outside Indian tax, say so in a final_answer.
"""


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

class AgentLoopError(Exception):
    """Raised when the agent loop terminates abnormally."""


class AgentLoop:
    """
    Raw agent loop — no framework dependencies.

    Usage:
        loop = AgentLoop(llm_client, tool_registry)
        state = await loop.run(user_query="...", user_id="...")
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
    ) -> None:
        self._llm = llm_client
        self._tools = tool_registry
        settings = get_settings()
        self._max_iterations = settings.max_agent_iterations
        self._max_tool_calls = settings.max_tool_calls
        self._max_llm_calls = settings.max_llm_calls

    async def run(
        self,
        user_query: str,
        user_id: str,
        session_id: str | None = None,
    ) -> AgentState:
        """
        Execute the agent loop for a single user request.

        Returns:
            AgentState with final_answer populated (or error_message on failure).
        """
        state = AgentState(
            user_id=user_id,
            session_id=session_id or "",
            user_query=user_query,
            status="running",
        )

        logger.info(
            "Agent run started [request_id=%s user_id=%s]",
            state.request_id, user_id,
        )

        # Seed conversation
        state.messages = [
            {"role": MessageRole.SYSTEM.value, "content": SYSTEM_PROMPT},
            {"role": MessageRole.USER.value, "content": user_query},
        ]

        try:
            await self._loop(state)
        except AgentLoopError as exc:
            state.error_message = str(exc)
            state.finish("failed")
            logger.error("Agent loop error [request_id=%s]: %s", state.request_id, exc)
        except Exception as exc:
            state.error_message = f"Unexpected error: {exc}"
            state.finish("failed")
            logger.exception("Unexpected agent error [request_id=%s]", state.request_id)

        logger.info(
            "Agent run finished [request_id=%s status=%s iterations=%d llm=%d tools=%d elapsed=%dms]",
            state.request_id,
            state.status,
            state.iteration_count,
            state.llm_call_count,
            state.tool_call_count,
            state.elapsed_ms,
        )
        return state

    async def _loop(self, state: AgentState) -> None:
        """Inner loop — mutates state until a terminal condition is reached."""

        while True:
            # ----------------------------------------------------------------
            # Safety: iteration limit
            # ----------------------------------------------------------------
            if state.iteration_count >= self._max_iterations:
                state.final_answer = (
                    "I was unable to complete this request within the allowed "
                    "number of reasoning steps. Please try rephrasing your question."
                )
                state.finish("timeout")
                logger.warning(
                    "Max iterations reached [request_id=%s limit=%d]",
                    state.request_id, self._max_iterations,
                )
                return

            # ----------------------------------------------------------------
            # Safety: LLM call limit
            # ----------------------------------------------------------------
            if state.llm_call_count >= self._max_llm_calls:
                state.final_answer = (
                    "I reached the maximum number of reasoning steps. "
                    "Please try a more specific question."
                )
                state.finish("timeout")
                return

            state.iteration_count += 1

            # ----------------------------------------------------------------
            # Call LLM
            # ----------------------------------------------------------------
            messages = self._build_messages(state)
            tool_defs = self._tools.get_tool_definitions()

            llm_response = await self._llm.generate(
                messages,
                tools=tool_defs if tool_defs else None,
            )

            state.llm_call_count += 1
            state.total_input_tokens += llm_response.usage.input_tokens
            state.total_output_tokens += llm_response.usage.output_tokens

            # ----------------------------------------------------------------
            # Handle native tool_use blocks (Bedrock returns these directly)
            # ----------------------------------------------------------------
            if llm_response.has_tool_calls:
                for tc in llm_response.tool_calls:
                    await self._handle_tool_call(
                        state,
                        tool_name=tc.name,
                        arguments=tc.arguments,
                        reasoning="(native tool use)",
                    )
                    if state.tool_call_count >= self._max_tool_calls:
                        state.final_answer = (
                            "I reached the maximum number of tool calls. "
                            "Here is what I found so far:\n\n"
                            + "\n".join(state.observations)
                        )
                        state.finish("timeout")
                        return
                # Add observations to context and continue
                self._append_observations_to_messages(state)
                continue

            # ----------------------------------------------------------------
            # Parse structured JSON decision from text content
            # ----------------------------------------------------------------
            raw_content = llm_response.content or ""
            decision = self._parse_decision(raw_content, state)

            if decision is None:
                # Could not parse — treat as final answer with raw content
                state.final_answer = raw_content
                state.finish("completed")
                return

            # ----------------------------------------------------------------
            # FinalAnswer → done
            # ----------------------------------------------------------------
            if isinstance(decision, FinalAnswer):
                state.final_answer = decision.answer
                state.citations = decision.citations
                state.reasoning = decision.reasoning
                state.finish("completed")
                return

            # ----------------------------------------------------------------
            # ToolCall → validate, execute, observe
            # ----------------------------------------------------------------
            if isinstance(decision, ToolCallDecision):
                if state.tool_call_count >= self._max_tool_calls:
                    state.final_answer = (
                        "I reached the maximum number of tool calls. "
                        "Please try a more specific question."
                    )
                    state.finish("timeout")
                    return

                await self._handle_tool_call(
                    state,
                    tool_name=decision.tool_name,
                    arguments=decision.arguments,
                    reasoning=decision.reasoning,
                )
                # Append the assistant decision + observation to messages
                state.messages.append(
                    {"role": MessageRole.ASSISTANT.value, "content": raw_content}
                )
                self._append_observations_to_messages(state)

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def _build_messages(self, state: AgentState) -> list[Message]:
        return [
            Message(role=MessageRole(m["role"]), content=m["content"])
            for m in state.messages
        ]

    async def _handle_tool_call(
        self,
        state: AgentState,
        tool_name: str,
        arguments: dict[str, Any],
        reasoning: str,
    ) -> None:
        logger.debug(
            "Tool call [request_id=%s tool=%s]",
            state.request_id, tool_name,
        )
        t0 = time.time()

        if not self._tools.has(tool_name):
            observation = (
                f"Tool '{tool_name}' is not available. "
                f"Available tools: {self._tools.tool_names}"
            )
            state.observations.append(observation)
            state.record_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                result=observation,
                success=False,
                duration_ms=0,
            )
            return

        tool_result = await self._tools.execute(
            tool_name, arguments, user_id=state.user_id
        )
        duration_ms = int((time.time() - t0) * 1000)

        if tool_result.success:
            observation = (
                f"Tool '{tool_name}' result:\n"
                + json.dumps(tool_result.data, ensure_ascii=False, indent=2)
            )
        else:
            observation = f"Tool '{tool_name}' failed: {tool_result.error}"

        state.observations.append(observation)
        state.record_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            result=tool_result.data if tool_result.success else tool_result.error,
            success=tool_result.success,
            duration_ms=duration_ms,
        )

    def _append_observations_to_messages(self, state: AgentState) -> None:
        """Add all pending observations as a USER message for next LLM turn."""
        if state.observations:
            observation_text = "\n\n---\n\n".join(state.observations)
            state.messages.append(
                {
                    "role": MessageRole.USER.value,
                    "content": f"Tool results:\n\n{observation_text}",
                }
            )
            state.observations.clear()

    def _parse_decision(
        self, content: str, state: AgentState
    ) -> AgentDecision | None:
        """
        Try to parse LLM text output as an AgentDecision.

        Strips markdown fences if present.
        Returns None if parsing fails (caller handles gracefully).
        """
        from pydantic import ValidationError

        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            data = json.loads(text)
            return parse_agent_decision(data)
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning(
                "Could not parse agent decision [request_id=%s]: %s",
                state.request_id, exc,
            )
            return None
