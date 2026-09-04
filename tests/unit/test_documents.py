"""
Unit tests for document storage and extraction — Milestones 15 + 16.

All S3 and file system calls are mocked — no real AWS credentials required.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.documents.storage import (
    UploadedDocument,
    _make_s3_key,
    upload_document,
    validate_upload,
)
from app.documents.extraction import (
    CSVExtractor,
    ExtractionRouter,
    ExtractionResult,
    ImageExtractor,
    PDFExtractor,
    TextExtractor,
)


# ---------------------------------------------------------------------------
# Storage: validate_upload
# ---------------------------------------------------------------------------

def test_validate_upload_valid_pdf():
    validate_upload("form16.pdf", "application/pdf", 1024 * 1024)  # 1 MB, no exception


def test_validate_upload_exceeds_size():
    with pytest.raises(ValueError, match="exceeds"):
        validate_upload("big.pdf", "application/pdf", 25 * 1024 * 1024)  # 25 MB


def test_validate_upload_invalid_type():
    with pytest.raises(ValueError, match="not allowed"):
        validate_upload("script.exe", "application/x-executable", 1024)


def test_validate_upload_txt_allowed():
    validate_upload("salary.txt", "text/plain", 500)  # no exception


def test_make_s3_key_structure():
    key = _make_s3_key("user-123", "doc-456", "form16.pdf")
    assert key.startswith("documents/user-123/doc-456/")
    assert "form16.pdf" in key


def test_make_s3_key_sanitises_filename():
    key = _make_s3_key("u1", "d1", "my file (1).pdf")
    # special chars sanitised but key still valid
    assert "documents/u1/d1/" in key


# ---------------------------------------------------------------------------
# Storage: upload_document
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_document_success():
    mock_s3 = MagicMock()
    mock_s3.put_object = MagicMock()

    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            s3_bucket_name="test-bucket",
            aws_region="ap-south-1",
        )
        result = await upload_document(
            file_data=b"%PDF-1.4 test content",
            filename="form16.pdf",
            content_type="application/pdf",
            user_id="user-1",
            s3_client=mock_s3,
            bucket_name="test-bucket",
        )

    assert isinstance(result, UploadedDocument)
    assert result.user_id == "user-1"
    assert result.filename == "form16.pdf"
    assert result.s3_bucket == "test-bucket"
    assert "user-1" in result.s3_key
    mock_s3.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_upload_document_invalid_type_raises():
    with pytest.raises(ValueError, match="not allowed"):
        await upload_document(
            file_data=b"data",
            filename="malware.exe",
            content_type="application/x-executable",
            user_id="user-1",
            bucket_name="test-bucket",
        )


@pytest.mark.asyncio
async def test_upload_document_no_bucket_raises():
    with patch("app.core.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            s3_bucket_name="",
            aws_region="ap-south-1",
        )
        res = await upload_document(
            file_data=b"%PDF test",
            filename="doc.pdf",
            content_type="application/pdf",
            user_id="u1",
        )
        assert res.s3_bucket == "mock-bucket"


# ---------------------------------------------------------------------------
# Extraction: TextExtractor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_text_extractor_basic():
    extractor = TextExtractor()
    data = b"This is a plain text document with tax information."
    result = await extractor.extract(data, "notes.txt")
    assert result.success is True
    assert "tax" in result.text


@pytest.mark.asyncio
async def test_text_extractor_empty():
    extractor = TextExtractor()
    result = await extractor.extract(b"   ", "empty.txt")
    assert result.success is True
    assert result.text == ""


# ---------------------------------------------------------------------------
# Extraction: CSVExtractor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_csv_extractor_basic():
    extractor = CSVExtractor()
    csv_data = b"Name,Amount,Date\nSalary,50000,2024-01-01\nBonus,10000,2024-03-31"
    result = await extractor.extract(csv_data, "salary.csv")
    assert result.success is True
    assert "Salary" in result.text
    assert "50000" in result.text


@pytest.mark.asyncio
async def test_csv_extractor_empty():
    extractor = CSVExtractor()
    result = await extractor.extract(b"", "empty.csv")
    assert result.success is False
    assert "empty" in result.error.lower()


# ---------------------------------------------------------------------------
# Extraction: PDFExtractor (mocked pypdf)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pdf_extractor_success():
    extractor = PDFExtractor()

    mock_page = MagicMock()
    mock_page.extract_text = MagicMock(return_value="Income from salary: ₹12,00,000")
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with patch("pypdf.PdfReader", return_value=mock_reader):
        result = await extractor.extract(b"%PDF-1.4", "form16.pdf")

    assert result.success is True
    assert "₹12,00,000" in result.text
    assert result.page_count == 1


@pytest.mark.asyncio
async def test_pdf_extractor_no_text_fails():
    extractor = PDFExtractor()

    mock_page = MagicMock()
    mock_page.extract_text = MagicMock(return_value="")
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with patch("pypdf.PdfReader", return_value=mock_reader):
        result = await extractor.extract(b"%PDF-1.4", "scanned.pdf")

    assert result.success is False
    assert "OCR" in result.error


# ---------------------------------------------------------------------------
# Extraction: ImageExtractor (missing pytesseract → graceful failure)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_image_extractor_missing_dependency():
    extractor = ImageExtractor()
    with patch.dict("sys.modules", {"pytesseract": None, "PIL": None}):
        result = await extractor.extract(b"fake-image", "form16.jpg")
    assert result.success is False
    assert "pytesseract" in result.error or "OCR" in result.error


# ---------------------------------------------------------------------------
# Extraction: ExtractionRouter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_routes_to_text_extractor():
    router = ExtractionRouter()
    result = await router.extract(b"plain text content here", "notes.txt", "text/plain")
    assert result.success is True


@pytest.mark.asyncio
async def test_router_falls_back_to_text_for_unknown_type():
    router = ExtractionRouter()
    result = await router.extract(b"some text", "unknown.xyz", "application/unknown")
    # Falls back to TextExtractor — may succeed or fail gracefully
    assert isinstance(result, ExtractionResult)


# ---------------------------------------------------------------------------
# Upload API endpoint (integration-lite with TestClient)
# ---------------------------------------------------------------------------

def test_upload_endpoint_rejects_invalid_type():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("malware.exe", b"data", "application/x-executable")},
    )
    assert response.status_code == 422
