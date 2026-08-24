"""
S3 document storage — Milestone 15.

Handles upload and download of user-uploaded tax documents:
    Form 16, AIS, TIS, broker statements, salary slips, capital gains reports.

Design principles:
    - Documents are NEVER stored permanently in the container filesystem.
    - All S3 operations use the AWS credential chain (IAM role in production).
    - No hardcoded AWS credentials, bucket names, or regions.
    - Presigned URLs are used for secure, time-limited direct access.

S3 key structure:
    documents/{user_id}/{document_id}/{filename}

This keeps user documents isolated and makes IAM prefix-based
access control straightforward.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from typing import BinaryIO

logger = logging.getLogger(__name__)

# Allowed MIME types for uploaded documents
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "text/plain",
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@dataclass
class UploadedDocument:
    """Metadata about a successfully uploaded document."""
    document_id: str
    user_id: str
    filename: str
    s3_key: str
    s3_bucket: str
    content_type: str
    size_bytes: int


def _get_s3_client():
    """
    Build a boto3 S3 client using the standard AWS credential chain.

    Production:  IAM task role (ECS) → no keys needed
    Local dev:   AWS CLI profile or environment variables
    """
    try:
        import boto3
        from app.core.config import get_settings
        settings = get_settings()
        if not settings.aws_region:
            raise RuntimeError("AWS_REGION is required for S3 operations.")
        return boto3.client("s3", region_name=settings.aws_region)
    except ImportError:
        raise RuntimeError("boto3 is not installed. Run: pip install boto3")


def _make_s3_key(user_id: str, document_id: str, filename: str) -> str:
    """Build a structured S3 key that scopes documents by user."""
    # Sanitise filename — keep only safe characters
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    safe_name = safe_name.strip() or "document"
    return f"documents/{user_id}/{document_id}/{safe_name}"


def validate_upload(filename: str, content_type: str, size_bytes: int) -> None:
    """
    Validate an upload before sending to S3.

    Raises:
        ValueError: If the file type or size is not acceptable.
    """
    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File size {size_bytes / 1024 / 1024:.1f}MB exceeds the "
            f"{MAX_FILE_SIZE_MB}MB limit."
        )

    # Normalise content type
    guessed = mimetypes.guess_type(filename)[0] or ""
    effective_type = content_type or guessed

    if effective_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"File type '{effective_type}' is not allowed. "
            f"Allowed types: PDF, JPEG, PNG, TIFF, TXT, CSV, XLS, XLSX."
        )


async def upload_document(
    file_data: bytes,
    filename: str,
    content_type: str,
    user_id: str,
    *,
    s3_client=None,
    bucket_name: str | None = None,
) -> UploadedDocument:
    """
    Upload a document to S3 and return its metadata.

    Args:
        file_data:    Raw file bytes.
        filename:     Original filename (used for S3 key and MIME detection).
        content_type: MIME type from the HTTP upload.
        user_id:      Owner of the document.
        s3_client:    Injectable boto3 S3 client (for testing).
        bucket_name:  Override bucket name (for testing).

    Returns:
        UploadedDocument with S3 key and metadata.

    Raises:
        ValueError: If the file type or size is invalid.
        RuntimeError: If S3_BUCKET_NAME is not configured.
    """
    import asyncio
    from app.core.config import get_settings

    validate_upload(filename, content_type, len(file_data))

    settings = get_settings()
    bucket = bucket_name or settings.s3_bucket_name
    if not bucket:
        raise RuntimeError(
            "S3_BUCKET_NAME is not configured. Set it in .env."
        )

    client = s3_client or _get_s3_client()
    document_id = str(uuid.uuid4())
    s3_key = _make_s3_key(user_id, document_id, filename)

    logger.info(
        "Uploading document to S3 [user=%s doc_id=%s key=%s size=%db]",
        user_id, document_id, s3_key, len(file_data),
    )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=file_data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
            Metadata={
                "user-id": user_id,
                "document-id": document_id,
                "original-filename": filename,
            },
        ),
    )

    logger.info("Document uploaded successfully [doc_id=%s]", document_id)
    return UploadedDocument(
        document_id=document_id,
        user_id=user_id,
        filename=filename,
        s3_key=s3_key,
        s3_bucket=bucket,
        content_type=content_type,
        size_bytes=len(file_data),
    )


async def download_document(
    s3_key: str,
    *,
    s3_client=None,
    bucket_name: str | None = None,
) -> bytes:
    """Download a document from S3 and return its raw bytes."""
    import asyncio
    from app.core.config import get_settings

    settings = get_settings()
    bucket = bucket_name or settings.s3_bucket_name
    if not bucket:
        raise RuntimeError("S3_BUCKET_NAME is not configured.")

    client = s3_client or _get_s3_client()
    loop = asyncio.get_event_loop()

    response = await loop.run_in_executor(
        None,
        lambda: client.get_object(Bucket=bucket, Key=s3_key),
    )
    return response["Body"].read()


def generate_presigned_url(
    s3_key: str,
    *,
    s3_client=None,
    bucket_name: str | None = None,
    expiry_seconds: int = 3600,
) -> str:
    """
    Generate a presigned URL for temporary, direct S3 access.

    The URL expires after `expiry_seconds` (default 1 hour).
    Never expose this URL publicly — it grants read access to the document.
    """
    from app.core.config import get_settings

    settings = get_settings()
    bucket = bucket_name or settings.s3_bucket_name
    client = s3_client or _get_s3_client()

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=expiry_seconds,
    )
    return url
