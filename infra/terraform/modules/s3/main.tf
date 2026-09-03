resource "random_id" "bucket_suffix" {
  byte_length = 4
}

locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : (
    "${var.project}-${var.environment}-documents-${random_id.bucket_suffix.hex}"
  )
}

# ── S3 Bucket ─────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "documents" {
  bucket = local.bucket_name

  tags = {
    Name        = local.bucket_name
    Project     = var.project
    Environment = var.environment
    Purpose     = "Tax document storage"
  }
}

# Block ALL public access — tax documents must never be publicly accessible
resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Server-side encryption at rest
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Versioning (optional — controlled by variable)
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Suspended"
  }
}

# Lifecycle policy — clean up old non-current versions to control costs
resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  count  = var.lifecycle_expire_days > 0 ? 1 : 0
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.lifecycle_expire_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
