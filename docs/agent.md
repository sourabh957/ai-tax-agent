# Agent Architecture

> See also: [architecture.md](architecture.md) * [langchain_comparison.md](langchain_comparison.md) * [langgraph_comparison.md](langgraph_comparison.md)

## Why a raw agent loop first

The raw agent loop (Milestone 8) is implemented before LangChain or LangGraph
so the architecture is fully understood without framework abstraction.

Benefits:
- Can explain every line in an interview without mentioning LangChain
- Failure modes are explicit and debuggable
- Safety limits (iteration cap, tool call cap, LLM call cap) are directly in Python
- No framework updates can break the core behaviour

---

## Agent loop walkthrough

File: app/agents/loop.py

```
User query
    |
    v
AgentLoop.run()
    |
    +-- Build messages (system prompt + user query + conversation history)
    |
    +-- LOOP (while iteration_count < MAX_AGENT_ITERATIONS):
    |       |
    |       +-- Check safety limits -> terminate gracefully if exceeded
    |       |
    |       +-- llm.generate(messages, tools=[...]) -> LLMResponse
    |       |
    |       +-- Parse AgentDecision from LLM content (JSON)
    |               |
    |               +-- FinalAnswer  -> set state.final_answer, return
    |               |
    |               +-- ToolCall     -> validate -> execute -> append observation
    |
    +-- Return AgentState
```

Key code pattern:
    response = await llm.generate(messages, tools=tool_defs)
    decision = parse_agent_decision(response.content)
    
    if isinstance(decision, FinalAnswer):
        state.final_answer = decision.answer    # done
        return
    
    if isinstance(decision, ToolCallDecision):
        result = await registry.execute(decision.tool_name, decision.arguments)
        state.observations.append(f"Tool result: {result.data}")
        # loop continues

---

## Agent state

File: app/agents/state.py

AgentState tracks everything for one request lifetime:

| Field | Description |
|-------|-------------|
| request_id | UUID for end-to-end correlation (matches X-Request-ID header) |
| user_id | Requesting user |
| session_id | Multi-turn session grouping |
| messages | Full conversation context (system + user + assistant + tool results) |
| tool_calls | Every tool call with result + latency |
| final_answer | The agent final response |
| citations | Source references cited in the answer |
| iteration_count | Total loop iterations |
| tool_call_count | Total tool executions |
| llm_call_count | Total LLM API calls |
| status | pending / running / completed / failed / timeout |

Short-term state only. AgentState is discarded after the request.
Persistent data goes to the AgentRun database model.

---

## Tool registry

File: app/tools/registry.py

The ToolRegistry is the security boundary between the LLM and tool execution.

    LLM says: "call calculate_tax with gross_income=1000000"
                    |
                    v
            ToolRegistry.execute()
                    |
                    +-- 1. Lookup tool by name (KeyError if unknown)
                    +-- 2. Pydantic input validation (ValidationError if bad args)
                    +-- 3. tool.execute(validated_input, user_id=...)
                    +-- 4. Return ToolResult (never raises - errors captured)

The LLM never executes tools directly. It requests them by name.
The registry decides whether to execute them.

### Registered tools

| Tool name | File | Description |
|-----------|------|-------------|
| calculate_tax | app/tools/tax.py | Indian income tax (new/old regime, deductions, comparison) |
| calculate_capital_gains | app/tools/capital_gains.py | Equity/debt/foreign CG (Budget 2024 rates) |
| retrieve_tax_rules | app/rag/agentic_rag.py | Qdrant hybrid retrieval + reranking + citations |

---

## Structured output

File: app/agents/schemas.py

The LLM must respond with JSON matching one of two schemas at each step:

Option 1 - final answer:
    {"type": "final_answer", "answer": "Your tax is 44200.", "reasoning": "...", "citations": [...]}

Option 2 - call a tool:
    {"type": "tool_call", "tool_name": "calculate_tax", "arguments": {"gross_income": 1000000, "regime": "new"}, "reasoning": "..."}

Pydantic validates every response before any action is taken.
Malformed JSON -> graceful fallback (treated as plain text final answer).

---

## Safety limits

All configurable via .env:

| Env var | Default | What it prevents |
|---------|---------|-----------------|
| MAX_AGENT_ITERATIONS | 8 | Infinite reasoning loops |
| MAX_TOOL_CALLS | 10 | Runaway tool execution |
| MAX_LLM_CALLS | 6 | Unbounded API cost per request |
| DAILY_REQUEST_LIMIT | 5 | Per-user daily abuse |

When a limit is hit, the agent returns a graceful message. Never an exception.

---

## Agent progression

| Milestone | Implementation | Why |
|-----------|---------------|-----|
| 8-9 | Raw Python loop | Understand the fundamentals |
| 24 | LangChain + ChatBedrock | Less boilerplate, multi-provider |
| 26 | LangGraph StateGraph | Stateful sessions, branching, human-in-loop |