"""Scoring tokenizer, vendored from mdq's ``scoring_terms`` (CJK bigram).

A run of CJK characters yields adjacent bigrams (mirrors Lucene's
CJKBigramFilter); ASCII runs are kept whole. This is the term unit BM25
ranking matches on; excerpt selection uses a separate, coarser tokenizer
(see :func:`snippet_tokens`) so the returned snippet is unaffected by it.

Both tokenizers share :func:`normalize` and :data:`CJK_CHAR_RANGES` so
that changing one without the other requires editing this module (D19-010).
"""
from __future__ import annotations

import re
import unicodedata

CJK_CHAR_RANGES: tuple[tuple[str, str], ...] = (
    ("぀", "ヿ"),  # hiragana + katakana (incl. the ー prolonged mark)
    ("一", "鿿"),  # CJK unified ideographs
)

_CJK_CLASS = "".join(f"{low}-{high}" for low, high in CJK_CHAR_RANGES)
_ASCII_RUN = r"[A-Za-z0-9_]+"
_SEGMENT_RE = re.compile(rf"{_ASCII_RUN}|[{_CJK_CLASS}]+")
_ASCII_RE = re.compile(_ASCII_RUN)
_SNIPPET_RE = re.compile(rf"{_ASCII_RUN}|[{_CJK_CLASS}]")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def scoring_terms(text: str) -> list[str]:
    """Return the terms BM25 ranking matches on.

    A run of CJK characters yields its adjacent bigrams; a CJK character with
    no adjacent CJK neighbour yields itself. ASCII runs are never split. The
    same span never contributes both a bigram and a unigram.
    """
    terms: list[str] = []
    for segment in _SEGMENT_RE.findall(normalize(text)):
        if _ASCII_RE.fullmatch(segment):
            terms.append(segment.lower())
        elif len(segment) == 1:
            terms.append(segment)
        else:
            terms.extend(segment[i:i + 2] for i in range(len(segment) - 1))
    return terms


def snippet_tokens(text: str) -> list[str]:
    """Coarser tokenizer for snippet line selection.

    Individual CJK characters and whole ASCII runs, all lowered.
    Shares :func:`normalize` and :data:`CJK_CHAR_RANGES` with
    :func:`scoring_terms` (D19-010).
    """
    return [t.lower() for t in _SNIPPET_RE.findall(normalize(text))]
