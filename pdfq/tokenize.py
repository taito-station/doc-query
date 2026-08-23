"""Scoring tokenizer, vendored from mdq's ``scoring_terms`` (CJK bigram).

A run of CJK characters yields adjacent bigrams (mirrors Lucene's
CJKBigramFilter); ASCII runs are kept whole. This is the term unit BM25
ranking matches on; excerpt selection uses a separate, coarser tokenizer
(see :mod:`pdfq.search`) so the returned snippet is unaffected by it.
"""
from __future__ import annotations

import re

CJK_CHAR_RANGES: tuple[tuple[str, str], ...] = (
    ("぀", "ヿ"),  # hiragana + katakana (incl. the ー prolonged mark)
    ("一", "鿿"),  # CJK unified ideographs
)

_CJK_CLASS = "".join(f"{low}-{high}" for low, high in CJK_CHAR_RANGES)
_ASCII_RUN = r"[A-Za-z0-9_]+"
_SEGMENT_RE = re.compile(rf"{_ASCII_RUN}|[{_CJK_CLASS}]+")
_ASCII_RE = re.compile(_ASCII_RUN)


def scoring_terms(text: str) -> list[str]:
    """Return the terms BM25 ranking matches on.

    A run of CJK characters yields its adjacent bigrams; a CJK character with
    no adjacent CJK neighbour yields itself. ASCII runs are never split. The
    same span never contributes both a bigram and a unigram.
    """
    terms: list[str] = []
    for segment in _SEGMENT_RE.findall(text):
        if _ASCII_RE.fullmatch(segment):
            terms.append(segment.lower())
        elif len(segment) == 1:
            terms.append(segment)
        else:
            terms.extend(segment[i:i + 2] for i in range(len(segment) - 1))
    return terms
