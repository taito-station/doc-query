"""SQLite-backed persistent store for the PDF chunk index.

Schema is intentionally small (adapted from mdq's `store.py`, trimmed to
what fixed-window PDF chunks need: no headings, no FTS5 mirror, no
embeddings). BM25 ranking is computed at query time over the chunks loaded
from this store — fine for the small/medium PDF corpora this tool targets.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = Path(".pdfq") / "index.sqlite"

SCHEMA_VERSION = 1

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
"""


def open_store(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open (or create) the SQLite store."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
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
