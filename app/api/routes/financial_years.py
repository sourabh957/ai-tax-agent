from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter

from app.services.tax_engine import TAX_RULES

router = APIRouter()


class FinancialYearResponse(BaseModel):
    id: str
    label: str
    year: str
    is_current: bool


@router.get("/financial-years", response_model=list[FinancialYearResponse])
async def list_financial_years() -> list[FinancialYearResponse]:
    years = sorted(TAX_RULES.keys(), reverse=True)
    current_year = years[0] if years else ""
    return [
        FinancialYearResponse(
            id=year,
            label=f"FY {year}",
            year=year,
            is_current=year == current_year,
        )
        for year in years
    ]
