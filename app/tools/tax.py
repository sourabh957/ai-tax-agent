"""
CalculateTaxTool — agent tool wrapping the deterministic tax engine.

Supports:
    - Single regime calculation
    - Regime comparison (new vs old)
    - Itemised deductions (80C, 80D, NPS, HRA)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.services.tax_engine import (
    TAX_RULES,
    DeductionBreakdown,
    calculate_income_tax,
    compare_regimes,
)
from app.tools.base import BaseTool, ToolResult


class CalculateTaxInput(BaseModel):
    gross_income: int = Field(
        ..., gt=0, description="Total gross income in INR (salary + other sources)."
    )
    regime: Literal["new", "old", "compare"] = Field(
        default="compare",
        description=(
            "'new' for new regime, 'old' for old regime, "
            "'compare' to calculate both and recommend the better one."
        ),
    )
    financial_year: str = Field(default="2024-25", description="e.g. '2024-25'.")
    section_80c: int = Field(default=0, ge=0, description="Section 80C investments (ELSS, PPF, LIC). Max ₹1.5L.")
    section_80d: int = Field(default=0, ge=0, description="Medical insurance premium (self + family). Max ₹25K.")
    section_80d_parents: int = Field(default=0, ge=0, description="Medical insurance for parents. Max ₹25K (₹50K if senior).")
    section_80ccd_1b: int = Field(default=0, ge=0, description="NPS contribution (additional, over 80C). Max ₹50K.")
    hra_exemption: int = Field(default=0, ge=0, description="HRA exemption amount (only old regime).")
    other_deductions: int = Field(default=0, ge=0, description="Other deductions (LTA, professional tax, etc.).")


class CalculateTaxTool(BaseTool):
    @property
    def name(self) -> str:
        return "calculate_tax"

    @property
    def description(self) -> str:
        supported_years = sorted(TAX_RULES.keys())
        return (
            "Calculate Indian income tax deterministically. "
            "Returns a full breakdown: taxable income, slab-wise tax, "
            "Section 87A rebate, surcharge, cess, total tax, and effective rate. "
            "Set regime='compare' to get both regimes with a recommendation. "
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
            ded = DeductionBreakdown(
                section_80c=validated_input.section_80c,
                section_80d=validated_input.section_80d,
                section_80d_parents=validated_input.section_80d_parents,
                section_80ccd_1b=validated_input.section_80ccd_1b,
                hra_exemption=validated_input.hra_exemption,
                other=validated_input.other_deductions,
            )

            if validated_input.regime == "compare":
                result = compare_regimes(
                    gross_income=validated_input.gross_income,
                    financial_year=validated_input.financial_year,
                    deductions=ded,
                )
                return ToolResult.ok(result.to_dict())
            else:
                breakdown = calculate_income_tax(
                    gross_income=validated_input.gross_income,
                    regime=validated_input.regime,
                    financial_year=validated_input.financial_year,
                    deductions=ded,
                )
                return ToolResult.ok(breakdown.to_dict())

        except ValueError as exc:
            return ToolResult.fail(str(exc))

