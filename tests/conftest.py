from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

_CJK_FONT = "HeiseiMin-W3"
pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))


def _write_pdf(path: Path, pages: list[list[str]]) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    for page_index, lines in enumerate(pages):
        c.setFont(_CJK_FONT, 12)
        y = 800
        for line in lines:
            c.drawString(72, y, line)
            y -= 14
        if page_index < len(pages) - 1:
            c.showPage()
    c.save()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """A 2-page text PDF with distinct, searchable content per page."""
    pdf_path = tmp_path / "sample.pdf"
    _write_pdf(pdf_path, [
        ["東京の天気予報について", "本日は晴れ、最高気温は25度です。", "!!!注意!!!"],
        ["大阪の天気予報について", "本日は雨、最高気温は18度です。"],
    ])
    return pdf_path


@pytest.fixture
def blank_pdf(tmp_path: Path) -> Path:
    """A PDF with a page that has no text (simulates a scanned page)."""
    pdf_path = tmp_path / "blank.pdf"
    _write_pdf(pdf_path, [[]])
    return pdf_path
