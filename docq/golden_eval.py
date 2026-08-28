"""Golden-query evaluation: correctness judgment, metrics, corpus generation.

The single implementation of correctness judgment lives here (REQ-D17-003).
The CLI script (``scripts/eval-golden.py``) is a thin wrapper.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from . import search as _search
from . import tokens as _tokens

_CJK_FONT = "HeiseiMin-W3"
_FONT_SIZE = 12
_PAGE_SEP = "%%PAGE%%"
_LEFT_MARGIN = 72
_RIGHT_MARGIN = 72
_TOP_Y = 800
_LINE_STEP = 14
BASELINE_EPSILON = 1e-9

_font_registered = False


def _ensure_font() -> None:
    global _font_registered
    if not _font_registered:
        pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))
        _font_registered = True


@dataclass
class GoldenQuery:
    anchor: str
    query: str
    expected_path: str
    expected_page: int


@dataclass
class EvalResult:
    top1: float
    topk: float
    mrr_at_k: float
    total_queries: int
    token_counter: str
    details: list[dict]


def is_correct(hit: _search.Hit, expected_path: str, expected_page: int) -> bool:
    """Single implementation of correctness judgment (D17-002, D17-003)."""
    return hit.path == expected_path and hit.start_page <= expected_page <= hit.end_page


def load_golden_set(path: Path) -> list[GoldenQuery]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [GoldenQuery(**entry) for entry in raw]


def validate_golden_set(
    queries: list[GoldenQuery],
    corpus_texts: dict[str, str],
) -> list[str]:
    """Validate golden set against corpus. Returns list of error messages."""
    errors: list[str] = []

    anchors = [q.anchor for q in queries]
    seen: set[str] = set()
    for a in anchors:
        if a in seen:
            errors.append(f"anchor が重複: {a!r}")
        seen.add(a)

    for q in queries:
        if q.expected_path not in corpus_texts:
            errors.append(f"[{q.anchor}] expected_path {q.expected_path!r} がコーパスに無い")
            continue
        text = corpus_texts[q.expected_path]
        n_pages = len(text.split(f"\n{_PAGE_SEP}\n"))
        if q.expected_page < 1 or q.expected_page > n_pages:
            errors.append(
                f"[{q.anchor}] expected_page={q.expected_page} がページ数 {n_pages} を超えている"
            )

    return errors


def _max_draw_width() -> float:
    page_w, _ = A4
    return page_w - _LEFT_MARGIN - _RIGHT_MARGIN


def generate_corpus(corpus_dir: Path, out_dir: Path) -> list[Path]:
    """Generate PDFs from source texts. Deterministic (D17-005).

    Raises ``ValueError`` if any line exceeds the drawable width.
    """
    _ensure_font()
    max_w = _max_draw_width()
    generated: list[Path] = []

    for txt_path in sorted(corpus_dir.glob("*.txt")):
        text = txt_path.read_text(encoding="utf-8")
        raw_pages = text.split(f"\n{_PAGE_SEP}\n")
        pages: list[list[str]] = []
        for pi, raw in enumerate(raw_pages, 1):
            lines = [ln for ln in raw.splitlines() if ln]
            for ln in lines:
                w = pdfmetrics.stringWidth(ln, _CJK_FONT, _FONT_SIZE)
                if w > max_w:
                    raise ValueError(
                        f"{txt_path.name} p.{pi}: 行幅 {w:.0f}pt が描画領域 {max_w:.0f}pt を超過: {ln!r}"
                    )
            pages.append(lines)

        pdf_name = txt_path.stem + ".pdf"
        pdf_path = out_dir / pdf_name
        c = canvas.Canvas(str(pdf_path), pagesize=A4, invariant=1)
        for page_i, lines in enumerate(pages):
            c.setFont(_CJK_FONT, _FONT_SIZE)
            y = _TOP_Y
            for ln in lines:
                c.drawString(_LEFT_MARGIN, y, ln)
                y -= _LINE_STEP
            if page_i < len(pages) - 1:
                c.showPage()
        c.save()
        generated.append(pdf_path)

    return generated


def corpus_text_map(corpus_dir: Path) -> dict[str, str]:
    """Build {pdf_filename: source_text} from corpus source files."""
    result: dict[str, str] = {}
    for txt_path in sorted(corpus_dir.glob("*.txt")):
        pdf_name = txt_path.stem + ".pdf"
        result[pdf_name] = txt_path.read_text(encoding="utf-8")
    return result


def evaluate(
    conn: sqlite3.Connection,
    queries: list[GoldenQuery],
    *,
    top_k: int = 5,
    max_tokens: int = 800,
) -> EvalResult:
    top1_hits = 0
    topk_hits = 0
    rr_sum = 0.0
    details: list[dict] = []

    for q in queries:
        hits = _search.search(conn, q.query, top_k=top_k, max_tokens=max_tokens)
        rank = None
        for i, h in enumerate(hits):
            if is_correct(h, q.expected_path, q.expected_page):
                rank = i + 1
                break

        entry: dict = {"anchor": q.anchor, "query": q.query, "rank": rank}
        if rank is not None:
            if rank == 1:
                top1_hits += 1
            topk_hits += 1
            rr_sum += 1.0 / rank
        details.append(entry)

    n = len(queries)
    return EvalResult(
        top1=top1_hits / n if n else 0.0,
        topk=topk_hits / n if n else 0.0,
        mrr_at_k=rr_sum / n if n else 0.0,
        total_queries=n,
        token_counter=_tokens.counter_name(),
        details=details,
    )


def check_baseline(
    result: EvalResult,
    baseline: dict,
    *,
    epsilon: float = BASELINE_EPSILON,
) -> list[str]:
    """Compare result against baseline. Returns list of failure messages."""
    failures: list[str] = []
    for metric in ("top1", "topk", "mrr_at_k"):
        actual = getattr(result, metric)
        expected = baseline[metric]
        if actual < expected - epsilon:
            failures.append(f"{metric}: {actual:.4f} < baseline {expected:.4f}")
    return failures
