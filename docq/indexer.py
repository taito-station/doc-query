"""Scan PDFs under configured roots, chunk them, and persist to the store.

Chunking follows mdq's `fixed_window` strategy (same defaults: 1000-char
window, 200-char overlap), applied per PDF page rather than per file —
PDFs have no heading structure, but a page number is a stable, meaningful
location to report back to the caller.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, NamedTuple

from . import extractor_pdf as _extractor
from . import store as _store
from . import tokens as _tokens

FIXED_WINDOW_CHARS = 1000
FIXED_WINDOW_OVERLAP = 200

PDF_SUFFIX = ".pdf"


class IndexResult(NamedTuple):
    chunks: int
    status: Literal["indexed", "skipped", "no_text"]


@dataclass
class IndexStats:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    no_text: int = 0
    no_text_files: list[str] = field(default_factory=list)
    pruned: int = 0
    chunks: int = 0
    # Errors mean the run did not do what was asked and set a non-zero exit
    # code. Warnings mean it did, but something is worth knowing. Keeping
    # them apart matters: an unreadable directory does not resolve on its
    # own, so folding it into `errors` would make every subsequent run fail
    # and train the caller to stop reading the exit code at all.
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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


def _stat_or_none(path: Path) -> os.stat_result | Literal[False] | None:
    """Three-way stat: stat_result (present), False (absent), None (unknown).

    Callers must compare with ``is False`` / ``is None``; ``not st`` would
    collapse the two apart cases into one.

    Neither ``Path.exists`` nor ``os.path.exists`` can express the third
    answer, and both are wrong for this. ``Path.exists`` lets
    ``PermissionError`` through, so an unreadable parent crashes the scan;
    ``os.path.exists`` swallows it and reports False, which reads as
    "deleted". Follows symlinks deliberately (``os.stat``, not ``lstat``): a
    link whose target is gone is gone, and ``lstat`` would call it present
    and leave the entry in the index forever.
    """
    try:
        return os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return None


def _is_gone(path: Path) -> bool | None:
    """True if `path` is definitely absent, False if present, None if unknown."""
    st = _stat_or_none(path)
    if st is None:
        return None
    if st is False:
        return True
    # Something is there, but not a file we could ever index — a directory
    # that took the path over is as gone as a deletion, and the scan will
    # never re-add it.
    return not stat.S_ISREG(st.st_mode)


def _is_usable_root(path: Path) -> tuple[bool, str]:
    """Whether `path` can be scanned, plus the reason when it cannot.

    Uses the same three-way stat as :func:`_is_gone` rather than
    ``Path.is_dir``, which raises ``PermissionError`` for an unreadable
    parent — the exact failure the prune side already guards against.
    """
    st = _stat_or_none(path)
    if st is None:
        return False, "cannot stat root"
    if st is False:
        return False, "root does not exist"
    if not stat.S_ISDIR(st.st_mode):
        return False, "root is not a directory"
    return True, ""


def _walk_pdfs(root: Path, stats: "IndexStats") -> list[Path]:
    """PDFs under `root`, in a stable order, reporting what could not be read.

    `Path.rglob` is unusable for this in two ways. It drops unreadable
    directories without a word, so a permissions problem is indistinguishable
    from an empty tree — the same "an empty scan looks like success" failure
    the prune side took three rounds to close. And filtering its results with
    `Path.is_file` raises `PermissionError` for a directory that is readable
    but not traversable, which aborts the whole run. `os.walk` reports both
    through `onerror` and classifies entries itself, so neither case is
    silent and neither one crashes.

    Suffix matching is case-insensitive: `*.pdf` as a glob would silently
    drop REPORT.PDF even on a case-insensitive filesystem.
    """
    found: list[Path] = []

    def on_error(exc: OSError) -> None:
        target = getattr(exc, "filename", None) or root
        stats.warnings.append(f"{target}: cannot read directory ({exc.strerror})")

    # followlinks=False: a symlinked directory would otherwise let a loop
    # run forever, and its contents are reachable from their real location.
    for dirpath, _dirnames, filenames in os.walk(root, onerror=on_error,
                                                  followlinks=False):
        for name in filenames:
            if not name.lower().endswith(PDF_SUFFIX):
                continue
            path = Path(dirpath) / name
            st = _stat_or_none(path)
            if st is False:
                # A symlink whose target is gone. Leaving it out of the scan
                # is what lets prune remove the stale entry.
                continue
            if st is None:
                stats.warnings.append(f"{path}: cannot stat, skipped")
                continue
            if stat.S_ISREG(st.st_mode):
                found.append(path)
    found.sort()
    return found


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


def index_one_file(conn, repo_root: Path, pdf_path: Path) -> IndexResult:
    """Index a single PDF. Returns IndexResult(chunks, status).

    Normalizes and claims `repo_root` itself rather than trusting the caller:
    this is a public entry point that writes keys, so the invariant "every
    key in a store shares one base directory" has to hold here too, not only
    in :func:`index_paths`.

    Does not commit; the caller owns the transaction.
    """
    repo_root = repo_root.resolve()
    _store.check_base_dir(conn, repo_root)
    rel = rel_path(pdf_path, repo_root)
    st = pdf_path.stat()
    sha1 = _sha1_of_file(pdf_path)
    existing = _store.get_file_meta(conn, rel)
    if existing is not None and existing[0] == sha1:
        return IndexResult(0, "skipped")

    # Everything that can fail for this file happens before the first write,
    # so a run whose only PDFs are unreadable neither claims the store nor
    # leaves a file registered with no chunks behind it (which would then be
    # skipped as unchanged on every later run).
    pages = _extractor.extract_pages(pdf_path)

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
    # First write of the run: claim the store here, so nothing above this
    # point can bind a base directory it never actually indexed.
    #
    # Wrapped in a savepoint because the writes are not independent: the
    # foreign key forces `upsert_file` to precede `insert_chunks`, so a
    # failure in between would leave the file recorded under its new sha1
    # with no chunks — and every later run would skip it as unchanged. The
    # caller still owns the commit.
    with _store.savepoint(conn, "index_one_file"):
        _store.bind_base_dir(conn, repo_root)
        _store.upsert_file(conn, rel, sha1, st.st_mtime, st.st_size)
        _store.delete_chunks_for(conn, rel)
        if rows:
            _store.insert_chunks(conn, rows)
    if rows:
        return IndexResult(len(rows), "indexed")
    return IndexResult(0, "no_text")


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
    found_under: dict[Path, int] = {}
    for root in roots:
        root = root.resolve()
        usable, reason = _is_usable_root(root)
        if not usable:
            # A typo'd or non-directory root must never look like
            # "scanned, found nothing" — that reading is indistinguishable
            # from an empty directory and, before prune learned to check the
            # filesystem, silently deleted the entry it was pointed at.
            stats.errors.append(f"{root}: {reason}")
            continue
        scanned_roots.append(root)
        found_under[root] = 0
        for pdf_path in _walk_pdfs(root, stats):
            stats.scanned += 1
            found_under[root] += 1
            rel = rel_path(pdf_path, repo_root)
            seen.add(rel)
            try:
                result = index_one_file(conn, repo_root, pdf_path)
            except _store.BaseDirMismatch:
                # A store-level invariant, not a problem with this file.
                # Demoting it to a per-file error string would hide it.
                raise
            except Exception as e:  # noqa: BLE001 - surface per-file, keep scanning
                stats.errors.append(f"{rel}: {e}")
                continue
            if result.status == "indexed":
                stats.indexed += 1
                stats.chunks += result.chunks
            elif result.status == "no_text":
                stats.no_text += 1
                stats.no_text_files.append(rel)
            elif result.status == "skipped":
                stats.skipped += 1
            else:
                raise ValueError(f"unexpected IndexResult status: {result.status!r}")

    if stats.no_text:
        names = stats.no_text_files[:10]
        if len(stats.no_text_files) > 10:
            names.append(f"... and {len(stats.no_text_files) - 10} more")
        stats.warnings.append(
            f"{stats.no_text} file(s) contained no extractable text "
            f"(scanned/image-only PDF — OCR is not supported): "
            + ", ".join(names)
        )

    if prune:
        indexed_under = {root: 0 for root in scanned_roots}
        candidates: list[tuple[str, Path, Path]] = []
        for rel in _store.list_all_paths(conn) - seen:
            abs_path = _abs_path(rel, repo_root)
            # Entries indexed from other roots were never looked at, so their
            # absence from `seen` says nothing about whether they still exist.
            root = next((r for r in scanned_roots if abs_path.is_relative_to(r)),
                        None)
            if root is None:
                continue
            indexed_under[root] += 1
            candidates.append((rel, abs_path, root))

        # A root that turned up nothing while holding entries could be an
        # unmounted mount point rather than a directory whose files were
        # deleted — but nothing on disk tells the two apart, and refusing to
        # prune would break the case prune exists for (a root that really was
        # emptied). Prune, and say that the whole root went.
        for root in sorted(root for root, n in indexed_under.items()
                           if n > 0 and found_under.get(root, 0) == 0):
            stats.warnings.append(
                f"{root}: scan found no files, so all {indexed_under[root]} "
                f"entries under it are candidates for removal"
            )

        for rel, abs_path, root in candidates:
            gone = _is_gone(abs_path)
            if gone is None:
                # Can't tell (unreadable parent, I/O error). Keep the entry
                # and say so: staying silent would read as a clean scan while
                # the index quietly goes stale.
                stats.warnings.append(f"{rel}: cannot verify, kept in the index")
                continue
            if not gone:
                continue
            _store.delete_file(conn, rel)
            stats.pruned += 1

    _store.set_meta(
        conn, "last_indexed_at",
        datetime.now(timezone.utc).isoformat(),
    )
    conn.commit()
    return stats
