# Networking Module

Creates a cost-conscious VPC for the AI Tax Agent.

## ⚠️ Cost awareness

| Resource | Cost implication |
|----------|-----------------|
| VPC | Free |
| Subnets | Free |
| Internet Gateway | Free |
| Security Groups | Free |
| **NAT Gateway** | **~$35/month per AZ — NOT created by default** |
| Route Tables | Free |

**NAT Gateway is intentionally omitted** from this module.

For development:
- ECS tasks run in **public subnets** with `assign_public_ip = true`
- No NAT Gateway cost
- Security groups restrict inbound access

For production (when justified):
- Set `create_nat_gateway = true`
- ECS tasks move to private subnets
- Estimated cost: ~$35/month per AZ

## Usage

```hcl
module "networking" {
  source      = "../../modules/networking"
  project     = var.project
  environment = var.environment
  aws_region  = var.aws_region
}
```
