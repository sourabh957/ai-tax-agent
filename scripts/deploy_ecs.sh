#!/usr/bin/env bash
# =============================================================================
# deploy_ecs.sh — Deploy new image to ECS Fargate service
#
# Usage:
#   ./scripts/deploy_ecs.sh [IMAGE_TAG] [ENVIRONMENT]
#
# What this does:
#   1. Pushes the Docker image to ECR (calls deploy_ecr.sh)
#   2. Updates the ECS task definition with the new image tag via Terraform
#   3. Forces a new ECS deployment
#   4. Waits for the service to stabilise
#   5. On failure: rolls back to the previous task definition revision
#
# Prerequisites:
#   - AWS CLI configured
#   - Terraform applied (ECR + ECS infrastructure exists)
#   - dev.tfvars present in infra/terraform/environments/<env>/
# =============================================================================
set -euo pipefail

IMAGE_TAG="${1:-latest}"
ENV="${2:-dev}"
TERRAFORM_DIR="infra/terraform/environments/${ENV}"
SCRIPTS_DIR="$(dirname "$0")"

# ── Prerequisites ─────────────────────────────────────────────────────────────
command -v aws       >/dev/null 2>&1 || { echo "ERROR: aws CLI not found."; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo "ERROR: terraform not found."; exit 1; }

# ── Verify AWS identity ───────────────────────────────────────────────────────
echo "==> Verifying AWS identity..."
aws sts get-caller-identity
echo ""

# ── Step 1: Build and push to ECR ────────────────────────────────────────────
echo "==> Step 1: Push image to ECR [tag=${IMAGE_TAG}]..."
bash "${SCRIPTS_DIR}/deploy_ecr.sh" "${IMAGE_TAG}"
echo ""

# ── Step 2: Read Terraform outputs ───────────────────────────────────────────
echo "==> Step 2: Reading Terraform outputs..."
CLUSTER=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ecs_cluster_name 2>/dev/null) || {
    echo "ERROR: Could not read ecs_cluster_name. Run terraform apply first."
    exit 1
}
SERVICE=$(terraform -chdir="${TERRAFORM_DIR}" output -raw ecs_service_name 2>/dev/null)
REGION=$(terraform -chdir="${TERRAFORM_DIR}" output -raw aws_region 2>/dev/null || echo "ap-south-1")

echo "  Cluster: ${CLUSTER}"
echo "  Service: ${SERVICE}"
echo "  Region:  ${REGION}"
echo ""

# ── Step 3: Save current task definition for rollback ────────────────────────
echo "==> Step 3: Saving current task definition ARN for rollback..."
CURRENT_TASK_DEF=$(aws ecs describe-services \
    --cluster "${CLUSTER}" \
    --services "${SERVICE}" \
    --region "${REGION}" \
    --query "services[0].taskDefinition" \
    --output text)
echo "  Current task definition: ${CURRENT_TASK_DEF}"
echo ""

# ── Step 4: Update ECS task definition via Terraform ─────────────────────────
echo "==> Step 4: Updating task definition to image tag '${IMAGE_TAG}'..."
terraform -chdir="${TERRAFORM_DIR}" apply \
    -var-file="${ENV}.tfvars" \
    -var="image_tag=${IMAGE_TAG}" \
    -var="ecs_desired_count=1" \
    -auto-approve \
    -input=false
echo ""

# ── Step 5: Force new deployment ─────────────────────────────────────────────
echo "==> Step 5: Forcing new ECS deployment..."
aws ecs update-service \
    --cluster "${CLUSTER}" \
    --service "${SERVICE}" \
    --force-new-deployment \
    --region "${REGION}" \
    --output text --query "service.serviceName"
echo ""

# ── Step 6: Wait for service stability ───────────────────────────────────────
echo "==> Step 6: Waiting for ECS service to stabilise (timeout: 5 min)..."
if aws ecs wait services-stable \
    --cluster "${CLUSTER}" \
    --services "${SERVICE}" \
    --region "${REGION}"; then
    echo "  [OK] Service is stable."
else
    echo ""
    echo "ERROR: Service did not stabilise. Initiating rollback..."
    aws ecs update-service \
        --cluster "${CLUSTER}" \
        --service "${SERVICE}" \
        --task-definition "${CURRENT_TASK_DEF}" \
        --force-new-deployment \
        --region "${REGION}" \
        --output text --query "service.serviceName"
    echo "Rollback initiated to: ${CURRENT_TASK_DEF}"
    echo "Check ECS console and CloudWatch logs for deployment failure details."
    exit 1
fi

echo ""
echo "==> Deployment complete!"
echo "    Image: ${IMAGE_TAG}"
echo "    Cluster: ${CLUSTER}"
echo "    Service: ${SERVICE}"
