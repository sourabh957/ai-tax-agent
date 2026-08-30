"""
Bedrock access validation — Milestone 35.

Verifies that:
    1. AWS credentials are available (credential chain)
    2. The configured Bedrock model exists in the configured region
    3. The ECS task role (or local profile) has bedrock:InvokeModel permission

This check runs at startup (via config_check.py) so the application fails
fast with a clear error instead of failing on the first user request.

Architecture:
    Development:
        AWS CLI profile → boto3 credential chain → Bedrock Runtime
        Permission source: IAM user/role attached to the CLI profile

    Production (ECS):
        ECS task role → boto3 credential chain → Bedrock Runtime
        Permission source: IAM task role (created by infra/terraform/modules/iam)
        No access keys required — the role is assumed automatically.

IAM policy required (created by Terraform IAM module):
    {
        "Effect": "Allow",
        "Action": [
            "bedrock:InvokeModel",
            "bedrock:InvokeModelWithResponseStream"
        ],
        "Resource": "arn:aws:bedrock:<region>::foundation-model/<model-id>"
    }
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def check_aws_credentials() -> tuple[bool, str]:
    """
    Verify AWS credentials are available via the credential chain.

    Returns:
        (True, identity_info) if credentials are available.
        (False, error_message) if credentials cannot be resolved.
    """
    try:
        import boto3
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        info = (
            f"account={identity.get('Account', '?')} "
            f"arn={identity.get('Arn', '?')}"
        )
        return True, info
    except Exception as exc:
        return False, str(exc)


def check_bedrock_model_access(model_id: str, region: str) -> tuple[bool, str]:
    """
    Verify the configured Bedrock model is accessible.

    Sends a minimal inference request to confirm:
    - The model exists in the region
    - The credential chain has bedrock:InvokeModel permission

    This uses a very short max_tokens to minimise cost (~0.001 cents).

    Returns:
        (True, message) if accessible.
        (False, error_message) if not.
    """
    try:
        import boto3
        import json

        client = boto3.client("bedrock-runtime", region_name=region)

        # Minimal prompt to verify access without meaningful cost
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Reply with: ok"}],
                }
            ],
            inferenceConfig={"maxTokens": 5, "temperature": 0.0},
        )

        stop_reason = response.get("stopReason", "")
        usage = response.get("usage", {})
        return True, (
            f"model accessible, stopReason={stop_reason}, "
            f"inputTokens={usage.get('inputTokens', 0)}"
        )

    except Exception as exc:
        error_str = str(exc)

        # Provide actionable guidance for common errors
        if "AccessDenied" in error_str or "UnauthorizedOperation" in error_str:
            return False, (
                f"Access denied to model '{model_id}' in region '{region}'. "
                "Check the IAM policy attached to your role/profile. "
                "Required action: bedrock:InvokeModel on the model ARN."
            )
        if "ResourceNotFoundException" in error_str or "ValidationException" in error_str:
            return False, (
                f"Model '{model_id}' not found in region '{region}'. "
                "Verify the model ID and that Bedrock is available in this region. "
                "Check: https://docs.aws.amazon.com/bedrock/latest/userguide/models-regions.html"
            )
        if "NoCredentialsError" in error_str or "credentials" in error_str.lower():
            return False, (
                "AWS credentials not found. "
                "For local development: run 'aws configure' or set AWS_PROFILE. "
                "For ECS: ensure the task role has bedrock:InvokeModel permission."
            )

        return False, f"Bedrock access check failed: {error_str}"


def check_bedrock_model_listed(model_id: str, region: str) -> tuple[bool, str]:
    """
    Check if the model is listed as available in Bedrock (non-billable check).

    Uses bedrock:ListFoundationModels — less accurate than a real invocation
    but does not incur inference costs.

    Returns:
        (True, message) if model is listed.
        (False, message) if not found or access denied.
    """
    try:
        import boto3
        client = boto3.client("bedrock", region_name=region)
        response = client.list_foundation_models()
        models = response.get("modelSummaries", [])
        model_ids = [m.get("modelId", "") for m in models]

        if model_id in model_ids:
            return True, f"Model '{model_id}' is available in {region}"

        # Check if a cross-region inference profile matches
        prefixes = [mid.split(".")[0] for mid in model_ids]
        if any(model_id.startswith(p) for p in prefixes):
            return True, f"Model '{model_id}' matched via prefix in {region}"

        return False, (
            f"Model '{model_id}' not found in Bedrock model list for region '{region}'. "
            f"Available models include: {model_ids[:5]}..."
        )
    except Exception as exc:
        return False, f"Could not list Bedrock models: {exc}"


def run_bedrock_checks(
    model_id: str,
    region: str,
    run_inference_check: bool = False,
) -> list[dict[str, Any]]:
    """
    Run all Bedrock readiness checks.

    Args:
        model_id:            The Bedrock model ID from BEDROCK_MODEL_ID.
        region:              AWS region from AWS_REGION.
        run_inference_check: If True, sends a real (minimal) inference request.
                             If False, only checks credentials and model listing.
                             Set False by default to avoid charges on every startup.

    Returns:
        List of check result dicts with keys: name, passed, detail.
    """
    results = []

    # 1. AWS credentials
    passed, detail = check_aws_credentials()
    results.append({"name": "AWS credentials", "passed": passed, "detail": detail})
    if not passed:
        return results  # No point continuing if credentials are broken

    # 2. Model listed in Bedrock
    passed, detail = check_bedrock_model_listed(model_id, region)
    results.append({"name": "Bedrock model listed", "passed": passed, "detail": detail})

    # 3. Optional: real inference check (billable, ~0.001 cents)
    if run_inference_check:
        passed, detail = check_bedrock_model_access(model_id, region)
        results.append({"name": "Bedrock inference", "passed": passed, "detail": detail})

    return results
