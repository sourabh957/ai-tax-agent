#!/usr/bin/env bash
# =============================================================================
# populate_secrets.sh — Populate AWS Secrets Manager with runtime secret values
#
# Run this ONCE after `terraform apply` before starting the EC2 app stack.
# The secrets CONTAINERS are created by Terraform; this script fills in the values.
#
# Usage:
#   ./scripts/populate_secrets.sh
#
# Environment variables you can pre-export to skip interactive prompts:
#   QDRANT_API_KEY       — Qdrant Cloud API key
#   QDRANT_URL           — Qdrant Cloud cluster URL  (e.g. https://xyz.qdrant.io)
#   OIDC_CLIENT_SECRET   — OIDC provider client secret (leave empty to skip)
#
# The DB credential secret is auto-populated by Terraform (from db_username/db_password).
# Verify it is set correctly with:
#   aws secretsmanager get-secret-value --secret-id ai-tax-agent-dev/db-credentials
# =============================================================================
set -euo pipefail

TERRAFORM_DIR="${TERRAFORM_DIR:-infra/terraform/environments/dev}"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}==> $*${NC}"; }
success() { echo -e "${GREEN}    ✓ $*${NC}"; }
warn()    { echo -e "${YELLOW}    ⚠ $*${NC}"; }

# ── Verify AWS identity ───────────────────────────────────────────────────────
info "Verifying AWS identity..."
aws sts get-caller-identity
echo ""

# ── Read Terraform outputs ────────────────────────────────────────────────────
info "Reading Terraform outputs from ${TERRAFORM_DIR}..."
REGION=$(terraform -chdir="${TERRAFORM_DIR}" output -raw aws_region 2>/dev/null || echo "ap-south-1")
QDRANT_SECRET=$(terraform -chdir="${TERRAFORM_DIR}" output -raw 2>/dev/null \
    | grep -E '^qdrant_api_key_secret_name' | awk -F' = ' '{print $2}' || true)

# Fallback: derive names from project/environment pattern
if [ -z "${QDRANT_SECRET:-}" ]; then
    QDRANT_SECRET="ai-tax-agent-dev/qdrant-api-key"
fi
OIDC_SECRET="ai-tax-agent-dev/oidc-credentials"
DB_SECRET="ai-tax-agent-dev/db-credentials"

echo "  Region:        ${REGION}"
echo "  DB secret:     ${DB_SECRET}"
echo "  Qdrant secret: ${QDRANT_SECRET}"
echo "  OIDC secret:   ${OIDC_SECRET}"
echo ""

# ── Verify DB secret ──────────────────────────────────────────────────────────
info "Checking DB credentials secret..."
DB_VALUE=$(aws secretsmanager get-secret-value \
    --secret-id "${DB_SECRET}" --region "${REGION}" \
    --query SecretString --output text 2>/dev/null || echo "")

if [ -n "${DB_VALUE}" ] && echo "${DB_VALUE}" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('host')" 2>/dev/null; then
    success "DB credentials already set."
else
    warn "DB credentials secret appears empty or incomplete."
    warn "Terraform should have populated this from dev.tfvars db_username/db_password."
    warn "If not set, run:"
    warn "  aws secretsmanager put-secret-value --region ${REGION} \\"
    warn "    --secret-id ${DB_SECRET} \\"
    warn "    --secret-string '{\"username\":\"taxly_user\",\"password\":\"<pass>\",\"host\":\"<rds-host>\",\"port\":\"5432\",\"dbname\":\"tax_agent\"}'"
fi
echo ""

# ── Qdrant API key ────────────────────────────────────────────────────────────
info "Setting Qdrant API key..."
if [ -z "${QDRANT_API_KEY:-}" ]; then
    echo -n "  Enter Qdrant API key (press Enter to skip): "
    read -r -s QDRANT_API_KEY
    echo ""
fi

if [ -n "${QDRANT_API_KEY}" ]; then
    # Also ask/use QDRANT_URL if not set
    if [ -z "${QDRANT_URL:-}" ]; then
        echo -n "  Enter Qdrant cluster URL (e.g. https://xyz.qdrant.io, Enter to skip): "
        read -r QDRANT_URL
    fi
    aws secretsmanager put-secret-value \
        --secret-id "${QDRANT_SECRET}" \
        --region "${REGION}" \
        --secret-string "{\"api_key\":\"${QDRANT_API_KEY}\",\"url\":\"${QDRANT_URL:-}\"}" \
        --output none
    success "Qdrant API key stored in Secrets Manager."
else
    warn "Qdrant API key skipped. RAG features will not work until this is set."
fi
echo ""

# ── OIDC client secret ────────────────────────────────────────────────────────
info "Setting OIDC client secret (optional — skip if not using OIDC auth)..."
if [ -z "${OIDC_CLIENT_SECRET:-}" ]; then
    echo -n "  Enter OIDC client secret (Enter to skip): "
    read -r -s OIDC_CLIENT_SECRET
    echo ""
fi

if [ -n "${OIDC_CLIENT_SECRET}" ]; then
    aws secretsmanager put-secret-value \
        --secret-id "${OIDC_SECRET}" \
        --region "${REGION}" \
        --secret-string "{\"client_secret\":\"${OIDC_CLIENT_SECRET}\"}" \
        --output none
    success "OIDC client secret stored in Secrets Manager."
else
    warn "OIDC secret skipped. JWT fallback auth will be used in development mode."
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
info "Done! Next steps:"
echo "  1. Verify secrets are readable from EC2:"
echo "       aws secretsmanager get-secret-value --secret-id ${DB_SECRET} --region ${REGION}"
echo ""
echo "  2. Restart the app stack on EC2 to pick up new secrets:"
echo "       EC2_IP=\$(terraform -chdir=${TERRAFORM_DIR} output -raw ec2_public_ip)"
echo "       ssh -i ~/.ssh/your-key.pem ec2-user@\$EC2_IP \\"
echo "         'sudo systemctl restart taxly-compose'"
echo ""
echo "  3. Run the deployment health check:"
echo "       ./scripts/check_deployment.sh"
