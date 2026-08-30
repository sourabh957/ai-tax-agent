# ECR Module

Creates ECR repository for the AI Tax Agent Docker image.
Image scanning on push enabled. Lifecycle policy limits stored images.

## Push commands
```bash
ECR_URL=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin $ECR_URL
docker build -t ai-tax-agent .
docker tag ai-tax-agent:latest $ECR_URL:latest
docker push $ECR_URL:latest
```
