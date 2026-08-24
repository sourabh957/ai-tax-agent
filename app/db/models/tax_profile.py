"""
TaxProfile model — stores a user's tax-relevant configuration.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin, new_uuid


class TaxProfile(Base, TimestampMixin):
    __tablename__ = "tax_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    financial_year: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="e.g. 2024-25"
    )
    tax_regime: Mapped[str] = mapped_column(
        String(10), nullable=False, default="new", comment="old | new"
    )
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    residential_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="resident"
    )
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="tax_profile")  # noqa: F821

    def __repr__(self) -> str:
        return f"<TaxProfile user={self.user_id} fy={self.financial_year}>"
