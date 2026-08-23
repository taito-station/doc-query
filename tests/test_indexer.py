from pathlib import Path

from pdfq import indexer, store


def test_windows_splits_long_text_with_overlap():
    text = "a" * 2500
    parts = indexer._windows(text, win=1000, overlap=200)
    assert len(parts) == 3  # step=800: starts at 0, 800, 1600 (last covers to 2500)
    assert all(len(p) <= 1000 for p in parts)
    # overlap: end of part i and start of part i+1 share 200 chars
    assert parts[0][-200:] == parts[1][:200]


def test_windows_short_text_single_window():
    assert indexer._windows("short text") == ["short text"]


def test_index_one_file_creates_chunks_per_page(tmp_path, sample_pdf):
    conn = store.open_store(tmp_path / "index.sqlite")
    n = indexer.index_one_file(conn, tmp_path, sample_pdf)
    assert n > 0
    rows = store.all_chunks(conn)
    pages = {r["start_page"] for r in rows}
    assert pages == {1, 2}


def test_index_one_file_skips_unchanged_file(tmp_path, sample_pdf):
    conn = store.open_store(tmp_path / "index.sqlite")
    first = indexer.index_one_file(conn, tmp_path, sample_pdf)
    second = indexer.index_one_file(conn, tmp_path, sample_pdf)
    assert first > 0
    assert second == 0


def test_index_one_file_skips_blank_pages(tmp_path, blank_pdf):
    conn = store.open_store(tmp_path / "index.sqlite")
    n = indexer.index_one_file(conn, tmp_path, blank_pdf)
    assert n == 0
    # file is still registered so re-indexing without changes is a no-op scan
    assert store.get_file_meta(conn, "blank.pdf") is not None


def test_index_paths_prunes_removed_files(tmp_path, sample_pdf):
    docs = tmp_path / "docs"
    docs.mkdir()
    pdf_in_docs = docs / "sample.pdf"
    pdf_in_docs.write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    stats = indexer.index_paths(conn, tmp_path, [docs])
    assert stats.indexed == 1
    assert stats.chunks > 0

    pdf_in_docs.unlink()
    stats2 = indexer.index_paths(conn, tmp_path, [docs])
    assert stats2.pruned == 1
    assert store.stats(conn)["files"] == 0
