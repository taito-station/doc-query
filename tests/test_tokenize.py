from docq.tokenize import scoring_terms


def test_cjk_sequence_yields_bigrams():
    assert scoring_terms("東京都") == ["東京", "京都"]


def test_single_cjk_yields_itself():
    assert scoring_terms("A東B") == ["a", "東", "b"]


def test_ascii_run_kept_whole_and_lowered():
    assert scoring_terms("BM25score") == ["bm25score"]


def test_mixed_cjk_ascii():
    assert scoring_terms("PDF検索engine") == ["pdf", "検索", "engine"]
