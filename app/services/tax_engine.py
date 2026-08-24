"""
Deterministic Indian Income Tax Calculator — FY 2024-25 / 2023-24.

The LLM MUST NOT perform tax arithmetic.
This module is the single source of truth for all tax calculations.

Supported:
    - New tax regime (default from FY 2023-24 onwards)
    - Old tax regime
    - Standard deduction
    - Health and Education Cess (4%)
    - Surcharge
    - Section 87A rebate

Tax rules are versioned by financial year.
Adding a new FY = adding a new entry to TAX_RULES.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Each slab: (upper_limit_inclusive_or_None, rate)
_Slabs = list[tuple[int | None, Decimal]]


@dataclass(frozen=True)
class TaxRules:
    financial_year: str
    new_regime_slabs: _Slabs
    old_regime_slabs: _Slabs
    new_regime_standard_deduction: int
    old_regime_standard_deduction: int
    cess_rate: Decimal
    # list of (income_threshold, surcharge_rate) — ascending order
    surcharge_rates: list[tuple[int, Decimal]]
    rebate_87a_new_threshold: int    # max taxable income eligible under new regime
    rebate_87a_old_threshold: int    # max taxable income eligible under old regime
    rebate_87a_max_amount: int


TAX_RULES: dict[str, TaxRules] = {
    "2024-25": TaxRules(
        financial_year="2024-25",
        new_regime_slabs=[
            (300_000,  Decimal("0.00")),
            (700_000,  Decimal("0.05")),
            (1_000_000, Decimal("0.10")),
            (1_200_000, Decimal("0.15")),
            (1_500_000, Decimal("0.20")),
            (None,      Decimal("0.30")),
        ],
        old_regime_slabs=[
            (250_000,  Decimal("0.00")),
            (500_000,  Decimal("0.05")),
            (1_000_000, Decimal("0.20")),
            (None,      Decimal("0.30")),
        ],
        new_regime_standard_deduction=75_000,   # Budget 2024
        old_regime_standard_deduction=50_000,
        cess_rate=Decimal("0.04"),
        surcharge_rates=[
            (5_000_000,  Decimal("0.10")),
            (10_000_000, Decimal("0.15")),
            (20_000_000, Decimal("0.25")),
            (50_000_000, Decimal("0.37")),
        ],
        rebate_87a_new_threshold=700_000,
        rebate_87a_old_threshold=500_000,
        rebate_87a_max_amount=25_000,
    ),
    "2023-24": TaxRules(
        financial_year="2023-24",
        new_regime_slabs=[
            (300_000,  Decimal("0.00")),
            (600_000,  Decimal("0.05")),
            (900_000,  Decimal("0.10")),
            (1_200_000, Decimal("0.15")),
            (1_500_000, Decimal("0.20")),
            (None,      Decimal("0.30")),
        ],
        old_regime_slabs=[
            (250_000,  Decimal("0.00")),
            (500_000,  Decimal("0.05")),
            (1_000_000, Decimal("0.20")),
            (None,      Decimal("0.30")),
        ],
        new_regime_standard_deduction=50_000,
        old_regime_standard_deduction=50_000,
        cess_rate=Decimal("0.04"),
        surcharge_rates=[
            (5_000_000,  Decimal("0.10")),
            (10_000_000, Decimal("0.15")),
            (20_000_000, Decimal("0.25")),
            (50_000_000, Decimal("0.37")),
        ],
        rebate_87a_new_threshold=700_000,
        rebate_87a_old_threshold=500_000,
        rebate_87a_max_amount=25_000,
    ),
}


def _apply_slabs(taxable_income: Decimal, slabs: _Slabs) -> Decimal:
    """Apply progressive tax slabs and return total tax."""
    tax = Decimal("0")
    prev = Decimal("0")
    for upper, rate in slabs:
        upper_d = Decimal(upper) if upper is not None else None
        if taxable_income <= prev:
            break
        slab_income = (
            min(taxable_income, upper_d) - prev
            if upper_d is not None
            else taxable_income - prev
        )
        tax += slab_income * rate
        if upper_d is not None:
            prev = upper_d
    return tax


def _calc_surcharge(gross: Decimal, tax: Decimal, rules: TaxRules, regime: str) -> Decimal:
    rate = Decimal("0")
    for threshold, sr in rules.surcharge_rates:
        if gross > Decimal(threshold):
            rate = sr
    # New regime: surcharge capped at 25% (Budget 2023)
    if regime == "new" and rate > Decimal("0.25"):
        rate = Decimal("0.25")
    return (tax * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@dataclass
class TaxBreakdown:
    financial_year: str
    regime: str
    gross_income: int
    standard_deduction: int
    other_deductions: int          # 80C, 80D, HRA etc. — old regime only
    taxable_income: int
    tax_before_rebate: int
    rebate_87a: int
    tax_after_rebate: int
    surcharge: int
    cess: int
    total_tax: int
    effective_rate_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "financial_year": self.financial_year,
            "regime": self.regime,
            "gross_income": self.gross_income,
            "standard_deduction": self.standard_deduction,
            "other_deductions": self.other_deductions,
            "taxable_income": self.taxable_income,
            "tax_before_rebate": self.tax_before_rebate,
            "rebate_87a": self.rebate_87a,
            "tax_after_rebate": self.tax_after_rebate,
            "surcharge": self.surcharge,
            "cess": self.cess,
            "total_tax": self.total_tax,
            "effective_rate_pct": self.effective_rate_pct,
        }


def calculate_income_tax(
    gross_income: int,
    regime: str = "new",
    financial_year: str = "2024-25",
    other_deductions: int = 0,
) -> TaxBreakdown:
    """
    Calculate Indian income tax deterministically.

    Args:
        gross_income:     Total gross income in INR (salary + other sources).
        regime:           "new" or "old".
        financial_year:   e.g. "2024-25".
        other_deductions: Section 80C/80D/HRA etc. Only applied under old regime.

    Returns:
        TaxBreakdown with full line-by-line calculation.

    Raises:
        ValueError: Unsupported financial year or regime.
    """
    if financial_year not in TAX_RULES:
        raise ValueError(
            f"Financial year '{financial_year}' is not supported. "
            f"Supported: {sorted(TAX_RULES.keys())}"
        )
    if regime not in ("new", "old"):
        raise ValueError(f"regime must be 'new' or 'old', got '{regime}'.")

    rules = TAX_RULES[financial_year]
    gross = Decimal(gross_income)

    std_ded = Decimal(
        rules.new_regime_standard_deduction
        if regime == "new"
        else rules.old_regime_standard_deduction
    )
    other_ded = Decimal(other_deductions) if regime == "old" else Decimal("0")
    taxable = max(gross - std_ded - other_ded, Decimal("0"))

    slabs = rules.new_regime_slabs if regime == "new" else rules.old_regime_slabs
    tax_raw = _apply_slabs(taxable, slabs)

    # Section 87A rebate
    threshold = (
        rules.rebate_87a_new_threshold
        if regime == "new"
        else rules.rebate_87a_old_threshold
    )
    rebate = Decimal("0")
    if taxable <= Decimal(threshold):
        rebate = min(tax_raw, Decimal(rules.rebate_87a_max_amount))

    tax_after_rebate = max(tax_raw - rebate, Decimal("0"))
    surcharge = _calc_surcharge(gross, tax_after_rebate, rules, regime)
    cess = ((tax_after_rebate + surcharge) * rules.cess_rate).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    total = int(tax_after_rebate + surcharge + cess)
    eff = round(float(Decimal(total) / gross * 100), 2) if gross > 0 else 0.0

    return TaxBreakdown(
        financial_year=financial_year,
        regime=regime,
        gross_income=gross_income,
        standard_deduction=int(std_ded),
        other_deductions=int(other_ded),
        taxable_income=int(taxable.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        tax_before_rebate=int(tax_raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        rebate_87a=int(rebate),
        tax_after_rebate=int(tax_after_rebate.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        surcharge=int(surcharge),
        cess=int(cess),
        total_tax=total,
        effective_rate_pct=eff,
    )
