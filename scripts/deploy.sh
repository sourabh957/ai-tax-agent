#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Build, push Docker images to ECR, then restart the app on EC2
#
# Usage:
#   ./scripts/deploy.sh [IMAGE_TAG]
#   IMAGE_TAG defaults to the short git SHA.
#
# Prerequisites:
#   - AWS CLI configured (profile or EC2 instance profile)
#   - Docker installed and running
#   - Terraform applied (ec2_public_ip and ecr_repository_url outputs exist)
#   - SSH key available (or set SSH_KEY_FILE env var)
# =============================================================================
set -euo pipefail

IMAGE_TAG="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"
TERRAFORM_DIR="infra/terraform/environments/dev"
KEY_FILE="${SSH_KEY_FILE:-~/.ssh/taxly-ec2.pem}"
SSH_USER="${SSH_USER:-ec2-user}"

echo "==> Taxly Deploy [tag=${IMAGE_TAG}]"
echo ""

# ── 1. Verify AWS identity ────────────────────────────────────────────────────
echo "==> Verifying AWS identity..."
aws sts get-caller-identity
echo ""

# ── 2. Read Terraform outputs ────────────────────────────────────────────────
echo "==> Reading Terraform outputs from ${TERRAFORM_DIR}..."
EC2_IP=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ec2_public_ip 2>/dev/null) || {
    echo "ERROR: Could not read ec2_public_ip. Run: terraform apply -var-file=dev.tfvars"
    exit 1
}
REGION=$(terraform -chdir="${TERRAFORM_DIR}" output -raw aws_region 2>/dev/null || echo "ap-south-1")

# Single ECR repo — backend tagged :api-latest, frontend tagged :frontend-latest
ECR_REPO=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ecr_repository_url 2>/dev/null) || {
    echo "ERROR: Could not read ecr_repository_url."
    exit 1
}
ECR_REGISTRY="${ECR_REPO%%/*}"
DOMAIN_NAME="${DOMAIN_NAME:-}"

echo "  EC2 IP:       ${EC2_IP}"
echo "  Region:       ${REGION}"
echo "  ECR repo:     ${ECR_REPO}"
echo ""

# ── 3. ECR login ──────────────────────────────────────────────────────────────
echo "==> Authenticating Docker to ECR..."
aws ecr get-login-password --region "${REGION}" \
    | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
echo ""

# ── 4. Build and push API (backend) ──────────────────────────────────────────
echo "==> Building API image..."
docker build -t taxly-api:build -f Dockerfile .
docker tag taxly-api:build "${ECR_REPO}:api-${IMAGE_TAG}"
docker tag taxly-api:build "${ECR_REPO}:api-latest"
docker push "${ECR_REPO}:api-${IMAGE_TAG}"
docker push "${ECR_REPO}:api-latest"
echo "  Pushed: ${ECR_REPO}:api-latest  (also tagged :api-${IMAGE_TAG})"
echo ""

# ── 5. Build and push Frontend ────────────────────────────────────────────────
API_BASE="${DOMAIN_NAME:+https://${DOMAIN_NAME}}"
API_BASE="${API_BASE:-http://${EC2_IP}}"
echo "==> Building frontend image (NEXT_PUBLIC_API_BASE_URL=${API_BASE})..."
docker build \
    --build-arg NEXT_PUBLIC_API_BASE_URL="${API_BASE}" \
    --build-arg NEXT_PUBLIC_APP_NAME="Taxly" \
    -t taxly-frontend:build \
    -f frontend/Dockerfile \
    frontend/
docker tag taxly-frontend:build "${ECR_REPO}:frontend-${IMAGE_TAG}"
docker tag taxly-frontend:build "${ECR_REPO}:frontend-latest"
docker push "${ECR_REPO}:frontend-${IMAGE_TAG}"
docker push "${ECR_REPO}:frontend-latest"
echo "  Pushed: ${ECR_REPO}:frontend-latest  (also tagged :frontend-${IMAGE_TAG})"
echo ""

# ── 6. Restart the app on EC2 via SSH ────────────────────────────────────────
if [ ! -f "${KEY_FILE}" ]; then
    echo "==> SSH key not found at ${KEY_FILE}. Skipping remote restart."
    echo "    Manually restart with:"
    echo "      ssh -i <key> ${SSH_USER}@${EC2_IP} 'sudo systemctl restart taxly-compose'"
    exit 0
fi

echo "==> Restarting Taxly on EC2 [${EC2_IP}]..."
ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=no "${SSH_USER}@${EC2_IP}" "
    set -e
    echo '--- Fetching latest secrets and images ---'
    sudo /usr/local/bin/taxly-fetch-secrets.sh
    sudo docker compose -f /opt/taxly/docker-compose.yml pull
    sudo docker compose -f /opt/taxly/docker-compose.yml up -d
    sleep 15
    echo '--- Health checks ---'
    curl -sf http://localhost:8000/api/v1/health && echo 'API: OK' || echo 'API: NOT ready yet'
    curl -sf http://localhost:3000 && echo 'Frontend: OK' || echo 'Frontend: NOT ready yet'
    echo 'Deploy complete: tag=${IMAGE_TAG}'
"

echo ""
echo "==> Done!"
echo "    App:    http://${DOMAIN_NAME:-${EC2_IP}}"
echo "    Health: http://${DOMAIN_NAME:-${EC2_IP}}/api/v1/health"
echo "    Logs:   aws logs tail \$(terraform -chdir=${TERRAFORM_DIR} output -raw app_log_group) --follow"

