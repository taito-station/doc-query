"""SQLite-backed persistent store for the chunk index.

Format-agnostic: a chunk is text plus a location, so the same schema serves
any extractor. Intentionally small (adapted from mdq's `store.py`, trimmed to
what fixed-window chunks need: no headings, no FTS5 mirror, no embeddings).
BM25 ranking is computed at query time over the chunks loaded from this store
— fine for the small/medium corpora this tool targets.
"""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = Path(".docq") / "index.sqlite"

# 2: added the `meta` table (records the base directory path keys are
# relative to). Bumped so a future version check can tell a pre-`meta`
# index apart from one that simply has not been bound yet.
SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  path        TEXT PRIMARY KEY,
  sha1        TEXT NOT NULL,
  mtime       REAL NOT NULL,
  size_bytes  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id    TEXT PRIMARY KEY,
  path        TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
  location    TEXT NOT NULL,
  start_page  INTEGER NOT NULL,
  end_page    INTEGER NOT NULL,
  token_est   INTEGER NOT NULL,
  text        TEXT NOT NULL,
  part_index  INTEGER NOT NULL DEFAULT 0,
  part_total  INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
CREATE TABLE IF NOT EXISTS meta (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL
);
"""

BASE_DIR_KEY = "base_dir"


class BaseDirMismatch(Exception):
    """The store was written against a different base directory.

    Path keys are relative to the directory indexing ran from, and that
    directory is not recoverable from the keys themselves. Opening the same
    ``--db`` from somewhere else would reinterpret every key against the new
    base: the same file gets indexed twice under two keys, and prune reads
    live entries as gone. Refuse instead of guessing.
    """


@contextlib.contextmanager
def savepoint(conn: sqlite3.Connection, name: str):
    """Roll back just this block on failure, leaving the transaction open.

    `with conn:` would commit the whole connection, which belongs to the
    caller. A savepoint scopes the undo to one unit of work instead.
    """
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        conn.execute(f"ROLLBACK TO {name}")
        conn.execute(f"RELEASE {name}")
        raise
    conn.execute(f"RELEASE {name}")


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def check_base_dir(conn: sqlite3.Connection, base_dir: Path) -> None:
    """Raise unless `base_dir` may serve as this store's key basis.

    Read-only, so callers can fail fast before doing any work. Read paths
    (`search` / `get` / `list`) do not call this at all: they only echo keys
    back, so a mismatch there is cosmetic, and refusing would make an index
    unreadable from anywhere but the directory that built it.
    """
    recorded = get_meta(conn, BASE_DIR_KEY)
    current = str(base_dir.resolve())
    if recorded == current:
        return
    if recorded is not None:
        raise BaseDirMismatch(
            f"index was built from {recorded!r}, but this run is in "
            f"{current!r}. Re-run from there, use a separate --db, or "
            f"delete the index to rebuild it here."
        )
    if list_all_paths(conn):
        # Unrecorded *and* already holding entries: those keys were written
        # against some base we cannot recover, so adopting the current one
        # would reinterpret every key — exactly the damage this guard exists
        # to prevent, just once and silently.
        raise BaseDirMismatch(
            "index has entries but no recorded base directory (built before "
            "this check existed). Delete the index and rebuild it."
        )


def bind_base_dir(conn: sqlite3.Connection, base_dir: Path) -> None:
    """Claim `base_dir` as this store's key basis. Call before writing keys.

    Claiming happens at the point of an actual write, not when a run starts:
    otherwise `docq index --root typo` from the wrong directory would bind an
    empty store to a directory it never indexed, and every later run from the
    right one would be refused.

    No commit here either — the caller's own commit makes the claim atomic
    with the writes it covers, so a run that fails partway leaves no claim.
    """
    check_base_dir(conn, base_dir)
    set_meta(conn, BASE_DIR_KEY, str(base_dir.resolve()))


def open_store(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open (or create) the SQLite store."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    gitignore = db_path.parent / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    # Stamp the version only on a store that has none. Overwriting it every
    # time would erase the very evidence the number exists to carry: an old
    # store would be relabelled current the first time it was opened, and a
    # later migration check would have nothing left to look at.
    if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


def upsert_file(conn: sqlite3.Connection, path: str, sha1: str, mtime: float,
                 size_bytes: int) -> None:
    conn.execute(
        "INSERT INTO files(path, sha1, mtime, size_bytes) VALUES(?,?,?,?) "
        "ON CONFLICT(path) DO UPDATE SET sha1=excluded.sha1, mtime=excluded.mtime, "
        "size_bytes=excluded.size_bytes",
        (path, sha1, mtime, size_bytes),
    )


def delete_chunks_for(conn: sqlite3.Connection, path: str) -> None:
    conn.execute("DELETE FROM chunks WHERE path = ?", (path,))


def insert_chunks(conn: sqlite3.Connection, rows: Iterable[tuple]) -> None:
    """Insert chunk rows.

    Each row: (chunk_id, path, location, start_page, end_page, token_est,
    text, part_index, part_total).
    """
    conn.executemany(
        "INSERT OR REPLACE INTO chunks(chunk_id, path, location, start_page, "
        "end_page, token_est, text, part_index, part_total) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        list(rows),
    )


def get_file_meta(conn: sqlite3.Connection, path: str) -> tuple[str, float] | None:
    cur = conn.execute("SELECT sha1, mtime FROM files WHERE path = ?", (path,))
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


def all_chunks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(conn.execute(
        "SELECT chunk_id, path, location, start_page, end_page, token_est, "
        "text, part_index, part_total FROM chunks"
    ))


def list_all_paths(conn: sqlite3.Connection) -> set[str]:
    """Return all file paths currently registered in the store."""
    return {row[0] for row in conn.execute("SELECT path FROM files")}


def delete_file(conn: sqlite3.Connection, path: str) -> int:
    """Delete a file row (chunks are removed via ON DELETE CASCADE).

    Returns the number of chunk rows removed.
    """
    n = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE path = ?", (path,)
    ).fetchone()[0]
    conn.execute("DELETE FROM files WHERE path = ?", (path,))
    return int(n)


def stats(conn: sqlite3.Connection) -> dict:
    f = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    c = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    return {"files": f, "chunks": c}
