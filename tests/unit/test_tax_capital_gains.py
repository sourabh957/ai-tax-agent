"""
Tests for the full tax engine (Milestone 17) and capital gains engine (Milestone 18).

All calculations verified against known values — no LLM, no API calls.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.tax_engine import (
    DeductionBreakdown,
    TaxBreakdown,
    calculate_income_tax,
    compare_regimes,
)
from app.services.capital_gains import (
    AssetClass,
    Transaction,
    calculate_capital_gains,
    calculate_transaction_gains,
)


# ============================================================
# Tax Engine — Milestone 17
# ============================================================

class TestDeductionBreakdown:
    def test_total(self):
        d = DeductionBreakdown(section_80c=150_000, section_80d=25_000, section_80ccd_1b=50_000)
        assert d.total == 225_000

    def test_to_dict_keys(self):
        d = DeductionBreakdown(section_80c=100_000)
        assert "section_80c" in d.to_dict()
        assert "total_deductions" in d.to_dict()


class TestCalculateIncomeTax:
    def test_backward_compat_other_deductions(self):
        """Legacy other_deductions param should still work."""
        r = calculate_income_tax(1_000_000, regime="old", other_deductions=150_000)
        assert r.total_tax > 0
        assert r.other_deductions == 150_000

    def test_80c_cap_applied(self):
        """80C cannot exceed ₹1.5L statutory limit."""
        r = calculate_income_tax(
            1_000_000, regime="old",
            deductions=DeductionBreakdown(section_80c=300_000)  # over limit
        )
        assert r.deductions.section_80c == 150_000  # capped

    def test_80d_cap_applied(self):
        r = calculate_income_tax(
            1_000_000, regime="old",
            deductions=DeductionBreakdown(section_80d=50_000)   # over 25K limit
        )
        assert r.deductions.section_80d == 25_000

    def test_new_regime_ignores_deductions(self):
        with_ded = calculate_income_tax(
            1_000_000, regime="new",
            deductions=DeductionBreakdown(section_80c=150_000, section_80d=25_000)
        )
        without_ded = calculate_income_tax(1_000_000, regime="new")
        assert with_ded.total_tax == without_ded.total_tax

    def test_80c_reduces_old_regime_tax(self):
        base = calculate_income_tax(1_000_000, regime="old")
        with_ded = calculate_income_tax(
            1_000_000, regime="old",
            deductions=DeductionBreakdown(section_80c=150_000)
        )
        assert with_ded.total_tax < base.total_tax

    def test_nps_additional_deduction(self):
        """80CCD(1B) NPS deduction up to ₹50K allowed in old regime."""
        base = calculate_income_tax(1_500_000, regime="old")
        with_nps = calculate_income_tax(
            1_500_000, regime="old",
            deductions=DeductionBreakdown(section_80ccd_1b=50_000)
        )
        assert with_nps.total_tax < base.total_tax

    def test_known_value_1000k_new_regime(self):
        """₹10L, new regime FY 2024-25 → ₹44,200"""
        r = calculate_income_tax(1_000_000, regime="new", financial_year="2024-25")
        assert r.total_tax == 44_200

    def test_known_value_500k_zero_tax(self):
        r = calculate_income_tax(500_000, regime="new")
        assert r.total_tax == 0

    def test_deduction_breakdown_in_to_dict(self):
        r = calculate_income_tax(
            1_000_000, regime="old",
            deductions=DeductionBreakdown(section_80c=100_000)
        )
        d = r.to_dict()
        assert "deductions" in d
        assert d["deductions"]["section_80c"] == 100_000


class TestRegimeComparison:
    def test_returns_comparison(self):
        comp = compare_regimes(1_000_000)
        assert comp.new_regime.regime == "new"
        assert comp.old_regime.regime == "old"

    def test_recommended_regime_is_new_or_old(self):
        comp = compare_regimes(1_000_000)
        assert comp.recommended_regime in ("new", "old")

    def test_tax_saving_non_negative(self):
        comp = compare_regimes(1_000_000)
        assert comp.tax_saving >= 0

    def test_high_deductions_favour_old_regime(self):
        """With max deductions, old regime can be better for mid-range income.
        ₹8L income, ₹2.25L deductions:
          New: taxable ₹7.25L → ₹23,400 tax
          Old: taxable ₹5.25L → ₹18,200 tax → old regime wins."""
        ded = DeductionBreakdown(
            section_80c=150_000,
            section_80d=25_000,
            section_80ccd_1b=50_000,
        )
        comp = compare_regimes(800_000, deductions=ded)
        assert comp.recommended_regime == "old"

    def test_to_dict_has_all_keys(self):
        d = compare_regimes(1_000_000).to_dict()
        for k in ["new_regime", "old_regime", "recommended_regime", "tax_saving_by_choosing_recommended"]:
            assert k in d

    def test_compare_tool_regime(self):
        """CalculateTaxTool with regime='compare' uses compare_regimes."""
        comp = compare_regimes(3_000_000)
        assert isinstance(comp.to_dict(), dict)


# ============================================================
# Capital Gains Engine — Milestone 18
# ============================================================

def equity_txn(buy_date, sell_date, buy_price, sell_price, fmv=0):
    return Transaction(
        asset_class=AssetClass.EQUITY,
        buy_date=buy_date, sell_date=sell_date,
        buy_price=buy_price, sell_price=sell_price,
        fmv_31jan2018=fmv,
    )


class TestCapitalGainsEngine:
    # ── Equity STCG ──────────────────────────────────────────────────────

    def test_equity_stcg_rate_2024(self):
        """Equity held < 12 months → STCG 20% (Budget 2024)."""
        txn = equity_txn(date(2024, 4, 1), date(2024, 9, 1), 100_000, 150_000)
        r = calculate_transaction_gains(txn, "2024-25")
        assert r.holding_period.value == "short_term"
        assert float(r.tax_rate) == 0.20
        # Tax = 50000 * 20% = 10000
        assert r.tax_amount == 10_000

    def test_equity_stcg_rate_2023(self):
        """FY 2023-24: STCG rate was 15%."""
        txn = equity_txn(date(2023, 4, 1), date(2023, 9, 1), 100_000, 150_000)
        r = calculate_transaction_gains(txn, "2023-24")
        assert float(r.tax_rate) == 0.15
        assert r.tax_amount == 7_500

    # ── Equity LTCG ──────────────────────────────────────────────────────

    def test_equity_ltcg_rate_2024(self):
        """Equity held ≥ 12 months → LTCG 12.5% (Budget 2024)."""
        txn = equity_txn(date(2023, 1, 1), date(2024, 6, 1), 100_000, 200_000)
        r = calculate_transaction_gains(txn, "2024-25")
        assert r.holding_period.value == "long_term"
        assert float(r.tax_rate) == 0.125

    def test_equity_ltcg_exemption_applied(self):
        """₹1.25L LTCG exempt, only excess taxed at 12.5%."""
        txns = [equity_txn(date(2023, 1, 1), date(2024, 6, 1), 100_000, 300_000)]
        portfolio = calculate_capital_gains(txns, "2024-25")
        # LTCG = 200,000; exempt = 125,000; taxable = 75,000
        assert portfolio.equity_ltcg_exempt == 125_000
        assert portfolio.equity_ltcg_taxable == 75_000
        # Tax = 75,000 * 12.5% * 1.04 cess = 9,750
        assert portfolio.equity_ltcg_tax == 9_750

    def test_equity_ltcg_below_exemption_zero_tax(self):
        """LTCG ≤ ₹1.25L → zero tax."""
        txns = [equity_txn(date(2023, 1, 1), date(2024, 6, 1), 100_000, 210_000)]
        portfolio = calculate_capital_gains(txns, "2024-25")
        # LTCG = 110,000 < 125,000 → tax = 0
        assert portfolio.equity_ltcg_tax == 0

    # ── Grandfathering ────────────────────────────────────────────────────

    def test_grandfathering_uses_fmv_when_higher(self):
        """Cost = max(actual_cost, FMV on 31-Jan-2018)."""
        txn = equity_txn(date(2016, 1, 1), date(2024, 6, 1),
                         buy_price=50_000, sell_price=200_000, fmv=120_000)
        r = calculate_transaction_gains(txn, "2024-25")
        # Cost should be FMV 120,000 (> actual 50,000)
        assert r.cost_of_acquisition == 120_000
        assert r.gain_loss == 80_000

    def test_grandfathering_uses_actual_when_higher(self):
        txn = equity_txn(date(2016, 1, 1), date(2024, 6, 1),
                         buy_price=180_000, sell_price=200_000, fmv=120_000)
        r = calculate_transaction_gains(txn, "2024-25")
        assert r.cost_of_acquisition == 180_000

    def test_grandfathering_no_artificial_loss(self):
        """FMV > sale price → cost capped at sale price (no artificial loss)."""
        txn = equity_txn(date(2016, 1, 1), date(2024, 6, 1),
                         buy_price=50_000, sell_price=100_000, fmv=200_000)
        r = calculate_transaction_gains(txn, "2024-25")
        assert r.cost_of_acquisition == 100_000  # capped at sell price
        assert r.gain_loss == 0

    # ── Debt MF ───────────────────────────────────────────────────────────

    def test_debt_mf_post_apr23_at_slab(self):
        txn = Transaction(
            asset_class=AssetClass.DEBT_MF,
            buy_date=date(2023, 6, 1), sell_date=date(2024, 6, 1),
            buy_price=100_000, sell_price=120_000,
        )
        r = calculate_transaction_gains(txn, "2024-25", debt_mf_acquired_pre_apr23=False)
        assert "slab" in r.tax_treatment.lower()
        assert r.tax_amount == 0   # amount = 0, caller adds to slab income

    def test_debt_mf_pre_apr23_ltcg_with_indexation(self):
        txn = Transaction(
            asset_class=AssetClass.DEBT_MF,
            buy_date=date(2020, 1, 1), sell_date=date(2024, 1, 1),
            buy_price=100_000, sell_price=150_000,
            cost_inflation_index_buy=301, cost_inflation_index_sell=348,
        )
        r = calculate_transaction_gains(txn, "2024-25", debt_mf_acquired_pre_apr23=True)
        assert r.holding_period.value == "long_term"
        assert float(r.tax_rate) == 0.20
        # Indexed cost = 100,000 * 348/301 = 115,614
        expected_cost = int(100_000 * 348 / 301)
        assert r.cost_of_acquisition == expected_cost

    # ── Foreign equity ────────────────────────────────────────────────────

    def test_foreign_equity_ltcg(self):
        txn = Transaction(
            asset_class=AssetClass.FOREIGN_EQUITY,
            buy_date=date(2022, 1, 1), sell_date=date(2024, 6, 1),
            buy_price=200_000, sell_price=350_000,
        )
        r = calculate_transaction_gains(txn, "2024-25")
        assert r.holding_period.value == "long_term"
        assert float(r.tax_rate) == 0.125

    def test_foreign_equity_stcg_at_slab(self):
        txn = Transaction(
            asset_class=AssetClass.FOREIGN_EQUITY,
            buy_date=date(2024, 1, 1), sell_date=date(2024, 6, 1),
            buy_price=100_000, sell_price=120_000,
        )
        r = calculate_transaction_gains(txn, "2024-25")
        assert r.holding_period.value == "short_term"
        assert r.tax_amount == 0  # slab rate, not flat

    # ── Portfolio aggregation ─────────────────────────────────────────────

    def test_portfolio_total_gains(self):
        txns = [
            equity_txn(date(2023, 1, 1), date(2024, 6, 1), 100_000, 200_000),  # LTCG 100K
            equity_txn(date(2024, 1, 1), date(2024, 6, 1), 50_000, 70_000),    # STCG 20K
        ]
        portfolio = calculate_capital_gains(txns, "2024-25")
        assert portfolio.equity_ltcg == 100_000
        assert portfolio.equity_stcg == 20_000

    def test_portfolio_loss_not_taxed(self):
        txns = [equity_txn(date(2024, 1, 1), date(2024, 6, 1), 100_000, 80_000)]
        portfolio = calculate_capital_gains(txns, "2024-25")
        assert portfolio.equity_stcg == -20_000
        assert portfolio.equity_stcg_tax == 0   # no tax on loss

    def test_invalid_financial_year(self):
        txns = [equity_txn(date(2024, 1, 1), date(2024, 6, 1), 100_000, 120_000)]
        with pytest.raises(ValueError, match="not found"):
            calculate_capital_gains(txns, "2000-01")


# ============================================================
# CalculateCapitalGainsTool
# ============================================================

@pytest.mark.asyncio
async def test_capital_gains_tool_success():
    from app.tools.capital_gains import CalculateCapitalGainsInput, CalculateCapitalGainsTool, TransactionInput

    tool = CalculateCapitalGainsTool()
    inp = CalculateCapitalGainsInput(
        transactions=[
            TransactionInput(
                asset_class="equity",
                buy_date=date(2023, 1, 1),
                sell_date=date(2024, 6, 1),
                buy_price=100_000,
                sell_price=250_000,
            )
        ],
        financial_year="2024-25",
    )
    result = await tool.execute(inp, user_id="u1")
    assert result.success is True
    assert "equity_ltcg_gross" in result.data


@pytest.mark.asyncio
async def test_capital_gains_tool_invalid_asset_class():
    from app.tools.capital_gains import CalculateCapitalGainsInput, CalculateCapitalGainsTool, TransactionInput

    tool = CalculateCapitalGainsTool()
    inp = CalculateCapitalGainsInput(
        transactions=[
            TransactionInput(
                asset_class="crypto",  # invalid
                buy_date=date(2024, 1, 1),
                sell_date=date(2024, 6, 1),
                buy_price=100_000,
                sell_price=120_000,
            )
        ],
    )
    result = await tool.execute(inp, user_id="u1")
    assert result.success is False
    assert "asset_class" in result.error


@pytest.mark.asyncio
async def test_compare_tax_tool_regime_compare():
    from app.tools.tax import CalculateTaxInput, CalculateTaxTool

    tool = CalculateTaxTool()
    inp = CalculateTaxInput(
        gross_income=3_000_000,
        regime="compare",
        section_80c=150_000,
        section_80d=25_000,
        section_80ccd_1b=50_000,
    )
    result = await tool.execute(inp, user_id="u1")
    assert result.success is True
    assert "recommended_regime" in result.data
    assert "new_regime" in result.data
    assert "old_regime" in result.data
