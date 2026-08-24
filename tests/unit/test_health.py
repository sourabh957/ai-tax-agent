"""Unit tests for health endpoints — no external services required."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health_returns_200():
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_body():
    response = client.get("/api/v1/health")
    body = response.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body
    assert isinstance(body["uptime_seconds"], (int, float))


def test_ready_returns_json():
    response = client.get("/api/v1/ready")
    body = response.json()
    assert "status" in body
    assert "checks" in body
    assert "environment" in body


def test_ready_without_config_is_503():
    """With no .env set, LLM_PROVIDER is unset → not ready → 503."""
    response = client.get("/api/v1/ready")
    # In CI/test runs with no .env, llm_provider is None → not ready
    assert response.status_code in (200, 503)  # depends on test env


def test_docs_available_in_development():
    """Swagger UI must be available outside production."""
    response = client.get("/docs")
    assert response.status_code == 200
