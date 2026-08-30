# LangGraph — When and Why

## What LangGraph adds

LangGraph is a graph-based orchestration layer built on LangChain.
It models the agent as a **directed state graph** where:

- **Nodes** are Python functions (LLM calls, tool executions, routing logic)
- **Edges** are transitions between nodes (can be conditional)
- **State** is a typed dict or Pydantic model shared across all nodes
- **Checkpointers** enable persistence, resumption, and time-travel

```
                  ┌─────────────────────────────────┐
                  │          StateGraph              │
                  │                                 │
  START ──────►  call_llm ──► route ──► call_tool  │
                  │              │           │       │
                  │              └──► END    └──►   │
                  │                      call_llm   │
                  └─────────────────────────────────┘
```

---

## Raw loop vs LangChain AgentExecutor vs LangGraph

| Concern | Raw Loop | LangChain AgentExecutor | LangGraph |
|---------|----------|------------------------|-----------|
| **Code complexity** | Most explicit | Simple | Medium |
| **State persistence** | Manual (AgentState) | None built-in | Native (checkpointer) |
| **Branching logic** | if/else in Python | Not supported | First-class conditional edges |
| **Parallel tool calls** | Manual asyncio.gather | Not supported | Native (fan-out nodes) |
| **Human-in-the-loop** | Manual pause/resume | Not supported | Built-in interrupt_before |
| **Retries** | Manual counter | Limited | Node-level retry policies |
| **Streaming** | Provider stream | astream_events | astream + astream_events |
| **Debugging** | Direct Python | LangSmith | LangSmith + graph visualiser |
| **Multi-agent** | Not built-in | Not supported | Native subgraphs |
| **Interview explainability** | Full | Partial | Requires LangGraph knowledge |

---

## When to use LangGraph

### Use LangGraph when you need:

**1. Stateful multi-turn workflows**
```
User asks Q1 → agent answers
User asks Q2 (referencing Q1) → agent uses persisted state
```
LangGraph checkpointers (SQLite, Postgres, Redis) persist state between HTTP requests
without any custom code.

**2. Complex branching**
```
Query arrives
    │
    ▼
Classify intent
    │
    ├──► simple calculation ──► calculate_tax ──► respond
    │
    ├──► needs documents ──► retrieve_docs ──► extract ──► calculate ──► respond
    │
    └──► regime comparison ──► calculate_both ──► compare ──► respond
```
LangGraph conditional edges replace `if/elif` chains in the raw loop.

**3. Human-in-the-loop**
```python
graph = StateGraph(TaxAgentState)
graph.add_node("calculate", calculate_node)
graph.add_node("human_review", human_review_node)
graph.compile(interrupt_before=["human_review"])

# Agent pauses at human_review, waits for approval
# Resumes after human provides input
```
Essential for high-stakes tax decisions that require CA review before sending.

**4. Parallel tool execution**
```
Fan-out:
    retrieve_tax_rules ──┐
    retrieve_user_data  ──┤──► synthesise ──► respond
    calculate_tax       ──┘
```

---

## When NOT to use LangGraph

**Don't use LangGraph for:**

- Simple single-turn Q&A — overkill, adds latency
- Deterministic workflows (always the same steps) — use a plain async function
- When you haven't mastered the raw loop yet — understand the primitives first

---

## LangGraph for the Tax Agent

The tax agent has legitimate LangGraph use cases:

| Feature | Value |
|---------|-------|
| Multi-turn sessions | User uploads Form 16 → asks follow-up questions → agent remembers context |
| Complex regime comparison | Parallel old/new regime calculation + retrieval |
| Document review workflow | `interrupt_before=["send_answer"]` for CA review |
| Retry on bad LLM output | Node-level retry before giving up |
| Agentic RAG sub-graph | Separate retrieval sub-graph with its own state |

---

## Architecture decision

We implement LangGraph **on top of** our existing components:

```
LangGraph StateGraph
    │
    ├── call_llm node        → uses LLMClient (our abstraction)
    ├── execute_tools node   → uses ToolRegistry (our registry)
    ├── retrieve node        → uses hybrid_retrieve (our RAG)
    └── should_continue edge → checks AgentState limits
```

We do NOT replace:
- Tax engine (deterministic Python)
- Capital gains engine
- RAG pipeline
- Guardrails
- Observability

LangGraph orchestrates. Our code does the work.

---

## Comparison with our raw loop

```python
# Raw loop (Milestone 8) — ~300 lines
while True:
    response = await llm.generate(messages)
    decision = parse_agent_decision(response.content)
    if isinstance(decision, FinalAnswer): break
    result = await registry.execute(decision.tool_name, ...)
    messages.append(observation)

# LangGraph (Milestone 26) — ~80 lines
graph = StateGraph(TaxAgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
graph.add_edge("tools", "agent")
compiled = graph.compile()
result = await compiled.ainvoke({"messages": [...]})
```

Same architecture. LangGraph provides the loop, checkpointing, and streaming.
