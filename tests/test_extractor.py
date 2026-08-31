import pdfplumber.utils.exceptions
import pytest

from docq import extractor_pdf


def test_extract_pages_returns_one_entry_per_page(sample_pdf):
    pages = extractor_pdf.extract_pages(sample_pdf)
    assert len(pages) == 2
    assert "東京" in pages[0]
    assert "大阪" in pages[1]


def test_extract_pages_blank_page_yields_empty_string(blank_pdf):
    pages = extractor_pdf.extract_pages(blank_pdf)
    assert len(pages) == 1
    assert pages[0] == ""


def test_extract_pages_raises_on_corrupt_file(tmp_path):
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"this is not a pdf")
    with pytest.raises(pdfplumber.utils.exceptions.PdfminerException):
        extractor_pdf.extract_pages(bad)


def test_extract_pages_raises_on_missing_file(tmp_path):
    missing = tmp_path / "no_such_file.pdf"
    with pytest.raises(FileNotFoundError):
        extractor_pdf.extract_pages(missing)
