# Agent Architecture

## Agent loop (raw implementation)

```
User Input
    │
    ▼
Agent
    │
    ▼
LLM (Bedrock)
    │
    ▼
Structured Decision ──► final_answer → done
    │
    ▼ tool_call
Tool Validation
    │
    ▼
Tool Execution
    │
    ▼
Observation
    │
    ▼
Agent (next iteration)
    │
   ...
    │
    ▼
Terminate (max iterations / final answer)
```

## Safety limits

| Variable | Purpose |
|----------|---------|
| `MAX_AGENT_ITERATIONS` | Hard stop on total iterations |
| `MAX_TOOL_CALLS` | Prevents runaway tool usage |
| `MAX_LLM_CALLS` | Limits API cost per request |

## Agent state

Each agent run tracks:
- `request_id`, `user_id`, `session_id`
- `messages` (conversation context)
- `tool_calls` and `observations`
- `retrieved_documents`
- `iteration_count`
- `errors`

## Tool registry

Tools are pre-registered with:
- name, description
- input schema (Pydantic)
- output schema (Pydantic)
- authorization check
- error handling

The LLM **requests** a tool. The backend **executes** it. The LLM never directly modifies state.

## Progression

1. **Raw agent loop** (current target) — no framework dependencies
2. **LangChain** — introduced after raw loop is understood
3. **LangGraph** — introduced for stateful workflows and branching
