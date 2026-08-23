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
