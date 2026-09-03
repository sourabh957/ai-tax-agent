locals {
  frontend_repository_url = lookup(var.ecr_repository_urls, "frontend", "")
  api_repository_url      = lookup(var.ecr_repository_urls, "api", "")
  server_name             = trimspace(var.domain_name) != "" ? var.domain_name : "_"
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

    if command -v dnf >/dev/null 2>&1; then
      dnf update -y
      dnf install -y docker docker-compose-plugin awscli curl nginx
      systemctl enable --now docker
      systemctl disable --now nginx || true
    elif command -v yum >/dev/null 2>&1; then
      yum update -y
      amazon-linux-extras install docker -y || true
      yum install -y docker awscli curl nginx
      mkdir -p /usr/local/lib/docker/cli-plugins
      curl -SL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-$(uname -m) -o /usr/local/lib/docker/cli-plugins/docker-compose
      chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
      systemctl enable --now docker
      systemctl disable --now nginx || true
    elif command -v apt-get >/dev/null 2>&1; then
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -y
      apt-get install -y ca-certificates curl gnupg lsb-release awscli nginx
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      chmod a+r /etc/apt/keyrings/docker.gpg
      echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
      apt-get update -y
      apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      systemctl enable --now docker
      systemctl disable --now nginx || true
    else
      echo "Unsupported Linux distribution for bootstrap" >&2
      exit 1
    fi

    usermod -aG docker ec2-user || true
    usermod -aG docker ubuntu || true

    mkdir -p /opt/taxly/nginx

    cat >/opt/taxly/.env <<'ENVFILE'
    AWS_REGION=${data.aws_region.current.name}
    DOMAIN_NAME=${local.server_name}
    FRONTEND_ECR_REPOSITORY=${local.frontend_repository_url}
    API_ECR_REPOSITORY=${local.api_repository_url}
    FRONTEND_IMAGE=${local.frontend_repository_url}:frontend-latest
    API_IMAGE=${local.api_repository_url}:api-latest
    APP_SECRET_ID=replace-with-your-app-secret-id
    DB_SECRET_ID=replace-with-your-db-secret-id
    ENVFILE

    cat >/opt/taxly/docker-compose.yml <<'COMPOSE'
    services:
      frontend:
        image: $${FRONTEND_IMAGE}
        restart: unless-stopped
        environment:
          AWS_REGION: $${AWS_REGION}
          APP_SECRET_ID: $${APP_SECRET_ID}
        logging:
          driver: awslogs
          options:
            awslogs-region: $${AWS_REGION}
            awslogs-group: ${var.cloudwatch_log_group}
            awslogs-stream: frontend

      api:
        image: $${API_IMAGE}
        restart: unless-stopped
        environment:
          AWS_REGION: $${AWS_REGION}
          APP_SECRET_ID: $${APP_SECRET_ID}
          DB_SECRET_ID: $${DB_SECRET_ID}
        logging:
          driver: awslogs
          options:
            awslogs-region: $${AWS_REGION}
            awslogs-group: ${var.cloudwatch_log_group}
            awslogs-stream: api

      nginx:
        image: nginx:1.27-alpine
        restart: unless-stopped
        depends_on:
          - frontend
          - api
        ports:
          - "80:80"
          - "443:443"
        volumes:
          - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
        logging:
          driver: awslogs
          options:
            awslogs-region: $${AWS_REGION}
            awslogs-group: ${var.cloudwatch_log_group}
            awslogs-stream: nginx
    COMPOSE

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

    cat >/usr/local/bin/taxly-ecr-login.sh <<'SCRIPT'
    #!/bin/bash
    set -euo pipefail

    REGION=$(awk -F\" '/region/ { print $4 }' <(curl -s http://169.254.169.254/latest/dynamic/instance-identity/document))

    repos=(
      "${local.frontend_repository_url}"
      "${local.api_repository_url}"
    )

    for repo in "$${repos[@]}"; do
      if [ -n "$repo" ]; then
        registry="$${repo%%/*}"
        aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$registry"
      fi
    done
    SCRIPT
    chmod +x /usr/local/bin/taxly-ecr-login.sh

    cat >/etc/systemd/system/taxly-compose.service <<'SERVICE'
    [Unit]
    Description=Taxly application stack via Docker Compose
    Requires=docker.service
    After=docker.service network-online.target
    Wants=network-online.target

    [Service]
    Type=oneshot
    WorkingDirectory=/opt/taxly
    EnvironmentFile=/opt/taxly/.env
    ExecStartPre=/usr/local/bin/taxly-ecr-login.sh
    ExecStartPre=/usr/bin/docker compose -f /opt/taxly/docker-compose.yml pull
    ExecStart=/usr/bin/docker compose -f /opt/taxly/docker-compose.yml up -d
    ExecStop=/usr/bin/docker compose -f /opt/taxly/docker-compose.yml down
    RemainAfterExit=yes
    TimeoutStartSec=0

    [Install]
    WantedBy=multi-user.target
    SERVICE

    cat >/opt/taxly/README-certbot.txt <<'CERTBOT'
    Manual TLS steps after DNS points to the instance:
      1. sudo dnf install -y certbot || sudo apt-get install -y certbot
      2. sudo systemctl stop taxly-compose
      3. sudo docker compose -f /opt/taxly/docker-compose.yml up -d frontend api
      4. sudo certbot certonly --standalone -d ${local.server_name}
      5. Mount /etc/letsencrypt into the nginx container and add the TLS server block.
      6. Start the full stack again: sudo systemctl start taxly-compose

    These steps are intentionally manual so certificate material is never baked
    into Terraform or user_data.
    CERTBOT

    systemctl daemon-reload
    systemctl enable taxly-compose.service
  EOF

  tags = {
    Name = "taxly-spot-instance"
  }
}
