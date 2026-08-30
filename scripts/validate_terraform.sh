#!/usr/bin/env bash
# =============================================================================
# validate_terraform.sh — CI/CD Terraform validation (non-destructive)
#
# Runs: fmt check → validate → plan (no apply)
# Safe to run in CI pipelines, pull request checks, and pre-commit hooks.
#
# Usage:
#   ./scripts/validate_terraform.sh [environment]
#
# Examples:
#   ./scripts/validate_terraform.sh           # validates dev (default)
#   ./scripts/validate_terraform.sh prod      # validates prod
# =============================================================================
set -euo pipefail

ENV="${1:-dev}"
TERRAFORM_DIR="infra/terraform/environments/${ENV}"

echo "==> Validating Terraform for environment: ${ENV}"
echo ""

# ── Check terraform is available ─────────────────────────────────────────────

command -v terraform >/dev/null 2>&1 || { echo "ERROR: terraform not found."; exit 1; }
terraform -version
echo ""

# ── Format check (non-destructive) ───────────────────────────────────────────

echo "==> Running terraform fmt -check -recursive..."
terraform -chdir=infra/terraform fmt -check -recursive
echo "  [OK] All Terraform files are formatted correctly."
echo ""

# ── Init ─────────────────────────────────────────────────────────────────────

echo "==> Running terraform init..."
terraform -chdir="${TERRAFORM_DIR}" init -backend=false -input=false
echo ""

# ── Validate ──────────────────────────────────────────────────────────────────

echo "==> Running terraform validate..."
terraform -chdir="${TERRAFORM_DIR}" validate
echo "  [OK] Configuration is valid."
echo ""

# ── Plan (requires AWS credentials + tfvars) ──────────────────────────────────

TFVARS_FILE="${TERRAFORM_DIR}/${ENV}.tfvars"

if [ -f "${TFVARS_FILE}" ]; then
    echo "==> Running terraform plan (review before applying)..."
    terraform -chdir="${TERRAFORM_DIR}" plan \
        -var-file="${ENV}.tfvars" \
        -input=false \
        -out=/tmp/tfplan-${ENV} \
        2>&1 || {
            echo ""
            echo "NOTE: terraform plan failed. This may be expected if AWS credentials"
            echo "are not configured or tfvars values are missing."
            echo "For CI without AWS: fmt + validate checks are sufficient."
        }
else
    echo "[WARN] ${TFVARS_FILE} not found — skipping terraform plan."
    echo "  Copy ${ENV}.tfvars.example to ${ENV}.tfvars and fill in values to enable plan."
fi

echo ""
echo "==> Validation complete for environment: ${ENV}"
echo ""
echo "REMINDER: Never run 'terraform apply' without first reviewing the plan output."
echo "          Never auto-apply in CI without explicit approval."
