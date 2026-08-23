"""CLI entry point: `python -m docq <index|search|get|list|stats>`.

Subcommand surface intentionally mirrors mdq's CLI so usage transfers
directly for anyone already familiar with it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import indexer as _indexer
from . import search as _search
from . import store as _store


def _open(db: str):
    return _store.open_store(Path(db))


def cmd_index(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    repo_root = Path.cwd()
    roots = [(repo_root / r) for r in (args.root or ["."])]
    stats = _indexer.index_paths(conn, repo_root, roots, prune=not args.no_prune)
    print(json.dumps({
        "scanned": stats.scanned,
        "indexed": stats.indexed,
        "skipped": stats.skipped,
        "pruned": stats.pruned,
        "chunks": stats.chunks,
        "errors": stats.errors,
    }, ensure_ascii=False))
    return 1 if stats.errors else 0


def cmd_search(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    hits = _search.search(
        conn, args.q,
        mode=args.mode,
        top_k=args.top_k,
        max_tokens=args.max_tokens,
        path_globs=args.paths,
        snippet_radius=args.snippet_radius,
        return_unit=args.return_unit,
    )
    for h in hits:
        print(json.dumps(h.to_dict(), ensure_ascii=False))
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    chunk = _search.get_chunk(conn, args.chunk_id)
    if chunk is None:
        print(json.dumps({"error": "not found", "chunk_id": args.chunk_id}))
        return 1
    print(json.dumps(chunk, ensure_ascii=False))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    for row in _search.list_chunks(conn, path_globs=args.paths, limit=args.limit):
        print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    print(json.dumps(_store.stats(conn), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="docq")
    p.add_argument("--db", default=str(_store.DEFAULT_DB_PATH),
                    help="Path to the SQLite index (default: .docq/index.sqlite)")
    sub = p.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Scan PDFs under --root and (re)index them")
    p_index.add_argument("--root", action="append",
                          help="Directory to scan for *.pdf (repeatable; default: .)")
    p_index.add_argument("--no-prune", action="store_true",
                          help="Do not remove index entries for files no longer on disk")
    p_index.set_defaults(func=cmd_index)

    p_search = sub.add_parser("search", help="BM25 search over the indexed chunks")
    p_search.add_argument("--q", required=True, help="Query string")
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.add_argument("--max-tokens", type=int, default=800)
    p_search.add_argument("--paths", nargs="*", default=None,
                           help="Glob(s) to restrict results to, e.g. 'docs/*'")
    p_search.add_argument("--snippet-radius", type=int, default=2)
    p_search.add_argument("--return-unit", choices=["line", "chunk", "locations"],
                           default="line")
    p_search.add_argument("--mode", choices=["bm25", "grep"], default="bm25")
    p_search.set_defaults(func=cmd_search)

    p_get = sub.add_parser("get", help="Fetch a chunk's full text by chunk_id")
    p_get.add_argument("--chunk-id", required=True)
    p_get.set_defaults(func=cmd_get)

    p_list = sub.add_parser("list", help="List indexed chunk locations")
    p_list.add_argument("--paths", nargs="*", default=None)
    p_list.add_argument("--limit", type=int, default=200)
    p_list.set_defaults(func=cmd_list)

    p_stats = sub.add_parser("stats", help="Show index file/chunk counts")
    p_stats.set_defaults(func=cmd_stats)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
