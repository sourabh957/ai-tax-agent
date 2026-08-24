"""
Text chunking utilities.

Splits documents into overlapping chunks suitable for embedding.

Strategy: fixed-size character chunks with overlap.
Future: sentence-aware, semantic, or recursive chunking can be added here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkConfig:
    chunk_size: int = 512       # characters per chunk
    chunk_overlap: int = 64     # character overlap between adjacent chunks
    min_chunk_size: int = 50    # discard chunks shorter than this


DEFAULT_CHUNK_CONFIG = ChunkConfig()


def chunk_text(
    text: str,
    source: str,
    doc_type: str,
    financial_year: str = "2024-25",
    section: str = "",
    config: ChunkConfig | None = None,
) -> list[dict]:
    """
    Split text into overlapping chunks.

    Returns a list of dicts suitable for constructing DocumentChunk objects.
    The caller decides on user_id and metadata.
    """
    cfg = config or DEFAULT_CHUNK_CONFIG
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = start + cfg.chunk_size
        chunk_text = text[start:end].strip()

        if len(chunk_text) >= cfg.min_chunk_size:
            chunks.append({
                "text": chunk_text,
                "source": source,
                "doc_type": doc_type,
                "financial_year": financial_year,
                "section": section,
                "chunk_index": idx,
            })
            idx += 1

        if end >= len(text):
            break
        start = end - cfg.chunk_overlap

    return chunks
