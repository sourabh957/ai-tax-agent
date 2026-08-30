#!/usr/bin/env bash
# =============================================================================
# deploy_ecr.sh — Build and push the AI Tax Agent Docker image to ECR
#
# Usage:
#   ./scripts/deploy_ecr.sh [IMAGE_TAG]
#
# Prerequisites:
#   - AWS CLI configured (aws configure) or running on ECS with task role
#   - Docker installed and running
#   - Terraform applied (to create ECR repository)
#   - Run from the repository root
#
# Examples:
#   ./scripts/deploy_ecr.sh                 # pushes as 'latest'
#   ./scripts/deploy_ecr.sh v1.0.0          # pushes as 'v1.0.0'
#   ./scripts/deploy_ecr.sh $(git rev-parse --short HEAD)  # git SHA tag
# =============================================================================
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

IMAGE_TAG="${1:-latest}"
TERRAFORM_ENV="dev"
TERRAFORM_DIR="infra/terraform/environments/${TERRAFORM_ENV}"

# ── Validate prerequisites ────────────────────────────────────────────────────

command -v aws    >/dev/null 2>&1 || { echo "ERROR: aws CLI not found. Install from https://aws.amazon.com/cli/"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found. Install from https://docs.docker.com/"; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo "ERROR: terraform not found. Install from https://developer.hashicorp.com/terraform"; exit 1; }

# ── Verify AWS identity ───────────────────────────────────────────────────────

echo "==> Verifying AWS identity..."
aws sts get-caller-identity
echo ""

# ── Get Terraform outputs ──────────────────────────────────────────────────────

echo "==> Reading Terraform outputs from ${TERRAFORM_DIR}..."
cd "${TERRAFORM_DIR}"
ECR_URL=$(terraform output -raw ecr_repository_url 2>/dev/null) || {
    echo "ERROR: Could not read ecr_repository_url from Terraform outputs."
    echo "Run: terraform apply -var-file=dev.tfvars"
    exit 1
}
REGION=$(terraform output -raw aws_region 2>/dev/null || echo "ap-south-1")
cd - >/dev/null

echo "  ECR URL:  ${ECR_URL}"
echo "  Region:   ${REGION}"
echo "  Tag:      ${IMAGE_TAG}"
echo ""

# ── Authenticate Docker to ECR ────────────────────────────────────────────────

echo "==> Authenticating Docker to ECR..."
aws ecr get-login-password --region "${REGION}" \
    | docker login --username AWS --password-stdin "${ECR_URL%%/*}"
echo ""

# ── Build Docker image ────────────────────────────────────────────────────────

echo "==> Building Docker image..."
docker build \
    --tag "ai-tax-agent:${IMAGE_TAG}" \
    --file Dockerfile \
    .
echo ""

# ── Tag and push ──────────────────────────────────────────────────────────────

echo "==> Tagging image..."
docker tag "ai-tax-agent:${IMAGE_TAG}" "${ECR_URL}:${IMAGE_TAG}"
docker tag "ai-tax-agent:${IMAGE_TAG}" "${ECR_URL}:latest"

echo "==> Pushing to ECR..."
docker push "${ECR_URL}:${IMAGE_TAG}"
docker push "${ECR_URL}:latest"

echo ""
echo "==> Done! Image pushed:"
echo "    ${ECR_URL}:${IMAGE_TAG}"
echo "    ${ECR_URL}:latest"
echo ""
echo "==> To deploy to ECS:"
echo "    cd ${TERRAFORM_DIR}"
echo "    terraform apply -var-file=dev.tfvars -var='image_tag=${IMAGE_TAG}' -var='ecs_desired_count=1'"
