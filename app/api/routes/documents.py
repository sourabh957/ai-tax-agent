"""
Document upload API routes.

POST /api/v1/documents/upload
    - Accepts multipart file upload
    - Validates file type and size
    - Uploads to S3
    - Triggers text extraction
    - Returns document metadata

GET /api/v1/documents/{document_id}
    - Returns document metadata + presigned download URL
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.documents.extraction import get_extraction_router
from app.documents.storage import (
    MAX_FILE_SIZE_MB,
    UploadedDocument,
    generate_presigned_url,
    upload_document,
    validate_upload,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    s3_key: str
    content_type: str
    size_bytes: int
    extraction_status: str
    extracted_chars: int
    message: str


@router.post(
    "/documents/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a tax document",
    description=(
        "Upload a tax document (Form 16, AIS, broker statement, etc.). "
        "The document is stored in S3 and text is extracted for RAG ingestion. "
        f"Maximum file size: {MAX_FILE_SIZE_MB}MB. "
        "Supported formats: PDF, JPEG, PNG, TIFF, TXT, CSV."
    ),
)
async def upload_tax_document(
    file: UploadFile,
    financial_year: str = "2024-25",
    # user_id: str = Depends(get_current_user)  # TODO: add auth in Milestone auth
) -> UploadResponse:
    """Upload a document, store in S3, and extract text."""

    # Placeholder user_id until auth is wired (Milestone security)
    user_id = "anonymous"

    content_type = file.content_type or "application/octet-stream"
    data = await file.read()

    # Validate before touching S3
    try:
        validate_upload(file.filename or "upload", content_type, len(data))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Upload to S3
    try:
        doc = await upload_document(
            file_data=data,
            filename=file.filename or "upload",
            content_type=content_type,
            user_id=user_id,
        )
    except RuntimeError as exc:
        logger.error("S3 upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Document storage unavailable: {exc}",
        )
    except Exception as exc:
        logger.exception("Unexpected upload error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload failed due to an internal error.",
        )

    # Extract text
    router_instance = get_extraction_router()
    extraction = await router_instance.extract(data, doc.filename, content_type)

    extraction_status = "success" if extraction.success else "failed"
    if not extraction.success:
        logger.warning(
            "Extraction failed for doc %s: %s", doc.document_id, extraction.error
        )

    return UploadResponse(
        document_id=doc.document_id,
        filename=doc.filename,
        s3_key=doc.s3_key,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        extraction_status=extraction_status,
        extracted_chars=len(extraction.text),
        message=(
            "Document uploaded and text extracted successfully."
            if extraction.success
            else f"Document uploaded but text extraction failed: {extraction.error}"
        ),
    )
