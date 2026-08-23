"""Scan PDFs under configured roots, chunk them, and persist to the store.

Chunking follows mdq's `fixed_window` strategy (same defaults: 1000-char
window, 200-char overlap), applied per PDF page rather than per file —
PDFs have no heading structure, but a page number is a stable, meaningful
location to report back to the caller.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from . import extractor as _extractor
from . import store as _store
from . import tokens as _tokens

FIXED_WINDOW_CHARS = 1000
FIXED_WINDOW_OVERLAP = 200


@dataclass
class IndexStats:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    pruned: int = 0
    chunks: int = 0
    errors: list[str] = field(default_factory=list)


def _sha1_of_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _windows(text: str, win: int = FIXED_WINDOW_CHARS,
             overlap: int = FIXED_WINDOW_OVERLAP) -> list[str]:
    step = max(1, win - overlap)
    n = len(text)
    parts: list[str] = []
    start = 0
    while start < n:
        end = min(n, start + win)
        parts.append(text[start:end])
        if end >= n:
            break
        start += step
    return parts


def _chunk_id(path: str, page: int, part_index: int) -> str:
    return hashlib.sha1(f"{path}:{page}:{part_index}".encode("utf-8")).hexdigest()


def index_one_file(conn, repo_root: Path, pdf_path: Path) -> int:
    """Index a single PDF; returns the number of chunks written (0 if skipped)."""
    rel = pdf_path.relative_to(repo_root).as_posix()
    stat = pdf_path.stat()
    sha1 = _sha1_of_file(pdf_path)
    existing = _store.get_file_meta(conn, rel)
    if existing is not None and existing[0] == sha1:
        return 0

    pages = _extractor.extract_pages(pdf_path)
    _store.upsert_file(conn, rel, sha1, stat.st_mtime, stat.st_size)
    _store.delete_chunks_for(conn, rel)

    rows: list[tuple] = []
    for page_num, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue
        parts = _windows(page_text)
        total = len(parts)
        for part_index, part_text in enumerate(parts):
            rows.append((
                _chunk_id(rel, page_num, part_index),
                rel,
                f"p.{page_num}",
                page_num,
                page_num,
                _tokens.count_tokens(part_text),
                part_text,
                part_index,
                total,
            ))
    if rows:
        _store.insert_chunks(conn, rows)
    return len(rows)


def index_paths(conn, repo_root: Path, roots: list[Path], *,
                 prune: bool = True) -> IndexStats:
    """Walk `roots` for *.pdf files (relative to `repo_root`) and index them."""
    stats = IndexStats()
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for pdf_path in sorted(root.rglob("*.pdf")):
            stats.scanned += 1
            rel = pdf_path.relative_to(repo_root).as_posix()
            seen.add(rel)
            try:
                n = index_one_file(conn, repo_root, pdf_path)
            except Exception as e:  # noqa: BLE001 - surface per-file, keep scanning
                stats.errors.append(f"{rel}: {e}")
                continue
            if n > 0:
                stats.indexed += 1
                stats.chunks += n
            else:
                stats.skipped += 1

    if prune:
        for rel in _store.list_all_paths(conn) - seen:
            _store.delete_file(conn, rel)
            stats.pruned += 1

    conn.commit()
    return stats
