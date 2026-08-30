"""
LangGraph Tax Agent — Milestone 26.

Implements the same agent architecture as the raw loop (Milestone 8)
using LangGraph's StateGraph.

Comparison with raw loop:
    Raw (app/agents/loop.py):
        - Manual while loop with explicit iteration counter
        - Custom AgentState dataclass
        - Direct JSON parsing of LLM output
        - Safety limits checked in Python

    LangGraph (this file):
        - StateGraph with nodes and conditional edges
        - TypedDict state with message history
        - Native tool calling via bind_tools
        - Safety limits as conditional edges
        - Optional checkpointing for multi-turn persistence

Architecture:
    START
      │
      ▼
    [agent] ── LLM call with tools bound ──►
      │
      ├── has tool calls? ──► [tools] ── execute via ToolRegistry ──► [agent]
      │
      └── final answer / limits exceeded? ──► END

The graph re-uses:
    - ToolRegistry (our existing tool registry)
    - LLMClient (our LLM abstraction)
    - Guardrails (checked before entering the graph)
    - AgentTrace (observability)
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, TypedDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

def _reducer(left: list, right: list) -> list:
    """Append-only reducer for message lists."""
    return left + right


class TaxAgentState(TypedDict):
    """
    Shared state across all LangGraph nodes.

    messages: Full conversation history (LangChain message objects).
    tool_call_count: Tracks tool calls for safety limit enforcement.
    iteration_count: Tracks LLM calls for safety limit enforcement.
    user_id: The requesting user (for tool authorization).
    request_id: Correlation ID for observability.
    final_answer: Set when the agent produces its answer.
    """
    messages: Annotated[list, _reducer]
    tool_call_count: int
    iteration_count: int
    user_id: str
    request_id: str
    final_answer: str


# ---------------------------------------------------------------------------
# Node: agent (LLM call)
# ---------------------------------------------------------------------------

def build_agent_node(llm_with_tools):
    """
    Returns a node function that calls the LLM with tools bound.

    The LLM decides whether to call a tool or produce a final answer.
    """
    async def agent_node(state: TaxAgentState) -> dict:
        from langchain_core.messages import AIMessage

        messages = state["messages"]
        response: AIMessage = await llm_with_tools.ainvoke(messages)

        return {
            "messages": [response],
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    return agent_node


# ---------------------------------------------------------------------------
# Node: tools (execute tool calls requested by LLM)
# ---------------------------------------------------------------------------

def build_tools_node(tool_registry):
    """
    Returns a node function that executes tool calls via our ToolRegistry.

    Uses the ToolRegistry instead of LangChain's built-in ToolNode so that
    our authorization, validation, and error handling remain in effect.
    """
    async def tools_node(state: TaxAgentState) -> dict:
        from langchain_core.messages import AIMessage, ToolMessage

        messages = state["messages"]
        last_message: AIMessage = messages[-1]
        user_id = state.get("user_id", "anonymous")

        tool_messages = []
        tool_call_count = state.get("tool_call_count", 0)

        for tool_call in (last_message.tool_calls or []):
            tool_name = tool_call["name"]
            arguments = tool_call["args"]
            tool_call_id = tool_call["id"]

            result = await tool_registry.execute(
                tool_name, arguments, user_id=user_id
            )

            content = (
                str(result.data) if result.success
                else f"Error: {result.error}"
            )
            tool_messages.append(
                ToolMessage(content=content, tool_call_id=tool_call_id)
            )
            tool_call_count += 1

        return {
            "messages": tool_messages,
            "tool_call_count": tool_call_count,
        }

    return tools_node


# ---------------------------------------------------------------------------
# Edge: should_continue
# ---------------------------------------------------------------------------

def build_should_continue(max_iterations: int = 8, max_tool_calls: int = 10):
    """
    Returns a conditional edge function.

    Decides whether to:
        - Continue to the tools node (LLM requested a tool)
        - End the graph (final answer or limits exceeded)
    """
    def should_continue(state: TaxAgentState) -> Literal["tools", "end"]:
        from langchain_core.messages import AIMessage

        messages = state["messages"]
        last_message = messages[-1] if messages else None

        # Safety: iteration limit
        if state.get("iteration_count", 0) >= max_iterations:
            logger.warning("LangGraph: max iterations reached (%d)", max_iterations)
            return "end"

        # Safety: tool call limit
        if state.get("tool_call_count", 0) >= max_tool_calls:
            logger.warning("LangGraph: max tool calls reached (%d)", max_tool_calls)
            return "end"

        # Has tool calls → route to tools node
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"

        # No tool calls → LLM produced final answer
        return "end"

    return should_continue


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def build_tax_agent_graph(
    llm_client,
    tool_registry,
    *,
    max_iterations: int = 8,
    max_tool_calls: int = 10,
    checkpointer=None,
):
    """
    Build and compile the LangGraph tax agent.

    Args:
        llm_client:      Our LLMClient (wraps Bedrock or LangChain provider).
        tool_registry:   Our ToolRegistry with registered tools.
        max_iterations:  Hard stop on LLM calls.
        max_tool_calls:  Hard stop on tool executions.
        checkpointer:    Optional LangGraph checkpointer for persistence
                         (e.g. MemorySaver for dev, PostgresSaver for prod).

    Returns:
        A compiled LangGraph CompiledStateGraph ready for .ainvoke() / .astream().
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        raise RuntimeError(
            "langgraph is not installed. Run: pip install langgraph"
        )

    # Build LangChain LLM with tools bound
    # We use the LangChain provider from our abstraction layer
    try:
        from langchain_aws import ChatBedrock
        from app.core.config import get_settings
        settings = get_settings()

        lc_tools = tool_registry.get_tool_definitions()
        # Convert our ToolDefinition list to LangChain StructuredTool format
        from app.llm.langchain_tools import get_all_lc_tools
        lc_tool_list = get_all_lc_tools()

        llm = ChatBedrock(
            model_id=settings.bedrock_model_id or "anthropic.claude-3-5-sonnet-20241022-v2:0",
            region_name=settings.aws_region or "ap-south-1",
        )
        llm_with_tools = llm.bind_tools(lc_tool_list)

    except Exception as exc:
        logger.warning(
            "Could not build LangChain LLM with tools (expected in test): %s", exc
        )
        # In tests, pass in a mock llm_with_tools via llm_client
        llm_with_tools = llm_client

    # Build nodes
    agent_node = build_agent_node(llm_with_tools)
    tools_node = build_tools_node(tool_registry)
    should_continue = build_should_continue(max_iterations, max_tool_calls)

    # Build graph
    graph = StateGraph(TaxAgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END},
    )
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# High-level run function
# ---------------------------------------------------------------------------

async def run_tax_agent_graph(
    user_query: str,
    user_id: str,
    llm_client,
    tool_registry,
    *,
    request_id: str | None = None,
    max_iterations: int = 8,
    max_tool_calls: int = 10,
    thread_id: str | None = None,
    checkpointer=None,
) -> dict[str, Any]:
    """
    Run the LangGraph tax agent for a single query.

    Args:
        user_query:      The user's tax question.
        user_id:         Requesting user ID.
        llm_client:      LLMClient instance.
        tool_registry:   ToolRegistry with registered tools.
        request_id:      Optional correlation ID.
        thread_id:       LangGraph thread ID for multi-turn persistence.
        checkpointer:    Optional checkpointer for state persistence.

    Returns:
        Dict with final_answer and full message history.
    """
    import uuid
    from langchain_core.messages import HumanMessage, SystemMessage
    from app.agents.loop import SYSTEM_PROMPT

    compiled = build_tax_agent_graph(
        llm_client,
        tool_registry,
        max_iterations=max_iterations,
        max_tool_calls=max_tool_calls,
        checkpointer=checkpointer,
    )

    rid = request_id or str(uuid.uuid4())
    tid = thread_id or rid

    initial_state: TaxAgentState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_query),
        ],
        "tool_call_count": 0,
        "iteration_count": 0,
        "user_id": user_id,
        "request_id": rid,
        "final_answer": "",
    }

    config = {"configurable": {"thread_id": tid}} if checkpointer else {}

    logger.info(
        "LangGraph agent run started [request_id=%s user_id=%s]", rid, user_id
    )

    result = await compiled.ainvoke(initial_state, config=config)

    # Extract final answer from last AI message
    final_answer = ""
    for msg in reversed(result.get("messages", [])):
        from langchain_core.messages import AIMessage
        if isinstance(msg, AIMessage) and msg.content:
            if isinstance(msg.content, str):
                final_answer = msg.content
                break

    logger.info(
        "LangGraph agent run completed [request_id=%s iterations=%d tools=%d]",
        rid,
        result.get("iteration_count", 0),
        result.get("tool_call_count", 0),
    )

    return {
        "request_id": rid,
        "final_answer": final_answer,
        "iteration_count": result.get("iteration_count", 0),
        "tool_call_count": result.get("tool_call_count", 0),
        "messages": result.get("messages", []),
    }
