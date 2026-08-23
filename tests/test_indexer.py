import pytest

from docq import indexer, store


def test_windows_splits_long_text_with_overlap():
    # Position-dependent text: with a uniform string every slice comparison
    # below is trivially true and the test passes even with overlap=0.
    text = "".join(chr(0x41 + (i % 26)) for i in range(2500))
    parts = indexer._windows(text, win=1000, overlap=200)
    assert len(parts) == 3  # step=800: starts at 0, 800, 1600 (last covers to 2500)
    assert all(len(p) <= 1000 for p in parts)
    # overlap: end of part i and start of part i+1 share 200 chars
    assert parts[0][-200:] == parts[1][:200]
    assert parts[1][-200:] == parts[2][:200]
    # and the windows really start where the step says they do
    assert parts[1] == text[800:1800]


def test_windows_without_overlap_does_not_share_edges():
    text = "".join(chr(0x41 + (i % 26)) for i in range(2500))
    parts = indexer._windows(text, win=1000, overlap=0)
    assert parts[0][-200:] != parts[1][:200]


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
    # chunks must go with the file: a surviving orphan would keep showing up
    # in search results for a file that no longer exists.
    assert store.stats(conn)["chunks"] == 0


def test_index_paths_does_not_prune_files_under_other_roots(tmp_path, sample_pdf):
    """Indexing root B must leave root A's entries alone.

    They were never scanned this run, so their absence from `seen` says
    nothing about whether they still exist on disk.
    """
    docs = tmp_path / "docs"
    manuals = tmp_path / "manuals"
    docs.mkdir()
    manuals.mkdir()
    (docs / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    (manuals / "manual.pdf").write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    indexer.index_paths(conn, tmp_path, [docs])
    stats = indexer.index_paths(conn, tmp_path, [manuals])

    assert stats.pruned == 0
    assert store.stats(conn)["files"] == 2
    assert store.get_file_meta(conn, "docs/sample.pdf") is not None


def test_index_paths_accepts_root_outside_repo_root(tmp_path, sample_pdf):
    """`--root` pointing outside the working directory is the ordinary use."""
    outside = tmp_path / "outside"
    workdir = tmp_path / "workdir"
    outside.mkdir()
    workdir.mkdir()
    (outside / "sample.pdf").write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    stats = indexer.index_paths(conn, workdir, [outside])

    assert stats.errors == []
    assert stats.indexed == 1
    assert store.get_file_meta(conn, "../outside/sample.pdf") is not None


def test_index_paths_prunes_under_root_outside_repo_root(tmp_path, sample_pdf):
    """The intersection of both fixes: `..` keys must still be prunable.

    Dropping the path normalization would make containment fail for keys
    that walk up, and prune would go silently dead while every other test
    stayed green.
    """
    outside = tmp_path / "outside"
    workdir = tmp_path / "workdir"
    outside.mkdir()
    workdir.mkdir()
    pdf = outside / "sample.pdf"
    pdf.write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    indexer.index_paths(conn, workdir, [outside])
    assert store.stats(conn)["files"] == 1

    pdf.unlink()
    stats = indexer.index_paths(conn, workdir, [outside])

    assert stats.pruned == 1
    assert store.stats(conn)["files"] == 0


def test_index_paths_prunes_only_the_scanned_root_when_several_are_indexed(
        tmp_path, sample_pdf):
    """Guards against "skip prune entirely once the index spans two roots"."""
    docs = tmp_path / "docs"
    manuals = tmp_path / "manuals"
    docs.mkdir()
    manuals.mkdir()
    gone = docs / "gone.pdf"
    gone.write_bytes(sample_pdf.read_bytes())
    (docs / "kept.pdf").write_bytes(sample_pdf.read_bytes())
    (manuals / "manual.pdf").write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    indexer.index_paths(conn, tmp_path, [docs, manuals])
    assert store.stats(conn)["files"] == 3

    gone.unlink()
    stats = indexer.index_paths(conn, tmp_path, [docs])

    assert stats.pruned == 1
    assert store.get_file_meta(conn, "docs/gone.pdf") is None
    assert store.get_file_meta(conn, "docs/kept.pdf") is not None
    assert store.get_file_meta(conn, "manuals/manual.pdf") is not None


def test_index_paths_rejects_non_directory_root(tmp_path, sample_pdf):
    """A file passed as `--root` must not prune the entry it points at."""
    docs = tmp_path / "docs"
    docs.mkdir()
    pdf = docs / "a.pdf"
    pdf.write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    indexer.index_paths(conn, tmp_path, [docs])
    assert store.stats(conn)["files"] == 1

    stats = indexer.index_paths(conn, tmp_path, [pdf])

    assert stats.pruned == 0
    assert len(stats.errors) == 1
    assert "not a directory" in stats.errors[0]
    assert store.get_file_meta(conn, "docs/a.pdf") is not None


def test_index_paths_ignores_directory_named_like_a_pdf(tmp_path, sample_pdf):
    docs = tmp_path / "docs"
    (docs / "archive.pdf").mkdir(parents=True)
    (docs / "real.pdf").write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    stats = indexer.index_paths(conn, tmp_path, [docs])

    assert stats.errors == []
    assert stats.scanned == 1
    assert stats.indexed == 1


def test_index_paths_keeps_entries_whose_files_are_still_on_disk(
        tmp_path, sample_pdf, monkeypatch):
    """A scan that comes up short must not be read as "the file is gone"."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "sample.pdf").write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    indexer.index_paths(conn, tmp_path, [docs])

    # Simulate rglob coming up empty (unreadable subdirectory, races, …)
    # while the file is still there.
    monkeypatch.setattr(type(docs), "rglob", lambda self, pattern: iter(()))
    stats = indexer.index_paths(conn, tmp_path, [docs])

    assert stats.pruned == 0
    assert store.get_file_meta(conn, "docs/sample.pdf") is not None


def test_index_paths_reports_missing_root(tmp_path):
    conn = store.open_store(tmp_path / "index.sqlite")
    stats = indexer.index_paths(conn, tmp_path, [tmp_path / "typo"])

    assert stats.scanned == 0
    assert len(stats.errors) == 1
    assert "does not exist" in stats.errors[0]


def test_index_paths_refuses_a_store_bound_to_another_base_dir(tmp_path,
                                                                sample_pdf):
    """Reusing one --db from a second working directory must fail closed.

    Keys are relative to the base directory and the base is not recoverable
    from them, so reinterpreting them elsewhere double-registers files and
    reads live entries as gone.
    """
    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / "docs").mkdir(parents=True)
    (b / "docs").mkdir(parents=True)
    (a / "docs" / "sample.pdf").write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "shared.sqlite")
    indexer.index_paths(conn, a, [a / "docs"])
    assert store.stats(conn)["files"] == 1

    with pytest.raises(store.BaseDirMismatch):
        indexer.index_paths(conn, b, [b / "docs"])

    assert store.get_file_meta(conn, "docs/sample.pdf") is not None


def test_index_paths_matches_uppercase_suffix(tmp_path, sample_pdf):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "REPORT.PDF").write_bytes(sample_pdf.read_bytes())

    conn = store.open_store(tmp_path / "index.sqlite")
    stats = indexer.index_paths(conn, tmp_path, [docs])

    assert stats.indexed == 1
