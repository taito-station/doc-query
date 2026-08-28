from docq.tokenize import scoring_terms, snippet_tokens


def test_cjk_sequence_yields_bigrams():
    assert scoring_terms("東京都") == ["東京", "京都"]


def test_single_cjk_yields_itself():
    assert scoring_terms("A東B") == ["a", "東", "b"]


def test_ascii_run_kept_whole_and_lowered():
    assert scoring_terms("BM25score") == ["bm25score"]


def test_mixed_cjk_ascii():
    assert scoring_terms("PDF検索engine") == ["pdf", "検索", "engine"]


def test_nfkc_fullwidth_alpha():
    assert scoring_terms("指定席Ａ") == ["指定", "定席", "a"]


def test_nfkc_fullwidth_digits():
    assert scoring_terms("０５０－３０６６－９６９０") == ["050", "3066", "9690"]


def test_nfkc_roman_numeral():
    assert scoring_terms("カテゴリⅠ") == ["カテ", "テゴ", "ゴリ", "i"]


def test_nfkc_different_fullwidth_produce_different_terms():
    terms_a = scoring_terms("指定席Ａ")
    terms_s = scoring_terms("指定席Ｓ")
    assert terms_a != terms_s
    assert "a" in terms_a
    assert "s" in terms_s


def test_snippet_tokens_shares_normalization():
    tokens = snippet_tokens("指定席Ａ")
    assert tokens == ["指", "定", "席", "a"]
