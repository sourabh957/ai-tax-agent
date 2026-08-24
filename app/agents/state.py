"""
AgentState — tracks everything that happens during a single agent run.

Short-term state only. This is NOT long-term memory.

One AgentState is created per user request and discarded after the response.
If persistence is needed (agent run history), that goes to the AgentRun DB model.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCallRecord:
    """A single tool call made during this run."""
    tool_name: str
    arguments: dict[str, Any]
    result: Any          # raw ToolResult.data or error string
    success: bool
    duration_ms: int


@dataclass
class AgentState:
    """
    Complete state for one agent execution.

    Lifecycle:
        1. Created at request start with user_id, session_id, user_query.
        2. Updated by the agent loop on every iteration.
        3. Read to build the final response.
        4. Optionally persisted to the AgentRun table after completion.
    """

    # Identity
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Input
    user_query: str = ""

    # Conversation context sent to the LLM
    messages: list[dict[str, Any]] = field(default_factory=list)

    # Tool call history
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    # Retrieved documents (populated by RAG tools)
    retrieved_documents: list[dict[str, Any]] = field(default_factory=list)

    # Observations (tool results as text, appended to messages)
    observations: list[str] = field(default_factory=list)

    # Output
    final_answer: str | None = None
    citations: list[str] = field(default_factory=list)
    reasoning: str = ""

    # Counters
    iteration_count: int = 0
    tool_call_count: int = 0
    llm_call_count: int = 0

    # Tokens
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Status
    status: str = "pending"   # pending | running | completed | failed | timeout
    error_message: str | None = None

    # Timing
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    @property
    def elapsed_ms(self) -> int:
        end = self.finished_at or time.time()
        return int((end - self.started_at) * 1000)

    def finish(self, status: str = "completed") -> None:
        self.status = status
        self.finished_at = time.time()

    def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
        success: bool,
        duration_ms: int,
    ) -> None:
        self.tool_calls.append(
            ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                success=success,
                duration_ms=duration_ms,
            )
        )
        self.tool_call_count += 1

    def to_summary(self) -> dict[str, Any]:
        """Lightweight summary for logging/persistence."""
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "status": self.status,
            "iteration_count": self.iteration_count,
            "tool_call_count": self.tool_call_count,
            "llm_call_count": self.llm_call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "elapsed_ms": self.elapsed_ms,
            "error_message": self.error_message,
        }
