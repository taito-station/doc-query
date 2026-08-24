"""PDF -> per-page plain text extraction.

Text-layer PDFs only (MVP scope). Scanned/image-only PDFs yield empty page
text and are silently skipped by the indexer — OCR is out of scope.
"""
from __future__ import annotations

from pathlib import Path

import pdfplumber


def extract_pages(pdf_path: Path) -> list[str]:
    """Return a list of page texts (1 entry per page, 1-indexed by position).

    A page with no extractable text (e.g. scanned image) yields "".
    """
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return pages
