from docq import tokens


def test_count_tokens_returns_positive_for_nonempty():
    assert tokens.count_tokens("hello world") > 0


def test_count_tokens_returns_zero_for_empty():
    assert tokens.count_tokens("") == 0


def test_counter_name_is_known_value():
    name = tokens.counter_name()
    assert name in {"tiktoken/cl100k_base", "chars/4-approx"}


def test_fallback_counter_name_reports_approx(monkeypatch):
    monkeypatch.setattr(tokens, "_ENCODER", None)
    monkeypatch.setattr(tokens, "_RESOLVED", True)
    assert tokens.counter_name() == "chars/4-approx"


def test_fallback_count_tokens_uses_char_heuristic(monkeypatch):
    monkeypatch.setattr(tokens, "_ENCODER", None)
    monkeypatch.setattr(tokens, "_RESOLVED", True)
    assert tokens.count_tokens("abcdefgh") == 2  # 8 / 4.0


def test_fallback_count_tokens_floors_to_one(monkeypatch):
    monkeypatch.setattr(tokens, "_ENCODER", None)
    monkeypatch.setattr(tokens, "_RESOLVED", True)
    assert tokens.count_tokens("ab") == 1  # max(1, int(2/4.0))
