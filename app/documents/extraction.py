"""
Document text extraction pipeline — Milestone 16.

Extracts text from uploaded documents (PDF, images, CSV, plain text)
for downstream chunking → embedding → Qdrant ingestion.

Pipeline:
    Raw bytes (from S3)
        │
        ▼
    ExtractorRouter  (selects extractor by MIME type)
        │
        ├─► PDFExtractor   (.pdf)
        ├─► ImageExtractor (.jpg, .png, .tiff — OCR)
        ├─► CSVExtractor   (.csv, .xls, .xlsx)
        └─► TextExtractor  (.txt)
        │
        ▼
    ExtractionResult (text + metadata)
        │
        ▼
    Chunking → Ingestion

Design principles:
    - Extractors are modular — swap or add without changing the pipeline.
    - OCR is optional and gracefully skipped if pytesseract is not installed.
    - No document content is permanently stored outside S3.
    - Extraction errors do not crash the API — they return a failed ExtractionResult.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Output of a document extraction operation."""
    success: bool
    text: str = ""
    page_count: int = 0
    doc_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def ok(cls, text: str, page_count: int = 1, doc_type: str = "", metadata: dict | None = None) -> "ExtractionResult":
        return cls(success=True, text=text, page_count=page_count, doc_type=doc_type, metadata=metadata or {})

    @classmethod
    def fail(cls, error: str) -> "ExtractionResult":
        return cls(success=False, error=error)


class BaseExtractor(ABC):
    """Abstract document extractor."""

    @abstractmethod
    async def extract(self, data: bytes, filename: str) -> ExtractionResult:
        """Extract text from raw document bytes."""

    @property
    @abstractmethod
    def supported_mime_types(self) -> set[str]:
        """MIME types this extractor handles."""


class TextExtractor(BaseExtractor):
    """Extracts text from plain text files (.txt)."""

    @property
    def supported_mime_types(self) -> set[str]:
        return {"text/plain"}

    async def extract(self, data: bytes, filename: str) -> ExtractionResult:
        try:
            text = data.decode("utf-8", errors="replace").strip()
            return ExtractionResult.ok(text=text, doc_type="text")
        except Exception as exc:
            return ExtractionResult.fail(f"Text extraction failed: {exc}")


class PDFExtractor(BaseExtractor):
    """
    Extracts text from PDF documents using pypdf.

    If pypdf is not installed, returns a graceful failure message.
    Install: pip install pypdf
    """

    @property
    def supported_mime_types(self) -> set[str]:
        return {"application/pdf"}

    async def extract(self, data: bytes, filename: str) -> ExtractionResult:
        import asyncio
        import io

        try:
            import pypdf
        except ImportError:
            return ExtractionResult.fail(
                "PDF extraction requires pypdf. Run: pip install pypdf"
            )

        def _extract_sync() -> ExtractionResult:
            try:
                reader = pypdf.PdfReader(io.BytesIO(data))
                pages = []
                for page in reader.pages:
                    page_text = page.extract_text() or ""
                    pages.append(page_text)

                full_text = "\n\n".join(p for p in pages if p.strip())
                if not full_text.strip():
                    return ExtractionResult.fail(
                        "PDF appears to be image-only (scanned). "
                        "OCR is required — use an image extractor."
                    )
                return ExtractionResult.ok(
                    text=full_text,
                    page_count=len(reader.pages),
                    doc_type="pdf",
                )
            except Exception as exc:
                return ExtractionResult.fail(f"PDF parsing error: {exc}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _extract_sync)


class ImageExtractor(BaseExtractor):
    """
    Extracts text from images using OCR (pytesseract + Pillow).

    Used for scanned Form 16, AIS, or broker statements.
    Requires: pip install pytesseract pillow
    Requires: tesseract-ocr installed on the OS.

    In production (ECS), the Dockerfile should include:
        RUN apt-get install -y tesseract-ocr
    """

    @property
    def supported_mime_types(self) -> set[str]:
        return {"image/jpeg", "image/png", "image/tiff"}

    async def extract(self, data: bytes, filename: str) -> ExtractionResult:
        import asyncio
        import io

        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return ExtractionResult.fail(
                "OCR requires pytesseract and Pillow. "
                "Run: pip install pytesseract pillow\n"
                "Also install tesseract-ocr on the OS."
            )

        def _ocr_sync() -> ExtractionResult:
            try:
                image = Image.open(io.BytesIO(data))
                text = pytesseract.image_to_string(image)
                return ExtractionResult.ok(
                    text=text.strip(),
                    page_count=1,
                    doc_type="image_ocr",
                )
            except Exception as exc:
                return ExtractionResult.fail(f"OCR error: {exc}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _ocr_sync)


class CSVExtractor(BaseExtractor):
    """
    Extracts text from CSV/Excel files.

    Converts tabular data into a structured text representation
    suitable for chunking and embedding.
    """

    @property
    def supported_mime_types(self) -> set[str]:
        return {
            "text/csv",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

    async def extract(self, data: bytes, filename: str) -> ExtractionResult:
        import asyncio
        import io

        def _extract_sync() -> ExtractionResult:
            try:
                import csv
                text_io = io.StringIO(data.decode("utf-8", errors="replace"))
                reader = csv.reader(text_io)
                rows = list(reader)
                if not rows:
                    return ExtractionResult.fail("CSV file is empty.")
                # Convert to readable text: header + rows
                lines = [", ".join(row) for row in rows if any(cell.strip() for cell in row)]
                return ExtractionResult.ok(
                    text="\n".join(lines),
                    page_count=1,
                    doc_type="csv",
                    metadata={"row_count": len(rows)},
                )
            except Exception as exc:
                return ExtractionResult.fail(f"CSV parsing error: {exc}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _extract_sync)


class ExtractionRouter:
    """
    Routes documents to the correct extractor based on MIME type.

    Usage:
        router = ExtractionRouter()
        result = await router.extract(file_bytes, filename, content_type)
    """

    def __init__(self) -> None:
        self._extractors: dict[str, BaseExtractor] = {}
        # Register built-in extractors
        for extractor in [
            TextExtractor(),
            PDFExtractor(),
            ImageExtractor(),
            CSVExtractor(),
        ]:
            for mime in extractor.supported_mime_types:
                self._extractors[mime] = extractor

    async def extract(
        self,
        data: bytes,
        filename: str,
        content_type: str,
    ) -> ExtractionResult:
        """
        Extract text from document bytes.

        Selects extractor by content_type.
        Falls back to TextExtractor for unknown types.
        """
        extractor = self._extractors.get(content_type)

        if extractor is None:
            logger.warning(
                "No extractor for content_type='%s', attempting text extraction.",
                content_type,
            )
            extractor = TextExtractor()

        logger.info(
            "Extracting document [filename=%s content_type=%s extractor=%s]",
            filename, content_type, type(extractor).__name__,
        )
        return await extractor.extract(data, filename)


# Module-level singleton
_router: ExtractionRouter | None = None


def get_extraction_router() -> ExtractionRouter:
    global _router
    if _router is None:
        _router = ExtractionRouter()
    return _router
