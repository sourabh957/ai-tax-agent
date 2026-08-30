"""
Deterministic Indian Capital Gains Calculator — FY 2024-25 / 2023-24.

The LLM MUST NOT perform capital gains arithmetic.
This module is the authoritative source for all capital gains calculations.

Supported asset classes:
    - Listed equity shares (BSE/NSE)
    - Equity mutual funds
    - Debt mutual funds
    - Foreign stocks / US stocks
    - Other assets (property, unlisted shares, gold, etc.)

Key rules implemented (FY 2024-25, post-Budget 2024):
    Equity (listed shares + equity MF):
        STCG (held < 12 months): 20% flat  ← changed from 15% in Budget 2024
        LTCG (held ≥ 12 months): 12.5% flat, exemption ₹1.25L ← changed in Budget 2024
        LTCG grandfathering: cost for pre-31-Jan-2018 acquisitions = max(actual, FMV on 31-Jan-2018)

    Debt mutual funds (acquired on/after 1-Apr-2023):
        No LTCG/STCG distinction — taxed as per income tax slab (Finance Act 2023)

    Debt mutual funds (acquired before 1-Apr-2023):
        STCG (held < 36 months): slab rate
        LTCG (held ≥ 36 months): 20% with indexation

    Foreign stocks / US stocks:
        STCG (held < 24 months): slab rate
        LTCG (held ≥ 24 months): 12.5% without indexation (Budget 2024)

    Other assets (property, gold, unlisted):
        STCG (held < 24 months): slab rate
        LTCG (held ≥ 24 months): 12.5% without indexation (Budget 2024)
                                 (was 20% with indexation pre-Budget 2024)

All rates are correct for FY 2024-25. FY 2023-24 uses pre-Budget 2024 rates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any


class AssetClass(str, Enum):
    EQUITY = "equity"               # Listed shares + equity MF (>65% equity)
    EQUITY_MF = "equity_mf"         # Equity mutual funds explicitly
    DEBT_MF = "debt_mf"             # Debt mutual funds
    FOREIGN_EQUITY = "foreign_equity"  # US stocks, foreign shares
    OTHER = "other"                 # Property, gold, unlisted shares


class HoldingPeriod(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


@dataclass
class Transaction:
    """A single buy→sell transaction for capital gains calculation."""
    asset_class: AssetClass
    buy_date: date
    sell_date: date
    buy_price: int          # total cost of acquisition in INR
    sell_price: int         # total sale proceeds in INR
    units: float = 1.0      # number of units/shares
    # For equity grandfathering (pre-31-Jan-2018 acquisition)
    fmv_31jan2018: int = 0  # Fair Market Value on 31-Jan-2018, if applicable
    # For debt MF with indexation
    cost_inflation_index_buy: int = 0
    cost_inflation_index_sell: int = 0

    @property
    def holding_days(self) -> int:
        return (self.sell_date - self.buy_date).days

    @property
    def holding_months(self) -> float:
        return self.holding_days / 30.44


@dataclass
class CapitalGainResult:
    """Result for a single transaction."""
    transaction: Transaction
    asset_class: AssetClass
    holding_period: HoldingPeriod
    holding_days: int
    sale_proceeds: int
    cost_of_acquisition: int       # after grandfathering / indexation
    gain_loss: int                 # positive = gain, negative = loss
    tax_rate: Decimal
    tax_treatment: str             # human-readable description
    tax_amount: int                # before exemption; final tax handled at portfolio level

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_class": self.asset_class.value,
            "holding_period": self.holding_period.value,
            "holding_days": self.holding_days,
            "sale_proceeds": self.sale_proceeds,
            "cost_of_acquisition": self.cost_of_acquisition,
            "gain_loss": self.gain_loss,
            "tax_rate_pct": float(self.tax_rate * 100),
            "tax_treatment": self.tax_treatment,
            "estimated_tax_before_exemption": self.tax_amount,
        }


@dataclass
class PortfolioCapitalGains:
    """Aggregated capital gains across all transactions."""
    transactions: list[CapitalGainResult]
    financial_year: str

    # Aggregates
    equity_stcg: int = 0
    equity_ltcg: int = 0
    equity_ltcg_exempt: int = 0      # ₹1.25L exemption (FY 2024-25)
    equity_ltcg_taxable: int = 0
    debt_gains_slab: int = 0         # taxed at slab rate
    debt_ltcg_indexed: int = 0       # debt MF acquired pre-Apr-2023, taxed at 20%
    foreign_stcg: int = 0            # at slab rate
    foreign_ltcg: int = 0            # at 12.5%
    other_stcg: int = 0
    other_ltcg: int = 0

    equity_stcg_tax: int = 0
    equity_ltcg_tax: int = 0
    debt_ltcg_tax: int = 0
    foreign_ltcg_tax: int = 0
    other_ltcg_tax: int = 0

    total_gains: int = 0
    total_tax: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "financial_year": self.financial_year,
            "equity_stcg": self.equity_stcg,
            "equity_ltcg_gross": self.equity_ltcg,
            "equity_ltcg_exempt": self.equity_ltcg_exempt,
            "equity_ltcg_taxable": self.equity_ltcg_taxable,
            "debt_gains_at_slab_rate": self.debt_gains_slab,
            "debt_ltcg_with_indexation": self.debt_ltcg_indexed,
            "foreign_stcg_at_slab": self.foreign_stcg,
            "foreign_ltcg": self.foreign_ltcg,
            "other_stcg_at_slab": self.other_stcg,
            "other_ltcg": self.other_ltcg,
            "total_gains": self.total_gains,
            "estimated_total_tax": self.total_tax,
            "transactions": [t.to_dict() for t in self.transactions],
            "notes": [
                "STCG/LTCG on equity and debt subject to slab rate must be added to total income.",
                "LTCG on equity ≥ ₹1.25L (FY 2024-25) taxed at 12.5% without indexation.",
                "Debt MF acquired on/after 1-Apr-2023 taxed at slab rate regardless of holding.",
                "Cess (4%) applies on all capital gains taxes.",
            ],
        }


# ── Capital gains rules per FY ───────────────────────────────────────────────

@dataclass(frozen=True)
class CapitalGainsRules:
    financial_year: str
    equity_stcg_rate: Decimal
    equity_ltcg_rate: Decimal
    equity_ltcg_exemption: int          # ₹1L (2023-24) / ₹1.25L (2024-25)
    equity_holding_months: int          # ≥12 = LTCG
    debt_mf_post_apr23_rate: str        # "slab" — no LTCG benefit
    debt_mf_pre_apr23_ltcg_rate: Decimal
    debt_mf_holding_months: int         # ≥36 = LTCG (pre-Apr-2023)
    foreign_stcg_rate: str              # "slab"
    foreign_ltcg_rate: Decimal
    foreign_holding_months: int         # ≥24 = LTCG
    other_ltcg_rate: Decimal
    other_holding_months: int           # ≥24 = LTCG


CG_RULES: dict[str, CapitalGainsRules] = {
    "2024-25": CapitalGainsRules(
        financial_year="2024-25",
        equity_stcg_rate=Decimal("0.20"),           # Budget 2024: 20% (was 15%)
        equity_ltcg_rate=Decimal("0.125"),           # Budget 2024: 12.5% (was 10%)
        equity_ltcg_exemption=125_000,               # Budget 2024: ₹1.25L (was ₹1L)
        equity_holding_months=12,
        debt_mf_post_apr23_rate="slab",
        debt_mf_pre_apr23_ltcg_rate=Decimal("0.20"),
        debt_mf_holding_months=36,
        foreign_stcg_rate="slab",
        foreign_ltcg_rate=Decimal("0.125"),          # Budget 2024: 12.5%
        foreign_holding_months=24,
        other_ltcg_rate=Decimal("0.125"),            # Budget 2024: 12.5% without indexation
        other_holding_months=24,
    ),
    "2023-24": CapitalGainsRules(
        financial_year="2023-24",
        equity_stcg_rate=Decimal("0.15"),
        equity_ltcg_rate=Decimal("0.10"),
        equity_ltcg_exemption=100_000,
        equity_holding_months=12,
        debt_mf_post_apr23_rate="slab",
        debt_mf_pre_apr23_ltcg_rate=Decimal("0.20"),
        debt_mf_holding_months=36,
        foreign_stcg_rate="slab",
        foreign_ltcg_rate=Decimal("0.20"),
        foreign_holding_months=24,
        other_ltcg_rate=Decimal("0.20"),
        other_holding_months=24,
    ),
}

CESS_RATE = Decimal("0.04")


def _is_long_term(txn: Transaction, rules: CapitalGainsRules) -> bool:
    months = txn.holding_months
    ac = txn.asset_class
    if ac in (AssetClass.EQUITY, AssetClass.EQUITY_MF):
        return months >= rules.equity_holding_months
    if ac == AssetClass.DEBT_MF:
        return months >= rules.debt_mf_holding_months
    if ac == AssetClass.FOREIGN_EQUITY:
        return months >= rules.foreign_holding_months
    return months >= rules.other_holding_months  # OTHER


def _equity_cost_grandfathered(txn: Transaction) -> int:
    """
    Apply LTCG grandfathering for equity acquired before 31-Jan-2018.

    Cost of acquisition = max(actual_cost, FMV on 31-Jan-2018)
    but capped at sale price (cannot create artificial loss).
    """
    if txn.fmv_31jan2018 <= 0:
        return txn.buy_price

    coa = max(txn.buy_price, txn.fmv_31jan2018)
    # If FMV > sale price, cap at sale price to avoid artificial loss
    coa = min(coa, txn.sell_price)
    return coa


def _debt_indexed_cost(txn: Transaction) -> int:
    """Apply Cost Inflation Index for pre-Apr-2023 debt MF LTCG."""
    if txn.cost_inflation_index_buy <= 0 or txn.cost_inflation_index_sell <= 0:
        return txn.buy_price
    indexed = int(
        txn.buy_price
        * txn.cost_inflation_index_sell
        / txn.cost_inflation_index_buy
    )
    return indexed


def calculate_transaction_gains(
    txn: Transaction,
    financial_year: str = "2024-25",
    debt_mf_acquired_pre_apr23: bool = False,
) -> CapitalGainResult:
    """
    Calculate capital gains for a single transaction.

    Args:
        txn:                      The buy→sell transaction.
        financial_year:           e.g. "2024-25".
        debt_mf_acquired_pre_apr23: True if debt MF was bought before 1-Apr-2023
                                    (gets old LTCG with indexation treatment).

    Returns:
        CapitalGainResult with gain/loss, tax rate, and treatment description.
    """
    if financial_year not in CG_RULES:
        raise ValueError(
            f"Capital gains rules for '{financial_year}' not found. "
            f"Supported: {sorted(CG_RULES.keys())}"
        )

    rules = CG_RULES[financial_year]
    is_lt = _is_long_term(txn, rules)
    hp = HoldingPeriod.LONG_TERM if is_lt else HoldingPeriod.SHORT_TERM

    ac = txn.asset_class

    # ── Equity (listed shares + equity MF) ───────────────────────────────
    if ac in (AssetClass.EQUITY, AssetClass.EQUITY_MF):
        if is_lt:
            cost = _equity_cost_grandfathered(txn)
            gain = txn.sell_price - cost
            rate = rules.equity_ltcg_rate
            treatment = (
                f"LTCG on equity — {float(rate)*100:.1f}% flat "
                f"(exemption ₹{rules.equity_ltcg_exemption:,} at portfolio level)"
            )
        else:
            cost = txn.buy_price
            gain = txn.sell_price - cost
            rate = rules.equity_stcg_rate
            treatment = f"STCG on equity — {float(rate)*100:.1f}% flat"

        tax = int(max(Decimal(max(gain, 0)) * rate, Decimal("0")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ))
        return CapitalGainResult(
            transaction=txn, asset_class=ac, holding_period=hp,
            holding_days=txn.holding_days, sale_proceeds=txn.sell_price,
            cost_of_acquisition=cost, gain_loss=gain,
            tax_rate=rate, tax_treatment=treatment, tax_amount=tax,
        )

    # ── Debt mutual funds ─────────────────────────────────────────────────
    if ac == AssetClass.DEBT_MF:
        if not debt_mf_acquired_pre_apr23:
            # Finance Act 2023: all debt MF gains taxed at slab rate
            cost = txn.buy_price
            gain = txn.sell_price - cost
            return CapitalGainResult(
                transaction=txn, asset_class=ac,
                holding_period=HoldingPeriod.SHORT_TERM,  # treated as slab
                holding_days=txn.holding_days, sale_proceeds=txn.sell_price,
                cost_of_acquisition=cost, gain_loss=gain,
                tax_rate=Decimal("0"),
                tax_treatment="Debt MF (post Apr-2023) — taxed at income slab rate",
                tax_amount=0,  # caller adds to taxable income
            )
        else:
            if is_lt:
                cost = _debt_indexed_cost(txn)
                gain = txn.sell_price - cost
                rate = rules.debt_mf_pre_apr23_ltcg_rate
                treatment = f"LTCG on debt MF (pre Apr-2023) — 20% with indexation"
            else:
                cost = txn.buy_price
                gain = txn.sell_price - cost
                rate = Decimal("0")
                treatment = "STCG on debt MF — taxed at income slab rate"

            tax = int(max(Decimal(max(gain, 0)) * rate, Decimal("0")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ))
            return CapitalGainResult(
                transaction=txn, asset_class=ac, holding_period=hp,
                holding_days=txn.holding_days, sale_proceeds=txn.sell_price,
                cost_of_acquisition=cost, gain_loss=gain,
                tax_rate=rate, tax_treatment=treatment, tax_amount=tax,
            )

    # ── Foreign equity / US stocks ────────────────────────────────────────
    if ac == AssetClass.FOREIGN_EQUITY:
        cost = txn.buy_price
        gain = txn.sell_price - cost
        if is_lt:
            rate = rules.foreign_ltcg_rate
            treatment = f"LTCG on foreign equity — {float(rate)*100:.1f}%"
        else:
            rate = Decimal("0")
            treatment = "STCG on foreign equity — taxed at income slab rate"

        tax = int(max(Decimal(max(gain, 0)) * rate, Decimal("0")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ))
        return CapitalGainResult(
            transaction=txn, asset_class=ac, holding_period=hp,
            holding_days=txn.holding_days, sale_proceeds=txn.sell_price,
            cost_of_acquisition=cost, gain_loss=gain,
            tax_rate=rate, tax_treatment=treatment, tax_amount=tax,
        )

    # ── Other (property, gold, unlisted) ─────────────────────────────────
    cost = txn.buy_price
    gain = txn.sell_price - cost
    if is_lt:
        rate = rules.other_ltcg_rate
        treatment = f"LTCG on other assets — {float(rate)*100:.1f}%"
    else:
        rate = Decimal("0")
        treatment = "STCG on other assets — taxed at income slab rate"

    tax = int(max(Decimal(max(gain, 0)) * rate, Decimal("0")).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ))
    return CapitalGainResult(
        transaction=txn, asset_class=ac, holding_period=hp,
        holding_days=txn.holding_days, sale_proceeds=txn.sell_price,
        cost_of_acquisition=cost, gain_loss=gain,
        tax_rate=rate, tax_treatment=treatment, tax_amount=tax,
    )


def calculate_capital_gains(
    transactions: list[Transaction],
    financial_year: str = "2024-25",
    debt_mf_pre_apr23_flags: list[bool] | None = None,
) -> PortfolioCapitalGains:
    """
    Calculate capital gains across a portfolio of transactions.

    Applies:
        - Per-transaction gain/loss calculation
        - Equity LTCG exemption (₹1.25L for FY 2024-25)
        - Aggregation by asset class and holding period
        - Cess (4%) on applicable flat-rate taxes

    Args:
        transactions:           List of Transaction objects.
        financial_year:         e.g. "2024-25".
        debt_mf_pre_apr23_flags: Per-transaction bool — True if debt MF acquired
                                  before 1-Apr-2023. Defaults to False for all.

    Returns:
        PortfolioCapitalGains with full aggregation.
    """
    if financial_year not in CG_RULES:
        raise ValueError(
            f"Capital gains rules for '{financial_year}' not found. "
            f"Supported: {sorted(CG_RULES.keys())}"
        )

    rules = CG_RULES[financial_year]
    flags = debt_mf_pre_apr23_flags or [False] * len(transactions)

    results: list[CapitalGainResult] = []
    for txn, flag in zip(transactions, flags):
        r = calculate_transaction_gains(txn, financial_year, flag)
        results.append(r)

    portfolio = PortfolioCapitalGains(transactions=results, financial_year=financial_year)

    for r in results:
        ac = r.asset_class
        gain = r.gain_loss

        if ac in (AssetClass.EQUITY, AssetClass.EQUITY_MF):
            if r.holding_period == HoldingPeriod.SHORT_TERM:
                portfolio.equity_stcg += gain
            else:
                portfolio.equity_ltcg += gain

        elif ac == AssetClass.DEBT_MF:
            if "slab" in r.tax_treatment.lower() and "indexation" not in r.tax_treatment.lower():
                portfolio.debt_gains_slab += gain
            else:
                portfolio.debt_ltcg_indexed += gain

        elif ac == AssetClass.FOREIGN_EQUITY:
            if r.holding_period == HoldingPeriod.SHORT_TERM:
                portfolio.foreign_stcg += gain
            else:
                portfolio.foreign_ltcg += max(gain, 0)

        else:  # OTHER
            if r.holding_period == HoldingPeriod.SHORT_TERM:
                portfolio.other_stcg += gain
            else:
                portfolio.other_ltcg += max(gain, 0)

    # ── Apply equity LTCG exemption ───────────────────────────────────────
    taxable_equity_ltcg = max(portfolio.equity_ltcg - rules.equity_ltcg_exemption, 0)
    portfolio.equity_ltcg_exempt = min(portfolio.equity_ltcg, rules.equity_ltcg_exemption)
    portfolio.equity_ltcg_taxable = taxable_equity_ltcg

    # ── Calculate taxes ───────────────────────────────────────────────────
    def _with_cess(amount: int) -> int:
        return int((Decimal(amount) * (1 + CESS_RATE)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ))

    if portfolio.equity_stcg > 0:
        portfolio.equity_stcg_tax = _with_cess(
            int((Decimal(portfolio.equity_stcg) * rules.equity_stcg_rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ))
        )

    if taxable_equity_ltcg > 0:
        portfolio.equity_ltcg_tax = _with_cess(
            int((Decimal(taxable_equity_ltcg) * rules.equity_ltcg_rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ))
        )

    if portfolio.debt_ltcg_indexed > 0:
        portfolio.debt_ltcg_tax = _with_cess(
            int((Decimal(portfolio.debt_ltcg_indexed) * rules.debt_mf_pre_apr23_ltcg_rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ))
        )

    if portfolio.foreign_ltcg > 0:
        portfolio.foreign_ltcg_tax = _with_cess(
            int((Decimal(portfolio.foreign_ltcg) * rules.foreign_ltcg_rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ))
        )

    if portfolio.other_ltcg > 0:
        portfolio.other_ltcg_tax = _with_cess(
            int((Decimal(portfolio.other_ltcg) * rules.other_ltcg_rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            ))
        )

    portfolio.total_gains = (
        portfolio.equity_stcg + portfolio.equity_ltcg
        + portfolio.debt_gains_slab + portfolio.debt_ltcg_indexed
        + portfolio.foreign_stcg + portfolio.foreign_ltcg
        + portfolio.other_stcg + portfolio.other_ltcg
    )
    portfolio.total_tax = (
        portfolio.equity_stcg_tax + portfolio.equity_ltcg_tax
        + portfolio.debt_ltcg_tax + portfolio.foreign_ltcg_tax
        + portfolio.other_ltcg_tax
    )

    return portfolio
