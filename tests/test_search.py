from docq import indexer, search, store


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


def test_empty_query_returns_no_hits(tmp_path, sample_pdf):
    """The empty string is the case that matters.

    `re.escape("")` matches at every offset, so without the guard the grep
    fallback returns every chunk ranked by length. A whitespace-only query
    happens to return nothing either way on this fixture, so it cannot stand
    in for this.
    """
    conn = _indexed_conn(tmp_path, sample_pdf)
    assert search.search(conn, "", top_k=5, max_tokens=800) == []
    assert search.search(conn, "", top_k=5, max_tokens=800, mode="grep") == []
    assert search.search(conn, "   ", top_k=5, max_tokens=800) == []


def test_idf_stays_positive_for_a_term_in_every_document():
    """The reason this project ships its own BM25 instead of rank_bm25.

    Textbook Okapi IDF goes negative once a term appears in more than half
    the corpus and hits exactly 0 at half — with a handful of indexed files
    that is an ordinary situation, and real matches silently score away to
    nothing. Guarding the smoothing directly, because a search-level test
    would still pass while ranking quietly degraded.
    """
    corpus = [["東京", "天気"], ["東京", "大阪"], ["東京", "京都"], ["東京", "奈良"]]
    bm25 = search._MiniBM25(corpus, b=search.LENGTH_NORM_B)

    assert bm25.idf["東京"] > 0  # present in all 4 of 4
    assert min(bm25.get_scores(["東京"])) > 0


def test_search_finds_a_term_present_in_every_chunk(tmp_path, sample_pdf):
    conn = _indexed_conn(tmp_path, sample_pdf)
    rows = store.all_chunks(conn)
    everywhere = "天気"
    assert all(everywhere in r["text"] for r in rows), "fixture precondition"

    hits = search.search(conn, everywhere, top_k=5, max_tokens=800)

    assert hits, "a term in every chunk must still be findable"
