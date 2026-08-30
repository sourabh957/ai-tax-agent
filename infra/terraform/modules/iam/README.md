# IAM Module

Creates ECS Execution Role and ECS Task Role with least-privilege permissions.

Task role grants: S3 (bucket only), Bedrock (specific models), CloudWatch Logs, Secrets Manager (project prefix only).
AdministratorAccess is never granted.

