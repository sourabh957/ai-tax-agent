# LangChain vs Raw Implementation

## Why we built the raw agent loop first

Before introducing LangChain, we implemented the complete agent architecture manually:

```
app/agents/loop.py        — raw agent loop
app/agents/state.py       — agent state
app/agents/schemas.py     — structured output (AgentDecision)
app/tools/registry.py     — tool registry
app/tools/base.py         — base tool class
app/llm/base.py           — LLM abstraction
app/llm/client.py         — LLM client
app/llm/providers/bedrock.py — Bedrock provider
```

This was intentional. You should be able to explain the full agent loop in an interview without mentioning LangChain once.

---

## Raw implementation walkthrough

```python
# What the raw loop does on every iteration:

messages = build_messages(state)          # 1. Build conversation context
response = await llm.generate(messages)   # 2. Call LLM
decision = parse_agent_decision(response) # 3. Parse structured JSON output

if isinstance(decision, FinalAnswer):
    state.final_answer = decision.answer  # 4a. Done
    return

if isinstance(decision, ToolCallDecision):
    tool = registry.get(decision.tool_name) # 4b. Look up tool
    result = await tool.execute(...)         #     Execute it
    state.observations.append(result)        #     Record observation
    # → loop continues
```

Every abstraction is visible. Every failure mode is explicit.

---

## LangChain equivalent

```python
from langchain_aws import ChatBedrock
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

llm = ChatBedrock(model_id=settings.bedrock_model_id)
tools = [lc_calculate_tax, lc_retrieve_tax_rules]  # wrapped as LangChain tools
prompt = ChatPromptTemplate.from_messages([...])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, max_iterations=8)

result = await executor.ainvoke({"input": user_query})
```

Same result. Much less code.

---

## Comparison table

| Concern | Raw Implementation | LangChain |
|---------|-------------------|-----------|
| **Lines of code** | ~300 (loop + state + schemas) | ~30 (executor setup) |
| **Transparency** | Full — every step is explicit | Abstracted — internals hidden |
| **Debugging** | Step-by-step, easy to add print/log | Verbose callbacks needed for deep inspection |
| **Custom state** | Native — `AgentState` is our own dataclass | Requires custom `AgentState` + `Checkpointer` |
| **Custom structured output** | Full control over Pydantic schema | Uses LCEL `.with_structured_output()` |
| **Tool authorization** | Enforced in `ToolRegistry` | Must add custom wrapper |
| **Safety limits** | Direct counters in `AgentState` | `max_iterations` in `AgentExecutor`, limited granularity |
| **Streaming** | Direct async generator from provider | `astream_events` with event types |
| **Provider switching** | `LLM_PROVIDER=bedrock/openai/local` | Different `ChatModel` classes per provider |
| **Observability** | `AgentTrace` — full control | LangSmith (SaaS) or custom callbacks |
| **Token counting** | Direct from provider response | Requires callback or LangSmith |
| **Testing** | Mock `LLMClient` — no framework | Mock `ChatModel` or use `FakeLLM` |
| **Learning curve** | Python only — no framework | Must learn LCEL, chains, runnables |
| **Production reliability** | Predictable — no framework updates break it | Framework updates can introduce regressions |
| **Interview explainability** | Full — can explain every line | Partial — "LangChain handles that" |

---

## When to use LangChain

**LangChain adds clear value for:**

1. **Model integration** — `ChatBedrock`, `ChatOpenAI`, `ChatAnthropic` handle
   authentication, retry, streaming, and token counting out of the box.

2. **Tool calling** — `@tool` decorator + `create_tool_calling_agent` reduces
   boilerplate significantly. No need to write `ToolRegistry` from scratch.

3. **Message handling** — `ChatPromptTemplate`, `MessagesPlaceholder`,
   `HumanMessage`, `AIMessage` provide a clean abstraction for conversation history.

4. **Structured output** — `.with_structured_output(MySchema)` reduces the
   JSON parsing + Pydantic validation we wrote manually.

5. **Multi-provider** — switching from Bedrock to OpenAI is `ChatBedrock` →
   `ChatOpenAI`. Our raw `LLMProvider` abstraction solves this too, but
   LangChain already has implementations for 30+ providers.

**LangChain adds no value for:**

1. **Deterministic tax calculations** — these are pure Python, nothing to do with LangChain
2. **RAG pipeline control** — our custom Qdrant + RRF + reranking pipeline is better
   than LangChain's `RetrievalQA` for our use case
3. **Tool authorization** — must still be implemented in Python regardless
4. **Guardrails** — not a LangChain concern

---

## LangChain disadvantages

1. **Abstraction leaks** — framework internals surface when debugging; error messages reference internal classes
2. **Version instability** — `langchain`, `langchain-core`, `langchain-community`, `langchain-aws` all version independently; breaking changes are common
3. **Observability tax** — requires LangSmith (external SaaS) or custom callbacks for production-grade tracing; our `AgentTrace` already does this natively
4. **Over-engineering risk** — the breadth of LangChain encourages using it for everything, including things that don't need it
5. **Interview credibility** — "I used LangChain" is less impressive than "I built the agent loop, then refactored to LangChain after understanding the primitives"

---

## Decision

We introduce LangChain for:

| Component | LangChain Replaces |
|-----------|-------------------|
| LLM calls | `BedrockProvider.generate()` → `ChatBedrock` |
| Tool calling | `ToolRegistry` → `@tool` + `create_tool_calling_agent` |
| Message history | `state.messages` dict list → `ChatPromptTemplate` |
| Structured output | `parse_agent_decision()` → `.with_structured_output()` |

We keep our own implementation for:

| Component | Reason |
|-----------|--------|
| Tax engine | Deterministic Python — no LLM |
| Capital gains engine | Deterministic Python — no LLM |
| RAG pipeline | Custom Qdrant + RRF + reranking |
| Guardrails | Security boundary must be in our code |
| Observability | `AgentTrace` + CloudWatch — no external SaaS |
| Evaluation | Custom metrics runner |

---

## Debugging guide

### Raw agent loop
```python
# Add to loop.py for step-by-step visibility:
logger.debug("Iteration %d: LLM returned %s", state.iteration_count, decision.type)
logger.debug("Tool call: %s(%s)", decision.tool_name, decision.arguments)
logger.debug("Observation: %s", observation[:200])
```

### LangChain agent
```python
# Use verbose=True for console output:
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Or use callbacks for structured logging:
from langchain.callbacks import StdOutCallbackHandler
executor = AgentExecutor(agent=agent, tools=tools, callbacks=[StdOutCallbackHandler()])
```

### Production (both)
Both implementations emit to `AgentTrace` → CloudWatch. Query with:
```
fields @timestamp, request_id, status, iteration_count, estimated_cost_usd
| filter request_id = "your-request-id"
| sort @timestamp asc
```

---

## Raw vs LangChain — same agent, different code

The key insight: **the architecture is identical**. LangChain is syntax sugar over
the same loop we wrote manually. Understanding the raw implementation means
you understand LangChain's internals, not just its API.

```
Raw:      User → AgentLoop → LLMClient → ToolRegistry → AgentState → Response
LangChain: User → AgentExecutor → ChatBedrock → @tool functions → Response
```

Same data flow. Same failure modes. Same safety requirements.
