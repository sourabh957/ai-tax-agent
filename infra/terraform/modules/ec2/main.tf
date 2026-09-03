locals {
  frontend_repository_url = lookup(var.ecr_repository_urls, "frontend", "")
  api_repository_url      = lookup(var.ecr_repository_urls, "api", "")
  server_name             = trimspace(var.domain_name) != "" ? var.domain_name : "_"
  # Derive ECR registry host and repo name from the api URL.
  # URL format: <account>.dkr.ecr.<region>.amazonaws.com/<repo-name>
  ecr_registry  = length(local.api_repository_url) > 0 ? split("/", local.api_repository_url)[0] : ""
  ecr_repo_name = length(local.api_repository_url) > 0 ? reverse(split("/", local.api_repository_url))[0] : ""
  default_ami_ssm_param = startswith(var.instance_type, "t4g") ? (
    "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
  ) : "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_region" "current" {}

data "aws_ssm_parameter" "default_ami" {
  count = var.ami_id == "" ? 1 : 0
  name  = local.default_ami_ssm_param
}

resource "aws_instance" "spot" {
  ami                    = var.ami_id != "" ? var.ami_id : data.aws_ssm_parameter.default_ami[0].value
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  iam_instance_profile   = var.iam_instance_profile
  key_name               = var.key_name != "" ? var.key_name : null

  instance_market_options {
    market_type = "spot"

    spot_options {
      instance_interruption_behavior = "terminate"
      spot_instance_type             = "one-time"
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  dynamic "credit_specification" {
    for_each = startswith(var.instance_type, "t") ? [1] : []
    content {
      cpu_credits = "standard"
    }
  }

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  user_data_replace_on_change = true

  user_data = <<-EOF
    #!/bin/bash
    set -euxo pipefail

    # ── 1. Install packages ────────────────────────────────────────────────────
    if command -v dnf >/dev/null 2>&1; then
      dnf update -y
      dnf install -y docker docker-compose-plugin awscli curl nginx python3 openssl
      systemctl enable --now docker
      systemctl disable --now nginx || true
    elif command -v yum >/dev/null 2>&1; then
      yum update -y
      amazon-linux-extras install docker -y || true
      yum install -y docker awscli curl nginx python3 openssl
      mkdir -p /usr/local/lib/docker/cli-plugins
      curl -SL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-$(uname -m) \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
      chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
      systemctl enable --now docker
      systemctl disable --now nginx || true
    fi

    usermod -aG docker ec2-user || true

    mkdir -p /opt/taxly/nginx

    # ── 2. Write the secrets-fetch script ─────────────────────────────────────
    # Runs at every boot to pull latest secret values from Secrets Manager.
    # The EC2 IAM instance profile grants read access — no static credentials needed.
    cat >/usr/local/bin/taxly-fetch-secrets.sh <<'FETCHSCRIPT'
    #!/bin/bash
    set -euo pipefail

    # Resolve the current region via IMDSv2
    TOKEN=$(curl -s -X PUT -H "X-aws-ec2-metadata-token-ttl-seconds: 60" \
      http://169.254.169.254/latest/api/token)
    REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
      http://169.254.169.254/latest/meta-data/placement/region)

    fetch_secret_json() {
      aws secretsmanager get-secret-value \
        --secret-id "$1" --region "$REGION" \
        --query SecretString --output text 2>/dev/null || echo "{}"
    }

    # DB credentials ─────────────────────────────────────────────────────────
    DB_SECRET_NAME="__DB_SECRET_NAME__"
    DB_JSON=$(fetch_secret_json "$DB_SECRET_NAME")
    DATABASE_URL=$(python3 -c "
    import json, sys
    d = json.loads('''$DB_JSON''')
    url = d.get('database_url') or ''
    if not url and d.get('host'):
        url = f\"postgresql+asyncpg://{d['username']}:{d['password']}@{d['host']}:5432/{d['dbname']}\"
    print(url)
    " 2>/dev/null || echo "")

    # Qdrant API key ──────────────────────────────────────────────────────────
    QDRANT_SECRET_NAME="__QDRANT_SECRET_NAME__"
    QDRANT_JSON=$(fetch_secret_json "$QDRANT_SECRET_NAME")
    QDRANT_API_KEY=$(python3 -c "
    import json, sys
    d = json.loads('''$QDRANT_JSON''')
    print(d.get('api_key', ''))
    " 2>/dev/null || echo "")

    # JWT secret — generate once, store in a local file so it survives restarts
    JWT_FILE=/opt/taxly/.jwt_secret
    if [ ! -f "$JWT_FILE" ]; then
      openssl rand -hex 32 > "$JWT_FILE"
      chmod 600 "$JWT_FILE"
    fi
    JWT_SECRET=$(cat "$JWT_FILE")

    # ECR login ───────────────────────────────────────────────────────────────
    ECR_REGISTRY="__ECR_REGISTRY__"
    aws ecr get-login-password --region "$REGION" \
      | docker login --username AWS --password-stdin "$ECR_REGISTRY"

    # Write resolved env file ─────────────────────────────────────────────────
    cat > /opt/taxly/.env <<ENV
    AWS_REGION=$REGION
    APP_ENV=production
    LOG_LEVEL=INFO
    DATABASE_URL=$DATABASE_URL
    QDRANT_API_KEY=$QDRANT_API_KEY
    QDRANT_URL=__QDRANT_URL__
    QDRANT_COLLECTION=__QDRANT_COLLECTION__
    JWT_SECRET_KEY=$JWT_SECRET
    LLM_PROVIDER=bedrock
    BEDROCK_MODEL_ID=__BEDROCK_MODEL_ID__
    S3_BUCKET_NAME=__S3_BUCKET_NAME__
    MAX_AGENT_ITERATIONS=8
    MAX_TOOL_CALLS=10
    MAX_LLM_CALLS=6
    DAILY_REQUEST_LIMIT=20
    CORS_ALLOWED_ORIGINS=http://__DOMAIN_NAME__,https://__DOMAIN_NAME__
    DOMAIN_NAME=__DOMAIN_NAME__
    NEXT_PUBLIC_API_BASE_URL=http://__DOMAIN_NAME__
    NEXT_PUBLIC_APP_NAME=Taxly
    API_IMAGE=__ECR_REGISTRY__/__REPO_NAME__:api-latest
    FRONTEND_IMAGE=__ECR_REGISTRY__/__REPO_NAME__:frontend-latest
    ENV

    echo "taxly-fetch-secrets: environment written to /opt/taxly/.env"
    FETCHSCRIPT

    # ── 3. Substitute Terraform values into the fetch script ──────────────────
    sed -i "s|__DB_SECRET_NAME__|${var.db_secret_name}|g" /usr/local/bin/taxly-fetch-secrets.sh
    sed -i "s|__QDRANT_SECRET_NAME__|${var.qdrant_secret_name}|g" /usr/local/bin/taxly-fetch-secrets.sh
    sed -i "s|__ECR_REGISTRY__|${local.ecr_registry}|g" /usr/local/bin/taxly-fetch-secrets.sh
    sed -i "s|__QDRANT_URL__|${var.qdrant_url}|g" /usr/local/bin/taxly-fetch-secrets.sh
    sed -i "s|__QDRANT_COLLECTION__|${var.qdrant_collection}|g" /usr/local/bin/taxly-fetch-secrets.sh
    sed -i "s|__BEDROCK_MODEL_ID__|${var.bedrock_model_id}|g" /usr/local/bin/taxly-fetch-secrets.sh
    sed -i "s|__S3_BUCKET_NAME__|${var.s3_bucket_name}|g" /usr/local/bin/taxly-fetch-secrets.sh
    sed -i "s|__REPO_NAME__|${local.ecr_repo_name}|g" /usr/local/bin/taxly-fetch-secrets.sh

    DOMAIN_ESCAPED="${local.server_name}"
    sed -i "s|__DOMAIN_NAME__|$DOMAIN_ESCAPED|g" /usr/local/bin/taxly-fetch-secrets.sh

    chmod +x /usr/local/bin/taxly-fetch-secrets.sh

    # ── 4. Docker Compose file ─────────────────────────────────────────────────
    cat >/opt/taxly/docker-compose.yml <<'COMPOSE'
    services:
      api:
        image: $${API_IMAGE}
        restart: unless-stopped
        env_file: /opt/taxly/.env
        environment:
          APP_ENV: production
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
          interval: 30s
          timeout: 10s
          retries: 3
          start_period: 30s
        logging:
          driver: awslogs
          options:
            awslogs-region: $${AWS_REGION}
            awslogs-group: ${var.cloudwatch_log_group}
            awslogs-stream: api

      frontend:
        image: $${FRONTEND_IMAGE}
        restart: unless-stopped
        environment:
          NODE_ENV: production
          NEXT_TELEMETRY_DISABLED: "1"
          NEXT_PUBLIC_API_BASE_URL: $${NEXT_PUBLIC_API_BASE_URL}
          NEXT_PUBLIC_APP_NAME: $${NEXT_PUBLIC_APP_NAME}
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:3000"]
          interval: 30s
          timeout: 10s
          retries: 3
          start_period: 20s
        logging:
          driver: awslogs
          options:
            awslogs-region: $${AWS_REGION}
            awslogs-group: ${var.cloudwatch_log_group}
            awslogs-stream: frontend

      nginx:
        image: nginx:1.27-alpine
        restart: unless-stopped
        depends_on:
          - api
          - frontend
        ports:
          - "80:80"
          - "443:443"
        volumes:
          - /opt/taxly/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
        logging:
          driver: awslogs
          options:
            awslogs-region: $${AWS_REGION}
            awslogs-group: ${var.cloudwatch_log_group}
            awslogs-stream: nginx
    COMPOSE

    # ── 5. Nginx config ────────────────────────────────────────────────────────
    cat >/opt/taxly/nginx/default.conf <<'NGINX'
    server {
      listen 80;
      server_name ${local.server_name};

      location /api/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
      }

      location / {
        proxy_pass http://frontend:3000/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
      }
    }
    NGINX

    # ── 6. Systemd service ─────────────────────────────────────────────────────
    cat >/etc/systemd/system/taxly-compose.service <<'SERVICE'
    [Unit]
    Description=Taxly application stack via Docker Compose
    Requires=docker.service
    After=docker.service network-online.target
    Wants=network-online.target

    [Service]
    Type=oneshot
    WorkingDirectory=/opt/taxly
    ExecStartPre=/usr/local/bin/taxly-fetch-secrets.sh
    ExecStartPre=/usr/bin/docker compose -f /opt/taxly/docker-compose.yml pull
    ExecStart=/usr/bin/docker compose -f /opt/taxly/docker-compose.yml up -d
    ExecStop=/usr/bin/docker compose -f /opt/taxly/docker-compose.yml down
    RemainAfterExit=yes
    TimeoutStartSec=0

    [Install]
    WantedBy=multi-user.target
    SERVICE

    # ── 7. TLS instructions ────────────────────────────────────────────────────
    cat >/opt/taxly/README-certbot.txt <<'CERTBOT'
    Manual TLS steps (after DNS points to this instance's public IP):
      1. sudo dnf install -y certbot || sudo apt-get install -y certbot
      2. sudo systemctl stop taxly-compose
      3. sudo certbot certonly --standalone -d ${local.server_name}
      4. Mount /etc/letsencrypt into the nginx container and add the TLS server block.
      5. sudo systemctl start taxly-compose
    CERTBOT

    systemctl daemon-reload
    systemctl enable taxly-compose.service
    systemctl start taxly-compose.service
  EOF

  tags = {
    Name = "taxly-spot-instance"
  }
}
