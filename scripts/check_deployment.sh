#!/usr/bin/env bash
# =============================================================================
# check_deployment.sh — Verify the Taxly app is running on EC2
#
# Usage:
#   ./scripts/check_deployment.sh
#   EC2_IP=1.2.3.4 ./scripts/check_deployment.sh   # skip Terraform lookup
# =============================================================================
set -euo pipefail

TERRAFORM_DIR="${TERRAFORM_DIR:-infra/terraform/environments/dev}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
info() { echo -e "${CYAN}==> $*${NC}"; }

PASS=0; FAIL=0

check_http() {
    local label="$1" url="$2" expected_status="${3:-200}"
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${url}" 2>/dev/null || echo "000")
    if [ "${status}" = "${expected_status}" ]; then
        ok "${label} → HTTP ${status}"
        PASS=$((PASS+1))
    elif [ "${status}" != "000" ]; then
        warn "${label} → HTTP ${status} (expected ${expected_status})"
        FAIL=$((FAIL+1))
    else
        fail "${label} → No response (connection refused or timeout)"
        FAIL=$((FAIL+1))
    fi
}

# ── Read Terraform outputs ────────────────────────────────────────────────────
if [ -z "${EC2_IP:-}" ]; then
    info "Reading Terraform outputs from ${TERRAFORM_DIR}..."
    EC2_IP=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ec2_public_ip 2>/dev/null) || {
        echo "ERROR: Could not read ec2_public_ip. Export EC2_IP= or run terraform apply first."
        exit 1
    }
fi

REGION=$(terraform -chdir="${TERRAFORM_DIR}" output -raw aws_region 2>/dev/null || echo "ap-south-1")
LOG_GROUP=$(terraform -chdir="${TERRAFORM_DIR}" output -raw app_log_group 2>/dev/null || echo "/ecs/taxly")

echo ""
info "Checking deployment at http://${EC2_IP}"
echo ""

# ── HTTP health checks ────────────────────────────────────────────────────────
info "HTTP endpoints..."
check_http "API health"      "http://${EC2_IP}/api/v1/health"
check_http "API ready"       "http://${EC2_IP}/api/v1/ready" "200"
check_http "Frontend home"   "http://${EC2_IP}/"
echo ""

# ── EC2 instance status ───────────────────────────────────────────────────────
info "EC2 instance status..."
INSTANCE_STATE=$(aws ec2 describe-instances \
    --filters "Name=ip-address,Values=${EC2_IP}" \
    --query "Reservations[*].Instances[*].State.Name" \
    --output text --region "${REGION}" 2>/dev/null || echo "unknown")

if [ "${INSTANCE_STATE}" = "running" ]; then
    ok "EC2 instance: ${INSTANCE_STATE}"
    PASS=$((PASS+1))
else
    fail "EC2 instance: ${INSTANCE_STATE}"
    FAIL=$((FAIL+1))
fi
echo ""

# ── ECR images ────────────────────────────────────────────────────────────────
info "ECR images..."
ECR_REPO=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ecr_repository_url 2>/dev/null) || ECR_REPO=""
if [ -n "${ECR_REPO}" ]; then
    REPO_NAME="${ECR_REPO##*/}"
    for tag in api-latest frontend-latest; do
        exists=$(aws ecr list-images --repository-name "${REPO_NAME}" --region "${REGION}" \
            --query "imageIds[?imageTag=='${tag}'].imageTag" --output text 2>/dev/null || echo "")
        if [ -n "${exists}" ]; then
            ok "ECR image: ${REPO_NAME}:${tag}"
            PASS=$((PASS+1))
        else
            fail "ECR image: ${REPO_NAME}:${tag} NOT FOUND — run: ./scripts/deploy.sh"
            FAIL=$((FAIL+1))
        fi
    done
fi
echo ""

# ── Secrets Manager ───────────────────────────────────────────────────────────
info "Secrets Manager..."
for secret in "ai-tax-agent-dev/db-credentials" "ai-tax-agent-dev/qdrant-api-key"; do
    value=$(aws secretsmanager get-secret-value \
        --secret-id "${secret}" --region "${REGION}" \
        --query SecretString --output text 2>/dev/null || echo "")
    if [ -n "${value}" ] && [ "${value}" != "{}" ]; then
        ok "Secret: ${secret}"
        PASS=$((PASS+1))
    else
        warn "Secret: ${secret} — empty (run ./scripts/populate_secrets.sh)"
        FAIL=$((FAIL+1))
    fi
done
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "──────────────────────────────────────────────"
echo -e "  Passed: ${GREEN}${PASS}${NC}  Failed/Warned: ${RED}${FAIL}${NC}"
echo "──────────────────────────────────────────────"
echo ""
if [ "${FAIL}" -gt 0 ]; then
    echo "Troubleshooting:"
    echo "  • View EC2 boot log:    aws ec2 get-console-output --instance-id <id> --region ${REGION}"
    echo "  • View app logs:        aws logs tail ${LOG_GROUP} --follow --region ${REGION}"
    echo "  • SSH to instance:      ssh -i ~/.ssh/key.pem ec2-user@${EC2_IP}"
    echo "  • Check compose status: sudo docker compose -f /opt/taxly/docker-compose.yml ps"
    echo "  • Re-run secrets fetch: sudo /usr/local/bin/taxly-fetch-secrets.sh"
    echo "  • Restart stack:        sudo systemctl restart taxly-compose"
    exit 1
else
    echo -e "${GREEN}Deployment looks healthy!${NC}"
fi
