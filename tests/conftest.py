"""
Pytest configuration.

Integration and LLM tests are gated behind markers so the default test run
never requires paid API calls or live external services.

    pytest               # unit tests only (fast, no external services)
    pytest -m integration  # requires live DB, Qdrant, etc.
    pytest -m llm          # requires paid LLM API access
"""
