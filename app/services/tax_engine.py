"""
Deterministic Indian Income Tax Calculator — FY 2024-25 / 2023-24.

The LLM MUST NOT perform tax arithmetic.
This module is the single source of truth for all tax calculations.

Supported:
    - New tax regime (default from FY 2023-24 onwards)
    - Old tax regime
    - Standard deduction
    - Common deductions (80C, 80D, HRA, NPS 80CCD(1B), LTA)
    - Health and Education Cess (4%)
    - Surcharge with marginal relief
    - Section 87A rebate
    - Regime comparison

Tax rules are versioned by financial year.
Adding a new FY = adding a new entry to TAX_RULES.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    # Deduction limits (old regime)
    max_80c: int = 150_000
    max_80d_self: int = 25_000        # self + family
    max_80d_parents: int = 25_000     # parents (50K if senior citizen)
    max_80ccd_1b: int = 50_000        # NPS additional deduction
    max_hra_exemption_pct: float = 0.50  # 50% for metro, 40% non-metro


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
        max_80c=150_000,
        max_80d_self=25_000,
        max_80d_parents=25_000,
        max_80ccd_1b=50_000,
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
        max_80c=150_000,
        max_80d_self=25_000,
        max_80d_parents=25_000,
        max_80ccd_1b=50_000,
    ),
}


@dataclass
class DeductionBreakdown:
    """Itemised deductions under old regime."""
    section_80c: int = 0          # ELSS, PPF, LIC, home loan principal, etc.
    section_80d: int = 0          # medical insurance self+family
    section_80d_parents: int = 0  # medical insurance parents
    section_80ccd_1b: int = 0     # NPS additional (over and above 80C)
    hra_exemption: int = 0        # House Rent Allowance exemption
    other: int = 0                # LTA, professional tax, etc.

    @property
    def total(self) -> int:
        return (
            self.section_80c
            + self.section_80d
            + self.section_80d_parents
            + self.section_80ccd_1b
            + self.hra_exemption
            + self.other
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_80c": self.section_80c,
            "section_80d_self": self.section_80d,
            "section_80d_parents": self.section_80d_parents,
            "section_80ccd_1b_nps": self.section_80ccd_1b,
            "hra_exemption": self.hra_exemption,
            "other_deductions": self.other,
            "total_deductions": self.total,
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
    """Calculate surcharge with marginal relief."""
    rate = Decimal("0")
    applicable_threshold = 0
    for threshold, sr in rules.surcharge_rates:
        if gross > Decimal(threshold):
            rate = sr
            applicable_threshold = threshold

    if rate == Decimal("0"):
        return Decimal("0")

    # New regime: surcharge capped at 25% (Budget 2023)
    if regime == "new" and rate > Decimal("0.25"):
        rate = Decimal("0.25")

    raw_surcharge = (tax * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # Marginal relief: surcharge cannot exceed the income above the threshold
    income_above = gross - Decimal(applicable_threshold)
    if raw_surcharge > income_above:
        raw_surcharge = income_above.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    return max(raw_surcharge, Decimal("0"))


@dataclass
class TaxBreakdown:
    financial_year: str
    regime: str
    gross_income: int
    standard_deduction: int
    deductions: DeductionBreakdown
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
            "deductions": self.deductions.to_dict(),
            "taxable_income": self.taxable_income,
            "tax_before_rebate": self.tax_before_rebate,
            "rebate_87a": self.rebate_87a,
            "tax_after_rebate": self.tax_after_rebate,
            "surcharge": self.surcharge,
            "cess": self.cess,
            "total_tax": self.total_tax,
            "effective_rate_pct": self.effective_rate_pct,
        }

    # Backward-compat property used by old tests
    @property
    def other_deductions(self) -> int:
        return self.deductions.total


@dataclass
class RegimeComparison:
    """Side-by-side comparison of old and new regime for the same income."""
    new_regime: TaxBreakdown
    old_regime: TaxBreakdown

    @property
    def recommended_regime(self) -> str:
        return "new" if self.new_regime.total_tax <= self.old_regime.total_tax else "old"

    @property
    def tax_saving(self) -> int:
        return abs(self.new_regime.total_tax - self.old_regime.total_tax)

    def to_dict(self) -> dict[str, Any]:
        return {
            "new_regime": self.new_regime.to_dict(),
            "old_regime": self.old_regime.to_dict(),
            "recommended_regime": self.recommended_regime,
            "tax_saving_by_choosing_recommended": self.tax_saving,
            "explanation": (
                f"Choose {self.recommended_regime.upper()} regime to save ₹{self.tax_saving:,}."
            ),
        }


def calculate_income_tax(
    gross_income: int,
    regime: str = "new",
    financial_year: str = "2024-25",
    other_deductions: int = 0,          # legacy param — maps to deductions.other
    deductions: DeductionBreakdown | None = None,
) -> TaxBreakdown:
    """
    Calculate Indian income tax deterministically.

    Args:
        gross_income:     Total gross income in INR (salary + other sources).
        regime:           "new" or "old".
        financial_year:   e.g. "2024-25".
        other_deductions: Legacy total deductions (old regime). Use `deductions` for itemised.
        deductions:       Itemised DeductionBreakdown (old regime only).

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

    # Build deduction breakdown
    if deductions is None:
        deductions = DeductionBreakdown(other=other_deductions)

    # Cap deductions at statutory limits
    if regime == "old":
        deductions = DeductionBreakdown(
            section_80c=min(deductions.section_80c, rules.max_80c),
            section_80d=min(deductions.section_80d, rules.max_80d_self),
            section_80d_parents=min(deductions.section_80d_parents, rules.max_80d_parents),
            section_80ccd_1b=min(deductions.section_80ccd_1b, rules.max_80ccd_1b),
            hra_exemption=deductions.hra_exemption,
            other=deductions.other,
        )
        total_ded = Decimal(deductions.total)
    else:
        deductions = DeductionBreakdown()   # new regime ignores all itemised deductions
        total_ded = Decimal("0")

    taxable = max(gross - std_ded - total_ded, Decimal("0"))

    slabs = rules.new_regime_slabs if regime == "new" else rules.old_regime_slabs
    tax_raw = _apply_slabs(taxable, slabs)

    # Section 87A rebate
    threshold = (
        rules.rebate_87a_new_threshold if regime == "new" else rules.rebate_87a_old_threshold
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
        deductions=deductions,
        taxable_income=int(taxable.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        tax_before_rebate=int(tax_raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        rebate_87a=int(rebate),
        tax_after_rebate=int(tax_after_rebate.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        surcharge=int(surcharge),
        cess=int(cess),
        total_tax=total,
        effective_rate_pct=eff,
    )


def compare_regimes(
    gross_income: int,
    financial_year: str = "2024-25",
    deductions: DeductionBreakdown | None = None,
) -> RegimeComparison:
    """
    Calculate tax under both regimes and return a comparison.

    Args:
        gross_income:   Total gross income in INR.
        financial_year: e.g. "2024-25".
        deductions:     Itemised deductions (applied to old regime only).

    Returns:
        RegimeComparison with recommendation and tax saving.
    """
    new_bd = calculate_income_tax(gross_income, regime="new", financial_year=financial_year)
    old_bd = calculate_income_tax(
        gross_income,
        regime="old",
        financial_year=financial_year,
        deductions=deductions,
    )
    return RegimeComparison(new_regime=new_bd, old_regime=old_bd)

