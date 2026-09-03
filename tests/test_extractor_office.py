import pytest

from docq import extractor_office


def test_extract_pages_pptx_returns_one_entry_per_slide(sample_pptx):
    pages = extractor_office.extract_pages(sample_pptx)
    assert len(pages) == 2
    assert "東京" in pages[0]
    assert "大阪" in pages[1]


def test_extract_pages_xlsx_returns_one_entry_per_sheet(sample_xlsx):
    pages = extractor_office.extract_pages(sample_xlsx)
    assert len(pages) == 2
    assert "東京" in pages[0]
    assert "大阪" in pages[1]


def test_extract_pages_pptx_blank_slide_yields_empty_string(blank_pptx):
    pages = extractor_office.extract_pages(blank_pptx)
    assert len(pages) == 1
    assert pages[0] == ""


def test_extract_pages_xlsx_blank_sheet_yields_empty_string(blank_xlsx):
    pages = extractor_office.extract_pages(blank_xlsx)
    assert len(pages) == 1
    assert pages[0] == ""


def test_extract_pages_pptx_raises_on_corrupt_file(tmp_path):
    bad = tmp_path / "corrupt.pptx"
    bad.write_bytes(b"this is not a pptx")
    with pytest.raises(Exception):
        extractor_office.extract_pages(bad)


def test_extract_pages_xlsx_raises_on_corrupt_file(tmp_path):
    bad = tmp_path / "corrupt.xlsx"
    bad.write_bytes(b"this is not an xlsx")
    with pytest.raises(Exception):
        extractor_office.extract_pages(bad)


def test_extract_pages_raises_on_unsupported_format(tmp_path):
    txt = tmp_path / "file.txt"
    txt.write_text("hello")
    with pytest.raises(ValueError, match="Unsupported format"):
        extractor_office.extract_pages(txt)


def test_extract_pages_pptx_raises_on_missing_file(tmp_path):
    missing = tmp_path / "no_such.pptx"
    with pytest.raises(Exception):
        extractor_office.extract_pages(missing)


def test_extract_pages_xlsx_raises_on_missing_file(tmp_path):
    missing = tmp_path / "no_such.xlsx"
    with pytest.raises(Exception):
        extractor_office.extract_pages(missing)
