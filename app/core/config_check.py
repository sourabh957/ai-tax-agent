"""
Configuration validation utility.

Usage:
    python -m app.core.config_check

Validates all configuration without exposing secret values.
"""

from __future__ import annotations

import sys


def _status(ok: bool, label: str, detail: str = "") -> None:
    icon = "[OK]  " if ok else "[ERROR]"
    line = f"{icon} {label}"
    if detail:
        line += f" — {detail}"
    print(line)


def _warn(label: str, detail: str = "") -> None:
    line = f"[WARN] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


def run_checks() -> bool:  # returns True if all required checks pass
    errors = False

    try:
        from app.core.config import get_settings

        settings = get_settings()
    except Exception as exc:
        print(f"[ERROR] Failed to load configuration: {exc}")
        return False

    # Application
    _status(True, "Application configuration", f"env={settings.app_env}, log_level={settings.log_level}")

    # Database
    if settings.database_url:
        _status(True, "Database configuration", "DATABASE_URL is set")
    else:
        _warn("Database configuration", "DATABASE_URL is not set (required for database operations)")

    # Qdrant
    if settings.qdrant_url:
        _status(True, "Qdrant configuration", "QDRANT_URL is set")
    else:
        _warn("Qdrant configuration", "QDRANT_URL is not set (required for RAG operations)")

    if not settings.qdrant_collection:
        _warn("Qdrant collection", "QDRANT_COLLECTION is not set")

    # AWS
    if settings.aws_region:
        _status(True, "AWS configuration", f"region={settings.aws_region}")
    else:
        _warn("AWS configuration", "AWS_REGION is not set")

    # S3
    if settings.s3_bucket_name:
        _status(True, "S3 configuration", "S3_BUCKET_NAME is set")
    else:
        _warn("S3 configuration", "S3_BUCKET_NAME is not set")

    # LLM
    if settings.llm_provider:
        _status(True, "LLM provider", f"provider={settings.llm_provider}")
    else:
        _warn("LLM provider", "LLM_PROVIDER is not set — agent will not be able to call LLM")

    if settings.llm_provider == "bedrock":
        if settings.bedrock_model_id:
            _status(True, "Bedrock configuration", "BEDROCK_MODEL_ID is set")
        else:
            print("[ERROR] BEDROCK_MODEL_ID is required when LLM_PROVIDER=bedrock")
            errors = True

        # Bedrock IAM check (non-billable: credential + model listing only)
        if settings.aws_region and settings.bedrock_model_id:
            try:
                from app.core.bedrock_check import run_bedrock_checks
                bedrock_results = run_bedrock_checks(
                    model_id=settings.bedrock_model_id,
                    region=settings.aws_region,
                    run_inference_check=False,  # non-billable startup check
                )
                for r in bedrock_results:
                    if r["passed"]:
                        _status(True, f"Bedrock: {r['name']}", r["detail"])
                    else:
                        _warn(f"Bedrock: {r['name']}", r["detail"])
            except Exception as exc:
                _warn("Bedrock checks", f"Could not run Bedrock checks: {exc}")

    if settings.llm_provider == "openai":
        if settings.llm_api_key:
            _status(True, "OpenAI configuration", "LLM_API_KEY is set")
        else:
            print("[ERROR] LLM_API_KEY is required when LLM_PROVIDER=openai")
            errors = True

    # Agent limits
    _status(
        True,
        "Agent limits",
        f"iterations={settings.max_agent_iterations}, "
        f"tool_calls={settings.max_tool_calls}, "
        f"llm_calls={settings.max_llm_calls}",
    )

    # Rate limiting
    _status(True, "Rate limiting", f"daily_request_limit={settings.daily_request_limit}")

    return not errors


def main() -> None:
    print("=" * 60)
    print("AI Tax Agent — Configuration Check")
    print("=" * 60)
    ok = run_checks()
    print("=" * 60)
    if ok:
        print("Configuration check passed.")
    else:
        print("Configuration check FAILED. Fix errors before starting the server.")
        sys.exit(1)


if __name__ == "__main__":
    main()
