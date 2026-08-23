from pdfq import indexer, search, store


def _indexed_conn(tmp_path, sample_pdf):
    conn = store.open_store(tmp_path / "index.sqlite")
    indexer.index_one_file(conn, tmp_path, sample_pdf)
    return conn


def test_search_ranks_matching_page_first(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    hits = search.search(conn, "大阪 天気", top_k=5, max_tokens=800)
    assert hits
    assert hits[0].start_page == 2


def test_search_returns_snippet_by_default(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    hits = search.search(conn, "東京", top_k=5, max_tokens=800)
    assert hits
    assert hits[0].snippet
    assert "東京" in hits[0].snippet


def test_search_return_unit_locations_has_no_snippet(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    hits = search.search(conn, "東京", top_k=5, max_tokens=800, return_unit="locations")
    assert hits
    assert hits[0].snippet is None


def test_search_no_match_returns_empty(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    hits = search.search(conn, "存在しないキーワードxyz", top_k=5, max_tokens=800)
    assert hits == []


def test_search_respects_max_tokens_budget(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    hits = search.search(conn, "天気", top_k=5, max_tokens=1)
    # budget of 1 token still admits exactly one hit (loop always keeps ≥1 hit)
    # but rejects a second once the budget is spent
    assert len(hits) == 1


def test_search_path_glob_filters_results(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    hits = search.search(conn, "天気", top_k=5, max_tokens=800, path_globs=["nomatch/*"])
    assert hits == []


def test_get_chunk_roundtrip(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    hits = search.search(conn, "東京", top_k=1, max_tokens=800)
    chunk = search.get_chunk(conn, hits[0].chunk_id)
    assert chunk is not None
    assert chunk["chunk_id"] == hits[0].chunk_id
    assert "東京" in chunk["text"]


def test_get_chunk_missing_returns_none(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    assert search.get_chunk(conn, "does-not-exist") is None
