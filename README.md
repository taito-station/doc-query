# doc-query

ローカル完結（外部APIなし）でオフィス文書群を横断検索し、ヒット箇所の小さなsnippetのみを返すツールです。LLMのContext Window消費を最小化することが目的です。`HypervelocityEngineering`の`mdq`（markdown-query）を移植したものです。

現時点で対応しているのはテキストレイヤーを持つPDFのみ（スキャン画像PDFのOCRは非対応）。汎用の索引・検索コア（`docq/store.py`・`docq/search.py`・`docq/tokenize.py`・`docq/tokens.py`）はフォーマット非依存に作ってあり、pptx/xlsxはフォーマット固有の抽出モジュール（`docq/extractor_pdf.py`と並ぶ`docq/extractor_pptx.py`等）を追加するだけで対応できるように設計している（未実装）。

## セットアップ

```bash
pip install -e ".[tokens,dev]"
```

## 使い方

```bash
# 索引対象PDFのディレクトリを走査して索引を作成（増分）
python -m docq index --root <PDFが置かれたディレクトリ>

# 検索
python -m docq search --q "<キーワード>" --top-k 5 --max-tokens 800

# 索引統計
python -m docq stats

# chunk本文の取得
python -m docq get --chunk-id <ID>
```

実測（3ページの日本語PDF）: 全文 10,566 トークン → 検索結果 647〜790 トークン（**92〜94% 削減**）。

## ドキュメント

確定した設計・要件・決定の記録は `docs/knowledge/` にある。読む入口はここ。

| 文書 | 内容 |
|---|---|
| [docs/knowledge/README.md](docs/knowledge/README.md) | 文書の規約（2層蒸留・frontmatter・REQ-ID・決定ログ・機械検査の範囲） |
| [docs/knowledge/product-goals.md](docs/knowledge/product-goals.md) | 目的・成功条件・対象境界と非目標 |
| [docs/knowledge/index-and-search.md](docs/knowledge/index-and-search.md) | 索引の単位・スコアリング・返却単位・トークン予算・CLIの出力契約 |
| [docs/knowledge/search-quality-evaluation.md](docs/knowledge/search-quality-evaluation.md) | 検索品質の計測方法と受入基準 |
| [docs/knowledge/glossary.md](docs/knowledge/glossary.md) | 用語（特に「トークン」の3つの別物） |
| [docs/knowledge/vendoring-and-upstream.md](docs/knowledge/vendoring-and-upstream.md) | mdqからのvendor範囲と責任境界 |
| [docs/knowledge/ci-and-checks.md](docs/knowledge/ci-and-checks.md) | CIと機械検査の構成 |
| [docs/knowledge/doc-classes.md](docs/knowledge/doc-classes.md) | 文書クラスの定義（正本） |

**要件は各文書の REQ 表**にあり、`REQ-D19-006` のように名指しできる。現時点で Confirmed 10 件 /
Tentative 18 件。**検証手段の無い要件は Confirmed にしない**規約なので、Tentative には「未実装」と
「実装は満たしているが測る手段が無い」が混在する。内訳は
[index-and-search.md](docs/knowledge/index-and-search.md) の「Tentative の内訳」に表で置いてある。

開発時の判断規律は [CLAUDE.md](CLAUDE.md)。

## Claude Code Skill

`.claude/skills/pdf-query/SKILL.md` にPDF向けのSkill定義がある（スコープはPDFのみ。pptx/xlsx対応時は別途追加予定）。このリポジトリ配下（または`.claude/skills/`にコピーした先）でClaude Codeを使うと、PDFに関する質問に対して自動的にこのツールが優先利用される。

## ライセンス

MIT。`docq/tokenize.py`・`docq/tokens.py`・`docq/store.py`・`docq/search.py`は`HypervelocityEngineering`の`mdq`（MIT）を元にしている。詳細は`NOTICE.md`を参照。
