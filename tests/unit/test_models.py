"""
Unit tests for database models — no live database required.

Tests only model structure, defaults, and repr — no actual DB operations.
"""

from __future__ import annotations

import uuid

from app.db.models.agent_run import AgentRun
from app.db.models.tax_profile import TaxProfile
from app.db.models.user import User


def test_user_tablename():
    assert User.__tablename__ == "users"


def test_tax_profile_tablename():
    assert TaxProfile.__tablename__ == "tax_profiles"


def test_agent_run_tablename():
    assert AgentRun.__tablename__ == "agent_runs"


def test_user_repr():
    u = User(id="test-id", email="test@example.com", hashed_password="x")
    assert "test@example.com" in repr(u)


def test_agent_run_default_status():
    """AgentRun default status should be 'pending'."""
    # Access column default directly from the mapped column
    col = AgentRun.__table__.c["status"]
    assert col.default.arg == "pending"


def test_tax_profile_default_regime():
    col = TaxProfile.__table__.c["tax_regime"]
    assert col.default.arg == "new"


def test_all_models_share_base():
    """All models must use the same declarative base (critical for Alembic)."""
    from app.db.base import Base

    assert issubclass(User, Base)
    assert issubclass(TaxProfile, Base)
    assert issubclass(AgentRun, Base)
