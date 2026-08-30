#!/usr/bin/env bash
# =============================================================================
# run_tests.sh — Run the full test suite for CI/CD
#
# Runs:
#   - Configuration check (no live services)
#   - Unit tests (no paid API calls, no live services)
#   - Marks integration/LLM tests as skipped unless flags are passed
#
# Usage:
#   ./scripts/run_tests.sh                    # unit tests only
#   ./scripts/run_tests.sh --integration      # include integration tests
#   ./scripts/run_tests.sh --all              # all including LLM tests
# =============================================================================
set -euo pipefail

RUN_INTEGRATION=false
RUN_LLM=false

for arg in "$@"; do
    case "$arg" in
        --integration) RUN_INTEGRATION=true ;;
        --all)         RUN_INTEGRATION=true; RUN_LLM=true ;;
    esac
done

# ── Configuration check ───────────────────────────────────────────────────────

echo "==> Running configuration check..."
python -m app.core.config_check || true   # warn but don't fail CI on missing optional config
echo ""

# ── Unit tests ────────────────────────────────────────────────────────────────

echo "==> Running unit tests..."
python -m pytest tests/unit/ \
    --tb=short \
    -q \
    --no-header

echo ""

# ── Integration tests (optional) ─────────────────────────────────────────────

if [ "$RUN_INTEGRATION" = true ]; then
    echo "==> Running integration tests (requires live services)..."
    python -m pytest tests/ \
        -m integration \
        --tb=short \
        -q \
        --no-header
    echo ""
fi

# ── LLM tests (optional, billable) ───────────────────────────────────────────

if [ "$RUN_LLM" = true ]; then
    echo "==> Running LLM tests (CAUTION: uses paid API)..."
    python -m pytest tests/ \
        -m llm \
        --tb=short \
        -q \
        --no-header
    echo ""
fi

echo "==> All tests passed."
