# Domain and HTTPS Setup

> This guide covers DNS configuration, Nginx setup, and Let's Encrypt SSL.

---

## Step 1: Purchase a domain

Purchase your domain from any registrar (GoDaddy, Namecheap, Cloudflare Registrar, etc.).
Taxly does not require a specific registrar.

---

## Step 2: Get your EC2 public IP

```bash
terraform -chdir=infra/terraform/environments/dev output ec2_public_ip
```

> **Note on Elastic IP:** The default EC2 Spot instance uses a dynamic public IP.
> If you need a stable IP (for DNS), allocate an Elastic IP:
>
> ```bash
> aws ec2 allocate-address --domain vpc
> aws ec2 associate-address --instance-id <INSTANCE_ID> --public-ip <EIP>
> ```
>
> **Cost:** Public IPv4 costs ~$0.005/hour (~₹300/month) whether attached or not.

---

## Step 3: Create DNS A record

At your domain registrar/DNS provider:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `@` or `yourdomain.com` | `<EC2_PUBLIC_IP>` | 300 |
| A | `www` | `<EC2_PUBLIC_IP>` | 300 |

Wait for DNS propagation (usually 5–30 minutes).

Verify:
```bash
nslookup yourdomain.com
dig yourdomain.com A
```

---

## Step 4: Configure Nginx

SSH into your EC2 instance, then:

```bash
# Install Nginx
sudo apt-get install -y nginx    # Ubuntu
# or
sudo yum install -y nginx        # Amazon Linux

# Copy Nginx config
sudo cp /opt/taxly/nginx.conf /etc/nginx/sites-available/taxly

# Replace DOMAIN_NAME placeholder
sudo sed -i 's/DOMAIN_NAME/yourdomain.com/g' /etc/nginx/sites-available/taxly

# Enable the site
sudo ln -sf /etc/nginx/sites-available/taxly /etc/nginx/sites-enabled/taxly
sudo rm -f /etc/nginx/sites-enabled/default

# Test config
sudo nginx -t

# Start Nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

---

## Step 5: Get Let's Encrypt certificate

```bash
# Install Certbot
sudo snap install certbot --classic

# Get certificate (Nginx plugin handles config automatically)
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com \
    --email your@email.com \
    --agree-tos \
    --no-eff-email

# Test renewal
sudo certbot renew --dry-run
```

Certbot automatically:
- Gets a free TLS certificate
- Updates Nginx to redirect HTTP → HTTPS
- Sets up a cron job for auto-renewal (every 60 days)

---

## Step 6: Verify HTTPS

```bash
# Should return 301 redirect
curl -I http://yourdomain.com

# Should return 200 OK
curl -I https://yourdomain.com

# API health check
curl https://yourdomain.com/api/v1/health
```

---

## Certificate renewal

Certbot renews automatically via a systemd timer. Check status:

```bash
sudo systemctl status certbot.timer
sudo certbot renew --dry-run   # test renewal
```

---

## OIDC redirect URI

After your domain is live, configure the OIDC callback URI in your identity provider:

```
https://yourdomain.com/api/auth/callback
```

Update your `.env` on EC2:
```
OIDC_ISSUER_URL=https://your-provider.com
OIDC_CLIENT_ID=your-client-id
OIDC_AUDIENCE=your-audience
```

And in Secrets Manager:
```bash
aws secretsmanager put-secret-value \
    --secret-id taxly-dev/oidc-credentials \
    --secret-string '{"client_secret":"your-secret"}'
```
