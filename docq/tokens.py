"""Token counting for the response budget, vendored from mdq's `tokens.py`.

`tiktoken` is imported lazily and only once so the search path does not pay
for it at import time. When unavailable the character heuristic is used and
:func:`counter_name` reports which counter produced the numbers, so an
approximation is never presented as an exact measurement.
"""
from __future__ import annotations

from typing import Any

_FALLBACK_CHARS_PER_TOKEN = 4.0
_ENCODER: Any = None
_RESOLVED = False


def _encoder() -> Any:
    global _ENCODER, _RESOLVED
    if not _RESOLVED:
        _RESOLVED = True
        try:
            import tiktoken

            _ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception:  # ImportError, cache miss, unknown encoding
            _ENCODER = None
    return _ENCODER


def counter_name() -> str:
    return "tiktoken/cl100k_base" if _encoder() is not None else "chars/4-approx"


def count_tokens(text: str) -> int:
    if not text:
        return 0
    encoder = _encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, int(len(text) / _FALLBACK_CHARS_PER_TOKEN))
