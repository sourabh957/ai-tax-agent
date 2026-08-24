# Deployment

## Local development

```bash
docker compose up --build
```

## Production flow

```
Git → CI → Docker build → ECR → ECS/Fargate
                               Terraform manages AWS infra
```

## ECR push

```bash
aws sts get-caller-identity

aws ecr get-login-password \
  --region <REGION> \
  | docker login \
  --username AWS \
  --password-stdin <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com

docker build -t ai-tax-agent .

docker tag ai-tax-agent:latest <ECR_URI>:latest

docker push <ECR_URI>:latest
```

Use `terraform output ecr_repository_url` to get `<ECR_URI>`.

## Rollback

Deploy previous task definition revision via ECS console or AWS CLI.

## Configuration in production

Secrets are stored in AWS Secrets Manager / Parameter Store.  
The ECS task role fetches them at runtime.  
No secrets are injected as plaintext environment variables.
