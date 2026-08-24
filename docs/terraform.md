# Terraform Guide

## Directory layout

```
infra/terraform/
├── modules/
│   ├── networking/
│   ├── iam/
│   ├── ecr/
│   ├── ecs/
│   ├── rds/
│   ├── s3/
│   └── cloudwatch/
└── environments/
    ├── dev/
    └── prod/
```

## Workflow (mandatory for every change)

```bash
cd infra/terraform/environments/dev

terraform init
terraform fmt -recursive
terraform validate
terraform plan -var-file="dev.tfvars"
```

**Review the plan.** Confirm expected resources and cost implications before proceeding.

```bash
terraform apply -var-file="dev.tfvars"
terraform output
```

## Cleanup

```bash
terraform destroy -var-file="dev.tfvars"
```

> ⚠️ Never run `terraform apply` or `terraform destroy` automatically.

## Cost-conscious rules

- NAT Gateway and Application Load Balancer are expensive — only create when justified.
- Use smallest practical RDS instance.
- ECS Fargate costs scale with task CPU/memory.
- Review the plan for `+ resource` entries before applying.

## Secrets

- Never commit `terraform.tfvars` containing real values.
- Use `*.tfvars.example` files with empty values.
- Prefer AWS Secrets Manager for runtime secrets.

## Remote state (future)

```hcl
terraform {
  backend "s3" {
    bucket         = "<STATE_BUCKET>"
    key            = "dev/terraform.tfstate"
    region         = "<REGION>"
    dynamodb_table = "<LOCK_TABLE>"
  }
}
```

Bootstrap the state bucket manually before using the S3 backend.

## Infrastructure progression

| Milestone | Resources |
|-----------|-----------|
| 28 | Networking (VPC, subnets, security groups) |
| 29 | S3 + IAM |
| 30 | ECR |
| 31 | RDS PostgreSQL |
| 32 | ECS/Fargate |
| 33 | CloudWatch |
| 34 | Secrets Manager |
