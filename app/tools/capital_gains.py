"""
CalculateCapitalGainsTool — agent tool wrapping the capital gains engine.

The LLM requests this tool with a list of transactions.
The engine calculates everything deterministically.
The LLM only reads and explains the result.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.services.capital_gains import (
    AssetClass,
    CG_RULES,
    Transaction,
    calculate_capital_gains,
)
from app.tools.base import BaseTool, ToolResult


class TransactionInput(BaseModel):
    asset_class: str = Field(
        ...,
        description="Asset class: 'equity', 'equity_mf', 'debt_mf', 'foreign_equity', 'other'.",
    )
    buy_date: date = Field(..., description="Date of purchase (YYYY-MM-DD).")
    sell_date: date = Field(..., description="Date of sale (YYYY-MM-DD).")
    buy_price: int = Field(..., gt=0, description="Total cost of acquisition in INR.")
    sell_price: int = Field(..., gt=0, description="Total sale proceeds in INR.")
    fmv_31jan2018: int = Field(
        default=0,
        ge=0,
        description="Fair Market Value on 31-Jan-2018 (for equity grandfathering). Use 0 if not applicable.",
    )
    debt_mf_pre_apr2023: bool = Field(
        default=False,
        description="True if this is a debt mutual fund acquired before 1-Apr-2023.",
    )


class CalculateCapitalGainsInput(BaseModel):
    transactions: list[TransactionInput] = Field(
        ...,
        min_length=1,
        description="List of buy→sell transactions to calculate capital gains for.",
    )
    financial_year: str = Field(
        default="2024-25",
        description="Financial year for applicable tax rates, e.g. '2024-25'.",
    )


class CalculateCapitalGainsTool(BaseTool):
    @property
    def name(self) -> str:
        return "calculate_capital_gains"

    @property
    def description(self) -> str:
        return (
            "Calculate Indian capital gains tax deterministically across a portfolio. "
            "Handles: listed equity STCG (20%) and LTCG (12.5%, ₹1.25L exempt), "
            "equity mutual funds, debt mutual funds (slab / 20% with indexation), "
            "foreign/US stocks, and other assets. "
            "Applies equity LTCG exemption, grandfathering for pre-Jan-2018 equity, "
            "and 4% cess on flat-rate taxes. "
            f"Supported financial years: {sorted(CG_RULES.keys())}. "
            "Use this for ALL capital gains arithmetic — never calculate yourself."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CalculateCapitalGainsInput

    async def execute(
        self,
        validated_input: CalculateCapitalGainsInput,
        *,
        user_id: str,
    ) -> ToolResult:
        try:
            transactions = []
            pre_apr23_flags = []

            for t in validated_input.transactions:
                try:
                    ac = AssetClass(t.asset_class)
                except ValueError:
                    return ToolResult.fail(
                        f"Unknown asset_class '{t.asset_class}'. "
                        f"Valid values: {[a.value for a in AssetClass]}"
                    )
                transactions.append(
                    Transaction(
                        asset_class=ac,
                        buy_date=t.buy_date,
                        sell_date=t.sell_date,
                        buy_price=t.buy_price,
                        sell_price=t.sell_price,
                        fmv_31jan2018=t.fmv_31jan2018,
                    )
                )
                pre_apr23_flags.append(t.debt_mf_pre_apr2023)

            result = calculate_capital_gains(
                transactions=transactions,
                financial_year=validated_input.financial_year,
                debt_mf_pre_apr23_flags=pre_apr23_flags,
            )
            return ToolResult.ok(result.to_dict())

        except ValueError as exc:
            return ToolResult.fail(str(exc))
