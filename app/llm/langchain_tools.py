"""
LangChain tool wrappers — Milestone 24.

Wraps our existing BaseTool implementations as LangChain @tool functions.
This enables using our tools with:
    - LangChain AgentExecutor
    - LCEL chains
    - LangGraph nodes

We wrap — not replace — our tools. The underlying tax engine and
tool registry remain authoritative. LangChain just calls them.

Architecture:
    LangChain AgentExecutor
        │
        ▼
    @tool lc_calculate_tax()
        │
        ▼
    CalculateTaxTool.execute()   ← our existing tool
        │
        ▼
    tax_engine.calculate_income_tax()   ← deterministic
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: run our async tools synchronously for LangChain
# (LangChain tools are sync by default; async support via ainvoke)
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine synchronously (for LangChain sync tool calls)."""
    try:
        loop = asyncio.get_running_loop()
        # Already inside an event loop — run in a thread pool
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running event loop — safe to create one
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# LangChain tool definitions
# ---------------------------------------------------------------------------

def make_lc_calculate_tax_tool(user_id: str = "anonymous"):
    """
    Create a LangChain @tool for Indian income tax calculation.

    Returns a callable compatible with LangChain AgentExecutor.
    """
    try:
        from langchain_core.tools import tool
    except ImportError:
        raise RuntimeError("langchain-core is not installed. Run: pip install langchain-core")

    @tool
    def lc_calculate_tax(
        gross_income: int,
        regime: str = "compare",
        financial_year: str = "2024-25",
        section_80c: int = 0,
        section_80d: int = 0,
        section_80ccd_1b: int = 0,
        other_deductions: int = 0,
    ) -> dict[str, Any]:
        """
        Calculate Indian income tax deterministically.
        Set regime='compare' to get both regimes with a recommendation.
        Supported regimes: 'new', 'old', 'compare'.
        Supported financial years: '2024-25', '2023-24'.
        Use for ALL tax arithmetic — never calculate tax yourself.
        """
        from app.tools.tax import CalculateTaxInput, CalculateTaxTool

        tool_instance = CalculateTaxTool()
        inp = CalculateTaxInput(
            gross_income=gross_income,
            regime=regime,
            financial_year=financial_year,
            section_80c=section_80c,
            section_80d=section_80d,
            section_80ccd_1b=section_80ccd_1b,
            other_deductions=other_deductions,
        )
        result = _run_async(tool_instance.execute(inp, user_id=user_id))
        if not result.success:
            raise ValueError(result.error)
        return result.data

    return lc_calculate_tax


def make_lc_calculate_capital_gains_tool(user_id: str = "anonymous"):
    """Create a LangChain @tool for capital gains calculation."""
    try:
        from langchain_core.tools import tool
    except ImportError:
        raise RuntimeError("langchain-core is not installed.")

    @tool
    def lc_calculate_capital_gains(
        transactions_json: str,
        financial_year: str = "2024-25",
    ) -> dict[str, Any]:
        """
        Calculate Indian capital gains tax for a portfolio.
        Pass transactions as a JSON string: list of objects with fields:
        asset_class, buy_date (YYYY-MM-DD), sell_date, buy_price, sell_price,
        fmv_31jan2018 (optional), debt_mf_pre_apr2023 (optional bool).
        asset_class values: equity, equity_mf, debt_mf, foreign_equity, other.
        Use for ALL capital gains arithmetic — never calculate yourself.
        """
        import json
        from app.tools.capital_gains import CalculateCapitalGainsInput, CalculateCapitalGainsTool, TransactionInput

        try:
            txn_data = json.loads(transactions_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"transactions_json must be valid JSON: {e}")

        tool_instance = CalculateCapitalGainsTool()
        inp = CalculateCapitalGainsInput(
            transactions=[TransactionInput(**t) for t in txn_data],
            financial_year=financial_year,
        )
        result = _run_async(tool_instance.execute(inp, user_id=user_id))
        if not result.success:
            raise ValueError(result.error)
        return result.data

    return lc_calculate_capital_gains


def get_all_lc_tools(user_id: str = "anonymous") -> list:
    """Return all LangChain tool wrappers for the given user."""
    return [
        make_lc_calculate_tax_tool(user_id),
        make_lc_calculate_capital_gains_tool(user_id),
    ]
