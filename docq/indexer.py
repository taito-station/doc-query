"""Scan PDFs under configured roots, chunk them, and persist to the store.

Chunking follows mdq's `fixed_window` strategy (same defaults: 1000-char
window, 200-char overlap), applied per PDF page rather than per file —
PDFs have no heading structure, but a page number is a stable, meaningful
location to report back to the caller.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import extractor_pdf as _extractor
from . import store as _store
from . import tokens as _tokens

FIXED_WINDOW_CHARS = 1000
FIXED_WINDOW_OVERLAP = 200

PDF_SUFFIX = ".pdf"


@dataclass
class IndexStats:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    pruned: int = 0
    chunks: int = 0
    errors: list[str] = field(default_factory=list)


def _sha1_of_file(path: Path) -> str:
    # Change detection only, never a security boundary.
    h = hashlib.sha1(usedforsecurity=False)
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def rel_path(path: Path, repo_root: Path) -> str:
    """Path key stored in the index, as a POSIX path relative to `repo_root`.

    ``Path.relative_to`` cannot express "outside the root" and raises for a
    root the caller passed as an absolute path elsewhere on the filesystem —
    which is the ordinary way to use this tool (``--root ~/Documents`` from
    any working directory). ``os.path.relpath`` walks up with ``..`` instead,
    so every readable path gets a key. The only case it still rejects is a
    different drive on Windows; there the absolute path is the key.
    """
    try:
        return Path(os.path.relpath(path, repo_root)).as_posix()
    except ValueError:  # different drive (Windows only)
        return path.as_posix()


def _abs_path(rel: str, repo_root: Path) -> Path:
    """Inverse of :func:`rel_path`, resolving `..` lexically only.

    Deliberately not ``Path.resolve()``: keys are built from paths that
    ``rglob`` yielded under an already-resolved root, so following symlinks
    here would produce a path outside that root and make the containment
    check below disagree with the key that was stored.
    """
    return Path(os.path.normpath(repo_root / rel))


def _is_gone(path: Path) -> bool | None:
    """True if `path` is definitely absent, False if present, None if unknown.

    Neither ``Path.exists`` nor ``os.path.exists`` can express the third
    answer, and both are wrong here. ``Path.exists`` lets ``PermissionError``
    through (an unreadable parent crashes the scan); ``os.path.exists``
    swallows it and reports False, which reads as "deleted" and prunes a file
    that is still there. Prune only on a definite answer.
    """
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError:
        return None
    return False


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
    """Index a single PDF; returns the number of chunks written (0 if skipped).

    Normalizes and claims `repo_root` itself rather than trusting the caller:
    this is a public entry point that writes keys, so the invariant "every
    key in a store shares one base directory" has to hold here too, not only
    in :func:`index_paths`.
    """
    repo_root = repo_root.resolve()
    _store.bind_base_dir(conn, repo_root)
    rel = rel_path(pdf_path, repo_root)
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
    # Normalize here rather than trusting the caller: `rel_path` and the
    # prune containment check below both depend on this, so the invariant
    # belongs next to the code that relies on it.
    repo_root = repo_root.resolve()
    # Fail fast before scanning; the claim itself is made per write, in
    # `index_one_file`, so a run that writes nothing never binds the store.
    _store.check_base_dir(conn, repo_root)
    stats = IndexStats()
    seen: set[str] = set()
    scanned_roots: list[Path] = []
    for root in roots:
        root = root.resolve()
        if not root.is_dir():
            # A typo'd or non-directory root must never look like
            # "scanned, found nothing" — that reading is indistinguishable
            # from an empty directory and, before prune learned to check
            # `exists()`, silently deleted the entry it was pointed at.
            reason = "root does not exist" if not root.exists() \
                else "root is not a directory"
            stats.errors.append(f"{root}: {reason}")
            continue
        scanned_roots.append(root)
        # Match the suffix case-insensitively: `rglob` is case-sensitive even
        # on a case-insensitive filesystem, so `*.pdf` silently drops
        # REPORT.PDF. `is_file` because a *directory* named `archive.pdf`
        # matches the suffix too, and would fail every scan from then on.
        # Suffix first: `is_file` stats every entry, and only PDF candidates
        # are worth that syscall.
        pdfs = (p for p in root.rglob("*")
                if p.suffix.lower() == PDF_SUFFIX and p.is_file())
        for pdf_path in sorted(pdfs):
            stats.scanned += 1
            rel = rel_path(pdf_path, repo_root)
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
        # Two conditions, both required. Entries indexed from other roots
        # were never looked at, so their absence from `seen` says nothing
        # about whether they still exist. And even under a scanned root,
        # absence from `seen` is not proof the file is gone: `rglob` skips
        # unreadable subdirectories without raising. Confirm on disk before
        # deleting, so every way a scan can come up short fails safe.
        for rel in _store.list_all_paths(conn) - seen:
            abs_path = _abs_path(rel, repo_root)
            if not any(abs_path.is_relative_to(root) for root in scanned_roots):
                continue
            gone = _is_gone(abs_path)
            if gone is None:
                # Can't tell (unreadable parent, I/O error). Keep the entry
                # and say so: staying silent would read as a clean scan while
                # the index quietly goes stale.
                stats.errors.append(f"{rel}: cannot verify, kept in the index")
                continue
            if not gone:
                continue
            _store.delete_file(conn, rel)
            stats.pruned += 1

    conn.commit()
    return stats
