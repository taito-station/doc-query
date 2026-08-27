"""BM25 search over the indexed chunks.

Format-agnostic: operates on whatever an extractor put in the store.
Adapted from mdq's `search.py`: same core mechanics (BM25 ranking over
CJK-bigram scoring terms, snippet trimming around the strongest matching
line, token-budget-aware result assembly), trimmed of the features this
project's flat fixed-window chunks don't use (FTS5 mirror, embeddings
fusion, pageindex tree, tags, parent/neighbor/part expansion).
"""
from __future__ import annotations

import fnmatch
import json
import math
import re
from dataclasses import dataclass

from . import tokenize as _tokenize

_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_]+|["
    + "".join(f"{low}-{high}" for low, high in _tokenize.CJK_CHAR_RANGES)
    + "]"
)

# Same BM25 length-normalization value mdq settled on (FR-MDQ-06).
LENGTH_NORM_B = 0.2


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class Hit:
    chunk_id: str
    path: str
    location: str
    start_page: int
    end_page: int
    score: float
    snippet: str | None

    def to_dict(self) -> dict:
        d: dict = {
            "chunk_id": self.chunk_id,
            "path": self.path,
            "location": self.location,
            "pages": [self.start_page, self.end_page],
            "score": round(self.score, 4),
        }
        if self.snippet is not None:
            d["snippet"] = self.snippet
        return d


class _MiniBM25:
    """Tiny BM25-Okapi implementation (no external deps).

    Uses ``log(1 + ...)`` IDF smoothing rather than the textbook Robertson
    formula: with the small chunk counts typical of a handful of indexed
    PDFs, a query term appearing in exactly half the corpus (or all of it)
    would otherwise score exactly 0 under the unsmoothed formula, silently
    dropping a real match. This is why a hand-rolled scorer is used here
    unconditionally instead of delegating to a general-purpose BM25 library
    tuned for larger corpora.
    """

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = LENGTH_NORM_B):
        self.k1, self.b = k1, b
        self.N = len(corpus)
        self.avgdl = sum(len(d) for d in corpus) / self.N if self.N else 0
        self.doc_len = [len(d) for d in corpus]
        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for doc in corpus:
            counts: dict[str, int] = {}
            for tok in doc:
                counts[tok] = counts.get(tok, 0) + 1
            self.tf.append(counts)
            for tok in counts:
                df[tok] = df.get(tok, 0) + 1
        self.idf = {
            tok: math.log(1 + (self.N - n + 0.5) / (n + 0.5))
            for tok, n in df.items()
        }

    def get_scores(self, query: list[str]) -> list[float]:
        scores = [0.0] * self.N
        for i in range(self.N):
            dl = self.doc_len[i]
            denom_norm = 1 - self.b + self.b * (dl / self.avgdl if self.avgdl else 1)
            for tok in query:
                if tok not in self.idf:
                    continue
                f = self.tf[i].get(tok, 0)
                if f == 0:
                    continue
                scores[i] += self.idf[tok] * (f * (self.k1 + 1)) / (
                    f + self.k1 * denom_norm
                )
        return scores


def _make_snippet(text: str, query_tokens: list[str], radius: int = 2,
                   max_chars: int = 400) -> str:
    """Return a compact snippet centered on the strongest matching line."""
    lines = text.splitlines()
    if not lines:
        return ""
    qset = set(query_tokens)
    best_idx = 0
    best_score = -1
    for i, line in enumerate(lines):
        toks = set(tokenize(line))
        score = len(toks & qset)
        if score > best_score:
            best_score = score
            best_idx = i
    lo = max(0, best_idx - radius)
    hi = min(len(lines), best_idx + radius + 1)
    snippet = "\n".join(lines[lo:hi])
    if len(snippet) > max_chars:
        snippet = snippet[: max_chars - 1] + "…"
    return snippet


def _excerpt(text: str, query_tokens: list[str], radius: int,
             return_unit: str) -> str | None:
    if return_unit == "locations":
        return None
    if return_unit == "chunk":
        return text
    return _make_snippet(text, query_tokens, radius=radius)


def _path_matches(path: str, globs: list[str]) -> bool:
    if not globs:
        return True
    return any(fnmatch.fnmatch(path, g) for g in globs)


def _scoring_text(row) -> str:
    """Text used for ranking only; the excerpt stays anchored to the body."""
    return f"{row['path']}\n{row['text']}"


def _budget_cost(hit: Hit) -> int:
    from . import tokens as _tokens

    return max(1, _tokens.count_tokens(json.dumps(hit.to_dict(), ensure_ascii=False)))


def _sort_scored(scored) -> None:
    scored.sort(key=lambda item: (
        -float(item[0]),
        str(item[1]["path"]),
        int(item[1]["start_page"]),
        str(item[1]["chunk_id"]),
    ))


def search(conn, query: str, *, mode: str = "bm25",
           top_k: int = 5, max_tokens: int = 800,
           path_globs: list[str] | None = None,
           snippet_radius: int = 2,
           return_unit: str = "line") -> list[Hit]:
    """Run a search against the indexed chunks.

    mode: 'bm25' | 'grep'
    return_unit: 'line' (default) centres a `snippet_radius`-line window on
        the strongest matching line; 'chunk' returns the full chunk body;
        'locations' returns no body at all (cheapest way to see more hits).
    """
    from . import store as _store

    if not query.strip():
        # Otherwise the empty-token path below falls through to grep, where
        # `re.escape("")` matches at every offset and every chunk comes back
        # ranked by length.
        return []

    rows = _store.all_chunks(conn)
    if path_globs:
        rows = [r for r in rows if _path_matches(r["path"], path_globs)]
    if not rows:
        return []

    q_tokens = tokenize(query)

    if mode == "grep" or not q_tokens:
        pat = re.compile(re.escape(query), re.IGNORECASE)
        scored = []
        for r in rows:
            n = len(pat.findall(r["text"]))
            if n > 0:
                scored.append((float(n), r))
        _sort_scored(scored)
    else:
        corpus = [_tokenize.scoring_terms(_scoring_text(r)) for r in rows]
        q_terms = _tokenize.scoring_terms(query)
        bm25 = _MiniBM25(corpus, b=LENGTH_NORM_B)
        scores = bm25.get_scores(q_terms)
        scored = [(float(s), r) for s, r in zip(scores, rows) if s > 0]
        _sort_scored(scored)

    hits: list[Hit] = []
    spent = 0
    for score, r in scored[: max(top_k * 6, top_k)]:
        snippet = _excerpt(r["text"], q_tokens, snippet_radius, return_unit)
        candidate = Hit(
            chunk_id=r["chunk_id"],
            path=r["path"],
            location=r["location"],
            start_page=r["start_page"],
            end_page=r["end_page"],
            score=score,
            snippet=snippet,
        )
        est = _budget_cost(candidate)
        if spent + est > max_tokens and hits:
            break
        spent += est
        hits.append(candidate)
        if len(hits) >= top_k:
            break

    return hits


def get_chunk(conn, chunk_id: str) -> dict | None:
    import sqlite3 as _sql
    conn.row_factory = _sql.Row
    row = conn.execute(
        "SELECT chunk_id, path, location, start_page, end_page, token_est, "
        "text FROM chunks WHERE chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "chunk_id": row["chunk_id"],
        "path": row["path"],
        "location": row["location"],
        "pages": [row["start_page"], row["end_page"]],
        "token_est": row["token_est"],
        "text": row["text"],
    }


def list_chunks(conn, path_globs: list[str] | None = None,
                 limit: int = 200) -> list[dict]:
    import sqlite3 as _sql
    conn.row_factory = _sql.Row
    rows = list(conn.execute(
        "SELECT path, location, start_page, end_page FROM chunks "
        "ORDER BY path, start_page"
    ))
    out = []
    for r in rows:
        if path_globs and not _path_matches(r["path"], path_globs):
            continue
        out.append({
            "path": r["path"],
            "location": r["location"],
            "pages": [r["start_page"], r["end_page"]],
        })
        if len(out) >= limit:
            break
    return out
