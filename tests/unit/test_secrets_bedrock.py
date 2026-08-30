"""
Tests for Milestones 34 + 35 + 36:
    - Secrets Manager client (mocked boto3)
    - build_database_url_from_secret
    - Bedrock check functions (mocked boto3)
    - Script existence checks (M36)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.core.secrets import (
    SecretsManagerClient,
    build_database_url_from_secret,
    validate_secret_access,
)
from app.core.bedrock_check import (
    check_aws_credentials,
    check_bedrock_model_access,
    check_bedrock_model_listed,
    run_bedrock_checks,
)


# ============================================================
# SecretsManagerClient
# ============================================================

def make_secrets_client(region="ap-south-1"):
    client = SecretsManagerClient(region=region)
    return client


def test_get_secret_string_success():
    mock_boto = MagicMock()
    mock_boto.get_secret_value.return_value = {"SecretString": "my-secret-value"}

    client = make_secrets_client()
    client._client = mock_boto

    result = client.get_secret_string("my-secret")
    assert result == "my-secret-value"


def test_get_secret_string_failure_raises():
    mock_boto = MagicMock()
    mock_boto.get_secret_value.side_effect = Exception("AccessDenied")

    client = make_secrets_client()
    client._client = mock_boto

    with pytest.raises(RuntimeError, match="Failed to fetch secret"):
        client.get_secret_string("my-secret")


def test_get_secret_json_success():
    data = {"username": "admin", "password": "secret", "host": "db.example.com", "dbname": "tax"}
    mock_boto = MagicMock()
    mock_boto.get_secret_value.return_value = {"SecretString": json.dumps(data)}

    client = make_secrets_client()
    client._client = mock_boto

    result = client.get_secret_json("my-secret")
    assert result["username"] == "admin"
    assert result["host"] == "db.example.com"


def test_get_secret_json_invalid_json_raises():
    mock_boto = MagicMock()
    mock_boto.get_secret_value.return_value = {"SecretString": "not-json"}

    client = make_secrets_client()
    client._client = mock_boto

    with pytest.raises(ValueError, match="not valid JSON"):
        client.get_secret_json("my-secret")


def test_secret_exists_true():
    mock_boto = MagicMock()
    mock_boto.get_secret_value.return_value = {"SecretString": "value"}

    client = make_secrets_client()
    client._client = mock_boto

    assert client.secret_exists("my-secret") is True


def test_secret_exists_false():
    mock_boto = MagicMock()
    mock_boto.get_secret_value.side_effect = Exception("ResourceNotFoundException")

    client = make_secrets_client()
    client._client = mock_boto

    assert client.secret_exists("missing-secret") is False


# ============================================================
# build_database_url_from_secret
# ============================================================

def test_build_database_url_success():
    secret_data = {
        "username": "tax_user",
        "password": "s3cr3t",
        "host": "db.ap-south-1.rds.amazonaws.com",
        "port": "5432",
        "dbname": "tax_agent",
    }

    with patch("app.core.secrets.SecretsManagerClient") as MockClient:
        instance = MockClient.return_value
        instance.get_secret_json.return_value = secret_data

        url = build_database_url_from_secret("my-secret", "ap-south-1")

    assert url.startswith("postgresql+asyncpg://")
    assert "tax_user" in url
    assert "db.ap-south-1.rds.amazonaws.com" in url
    assert "tax_agent" in url


def test_build_database_url_missing_field_raises():
    secret_data = {"username": "user", "host": "db.example.com"}
    # missing: password, dbname

    with patch("app.core.secrets.SecretsManagerClient") as MockClient:
        instance = MockClient.return_value
        instance.get_secret_json.return_value = secret_data

        with pytest.raises(ValueError, match="missing required fields"):
            build_database_url_from_secret("my-secret", "ap-south-1")


def test_validate_secret_access_returns_false_on_error():
    with patch("app.core.secrets.SecretsManagerClient") as MockClient:
        instance = MockClient.return_value
        instance.secret_exists.side_effect = Exception("network error")

        result = validate_secret_access("my-secret", "ap-south-1")
        assert result is False


# ============================================================
# Bedrock checks
# ============================================================

def test_check_aws_credentials_success():
    with patch("boto3.client") as mock_client:
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Account": "123456789012",
            "Arn": "arn:aws:iam::123456789012:role/test-role",
        }
        mock_client.return_value = mock_sts
        passed, detail = check_aws_credentials()
    assert passed is True
    assert "123456789012" in detail


def test_check_aws_credentials_failure():
    with patch("boto3.client") as mock_client:
        mock_client.return_value.get_caller_identity.side_effect = Exception("NoCredentialsError")
        passed, detail = check_aws_credentials()
    assert passed is False


def test_check_bedrock_model_listed_found():
    with patch("boto3.client") as mock_client:
        mock_bedrock = MagicMock()
        mock_bedrock.list_foundation_models.return_value = {
            "modelSummaries": [
                {"modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0"},
                {"modelId": "amazon.titan-embed-text-v2:0"},
            ]
        }
        mock_client.return_value = mock_bedrock
        passed, detail = check_bedrock_model_listed(
            "anthropic.claude-3-5-sonnet-20241022-v2:0", "ap-south-1"
        )
    assert passed is True


def test_check_bedrock_model_listed_not_found():
    with patch("boto3.client") as mock_client:
        mock_bedrock = MagicMock()
        mock_bedrock.list_foundation_models.return_value = {"modelSummaries": []}
        mock_client.return_value = mock_bedrock
        passed, detail = check_bedrock_model_listed("unknown-model", "ap-south-1")
    assert passed is False
    assert "not found" in detail.lower()


def test_check_bedrock_access_denied_gives_clear_message():
    with patch("boto3.client") as mock_client:
        mock_br = MagicMock()
        mock_br.converse.side_effect = Exception("AccessDeniedException")
        mock_client.return_value = mock_br
        passed, detail = check_bedrock_model_access(
            "anthropic.claude-3-5-sonnet-20241022-v2:0", "ap-south-1"
        )
    assert passed is False
    assert "Access denied" in detail or "IAM" in detail


def test_run_bedrock_checks_no_inference():
    with patch("app.core.bedrock_check.check_aws_credentials") as mock_cred, \
         patch("app.core.bedrock_check.check_bedrock_model_listed") as mock_list:

        mock_cred.return_value = (True, "account=123")
        mock_list.return_value = (True, "Model available")

        results = run_bedrock_checks(
            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
            region="ap-south-1",
            run_inference_check=False,
        )

    assert len(results) == 2
    assert all(r["passed"] for r in results)


def test_run_bedrock_checks_stops_on_credential_failure():
    with patch("app.core.bedrock_check.check_aws_credentials") as mock_cred:
        mock_cred.return_value = (False, "No credentials found")

        results = run_bedrock_checks("model", "ap-south-1")

    # Should stop after credential check — no further checks without credentials
    assert len(results) == 1
    assert results[0]["passed"] is False


# ============================================================
# M36 — Script existence and content
# ============================================================

def test_deploy_ecr_script_exists():
    import os
    assert os.path.exists("scripts/deploy_ecr.sh")


def test_validate_terraform_script_exists():
    import os
    assert os.path.exists("scripts/validate_terraform.sh")


def test_run_tests_script_exists():
    import os
    assert os.path.exists("scripts/run_tests.sh")


def test_deploy_ecr_script_content():
    with open("scripts/deploy_ecr.sh") as f:
        content = f.read()
    assert "aws ecr get-login-password" in content
    assert "docker build" in content
    assert "docker push" in content
    assert "terraform output" in content


def test_validate_terraform_script_content():
    with open("scripts/validate_terraform.sh") as f:
        content = f.read()
    assert "terraform fmt" in content
    assert "terraform validate" in content
    assert "terraform plan" in content
    # Must not actually execute terraform apply (only mention it in warnings is ok)
    # Check the key safety note is present
    assert "Never" in content or "never" in content
    assert "auto-apply" in content or "without" in content
