"""
Tests for the deterministic tax engine.

All values verified manually against known Indian tax slabs.
No LLM, no API calls, no external services.
"""

from __future__ import annotations

import pytest

from app.services.tax_engine import TaxBreakdown, calculate_income_tax


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

def test_returns_tax_breakdown():
    result = calculate_income_tax(500_000)
    assert isinstance(result, TaxBreakdown)


def test_to_dict_has_all_keys():
    d = calculate_income_tax(500_000).to_dict()
    for key in [
        "financial_year", "regime", "gross_income", "standard_deduction",
        "deductions", "taxable_income", "tax_before_rebate",
        "rebate_87a", "tax_after_rebate", "surcharge", "cess",
        "total_tax", "effective_rate_pct",
    ]:
        assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# New regime — FY 2024-25
# Known: gross ₹5L, std deduction ₹75K → taxable ₹4,25,000
#        slab tax: 3L @ 0% + 1,25,000 @ 5% = ₹6,250
#        taxable ≤ ₹7L → 87A rebate min(6250, 25000) = ₹6,250 → tax = 0
# ---------------------------------------------------------------------------

def test_new_regime_500k_zero_tax():
    r = calculate_income_tax(500_000, regime="new", financial_year="2024-25")
    assert r.total_tax == 0
    assert r.rebate_87a == r.tax_before_rebate  # full rebate


def test_new_regime_700k_zero_tax():
    # ₹7L gross, std ded ₹75K → taxable ₹6,25,000
    # slab: 3L@0% + 3,25,000@5% = ₹16,250; taxable ≤ ₹7L → rebate ₹16,250 → tax 0
    r = calculate_income_tax(700_000, regime="new", financial_year="2024-25")
    assert r.total_tax == 0


def test_new_regime_800k_has_tax():
    # ₹8L → taxable ₹7,25,000 → above 87A threshold → some tax
    r = calculate_income_tax(800_000, regime="new", financial_year="2024-25")
    assert r.total_tax > 0


def test_new_regime_1000k():
    # ₹10L gross, std ded ₹75K → taxable ₹9,25,000
    # 3L@0% + 4L@5% + 2,25,000@10% = 0 + 20,000 + 22,500 = ₹42,500
    # taxable > 7L → no 87A; cess 4% on 42,500 = 1,700 → total ₹44,200
    r = calculate_income_tax(1_000_000, regime="new", financial_year="2024-25")
    assert r.tax_before_rebate == 42_500
    assert r.rebate_87a == 0
    assert r.cess == 1_700
    assert r.total_tax == 44_200


def test_new_regime_3000k():
    # ₹30L gross, std ded ₹75K → taxable ₹29,25,000
    # 3L@0% + 4L@5% + 3L@10% + 2L@15% + 3L@20% + 14,25,000@30%
    # = 0 + 20000 + 30000 + 30000 + 60000 + 427500 = ₹567,500
    r = calculate_income_tax(3_000_000, regime="new", financial_year="2024-25")
    assert r.tax_before_rebate == 567_500
    assert r.surcharge == 0  # income < ₹50L
    assert r.total_tax == int(567_500 * 1.04)  # cess only


# ---------------------------------------------------------------------------
# Old regime — FY 2024-25
# ---------------------------------------------------------------------------

def test_old_regime_500k_zero_tax():
    # ₹5L gross, std ded ₹50K → taxable ₹4,50,000
    # 2.5L@0% + 2L@5% = ₹10,000; taxable ≤ ₹5L → rebate ₹10,000 → total 0
    r = calculate_income_tax(500_000, regime="old", financial_year="2024-25")
    assert r.total_tax == 0


def test_old_regime_deductions_reduce_tax():
    # ₹10L gross, ₹1.5L deductions (80C), std ded ₹50K → taxable ₹8L
    # vs no deductions taxable ₹9.5L → less tax with deductions
    with_ded = calculate_income_tax(1_000_000, regime="old", other_deductions=150_000)
    without_ded = calculate_income_tax(1_000_000, regime="old")
    assert with_ded.total_tax < without_ded.total_tax


def test_old_regime_deductions_ignored_in_new():
    new_with = calculate_income_tax(1_000_000, regime="new", other_deductions=150_000)
    new_without = calculate_income_tax(1_000_000, regime="new")
    assert new_with.total_tax == new_without.total_tax  # deductions ignored


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_invalid_financial_year():
    with pytest.raises(ValueError, match="not supported"):
        calculate_income_tax(500_000, financial_year="2010-11")


def test_invalid_regime():
    with pytest.raises(ValueError, match="regime must be"):
        calculate_income_tax(500_000, regime="ultra")


# ---------------------------------------------------------------------------
# Surcharge
# ---------------------------------------------------------------------------

def test_surcharge_applied_above_50L():
    r = calculate_income_tax(60_000_000, regime="new", financial_year="2024-25")
    assert r.surcharge > 0


def test_new_regime_surcharge_capped_at_25pct():
    # ₹6Cr income triggers 37% surcharge in old regime, capped at 25% in new
    r_new = calculate_income_tax(60_000_000, regime="new")
    r_old = calculate_income_tax(60_000_000, regime="old")
    # new regime surcharge rate capped lower, so surcharge/tax ratio differs
    new_rate = r_new.surcharge / r_new.tax_after_rebate if r_new.tax_after_rebate else 0
    old_rate = r_old.surcharge / r_old.tax_after_rebate if r_old.tax_after_rebate else 0
    assert new_rate <= old_rate


# ---------------------------------------------------------------------------
# CalculateTaxTool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_tax_tool_success():
    from app.tools.tax import CalculateTaxInput, CalculateTaxTool

    tool = CalculateTaxTool()
    inp = CalculateTaxInput(gross_income=1_000_000, regime="new")
    result = await tool.execute(inp, user_id="u1")
    assert result.success is True
    assert result.data["total_tax"] > 0


@pytest.mark.asyncio
async def test_calculate_tax_tool_invalid_year():
    from app.tools.tax import CalculateTaxInput, CalculateTaxTool

    tool = CalculateTaxTool()
    inp = CalculateTaxInput(gross_income=500_000, financial_year="1999-00")
    result = await tool.execute(inp, user_id="u1")
    assert result.success is False
    assert "not supported" in result.error
