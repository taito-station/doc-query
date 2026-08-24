# NOTICE

`docq/tokenize.py` and `docq/tokens.py` are vendored near-verbatim from the
`mdq` (markdown-query) package in [HypervelocityEngineering](https://github.com/dahatake/HypervelocityEngineering)
(MIT License).

`docq/store.py` and `docq/search.py` are adapted from the same `mdq` package:
the core mechanics (SQLite chunk store, BM25-over-CJK-bigram scoring, snippet
trimming, token-budget-aware result assembly) are reused, but the schema and
search surface are trimmed to what this project's fixed-window use case
needs — no FTS5 mirror, no embeddings fusion, no pageindex tree, no tags,
no Markdown heading hierarchy.

`docq/indexer.py`'s fixed-size sliding-window chunking (window/overlap size)
follows the same defaults as `mdq/strategies.py`'s `fixed_window` strategy.

`docq/cli.py` borrows the subcommand names and their surface (`index` /
`search` / `get` / `list` / `stats`) from `mdq`'s CLI so usage transfers, but
no code is copied.

Original repository license: MIT. See `LICENSE` in this repository for the
full text as applied to this project.
