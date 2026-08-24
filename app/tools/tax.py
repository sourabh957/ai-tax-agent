"""
CalculateTaxTool — agent tool wrapping the deterministic tax engine.

The LLM requests this tool with structured arguments.
The tool validates inputs, calls the tax engine, and returns a ToolResult.
The LLM never touches the arithmetic — it only reads the result to explain it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.services.tax_engine import TAX_RULES, calculate_income_tax
from app.tools.base import BaseTool, ToolResult


class CalculateTaxInput(BaseModel):
    gross_income: int = Field(
        ..., gt=0, description="Total gross income in INR (salary + other sources)."
    )
    regime: Literal["new", "old"] = Field(
        default="new",
        description="Tax regime: 'new' (default) or 'old'.",
    )
    financial_year: str = Field(
        default="2024-25",
        description="Financial year, e.g. '2024-25'.",
    )
    other_deductions: int = Field(
        default=0,
        ge=0,
        description=(
            "Total deductions under 80C, 80D, HRA, etc. "
            "Only applied under old regime; ignored for new regime."
        ),
    )


class CalculateTaxTool(BaseTool):
    @property
    def name(self) -> str:
        return "calculate_tax"

    @property
    def description(self) -> str:
        supported_years = sorted(TAX_RULES.keys())
        return (
            "Calculate Indian income tax deterministically. "
            "Returns a full breakdown: taxable income, tax by slab, "
            "Section 87A rebate, surcharge, cess, total tax, and effective rate. "
            f"Supported financial years: {supported_years}. "
            "Use this tool for ALL tax arithmetic — never calculate tax yourself."
        )

    @property
    def input_schema(self) -> type[BaseModel]:
        return CalculateTaxInput

    async def execute(
        self,
        validated_input: CalculateTaxInput,
        *,
        user_id: str,
    ) -> ToolResult:
        try:
            breakdown = calculate_income_tax(
                gross_income=validated_input.gross_income,
                regime=validated_input.regime,
                financial_year=validated_input.financial_year,
                other_deductions=validated_input.other_deductions,
            )
            return ToolResult.ok(breakdown.to_dict())
        except ValueError as exc:
            return ToolResult.fail(str(exc))
