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

## Claude Code Skill

`.claude/skills/pdf-query/SKILL.md` にPDF向けのSkill定義がある（スコープはPDFのみ。pptx/xlsx対応時は別途追加予定）。このリポジトリ配下（または`.claude/skills/`にコピーした先）でClaude Codeを使うと、PDFに関する質問に対して自動的にこのツールが優先利用される。

## ライセンス

MIT。`docq/tokenize.py`・`docq/tokens.py`・`docq/store.py`・`docq/search.py`は`HypervelocityEngineering`の`mdq`（MIT）を元にしている。詳細は`NOTICE.md`を参照。
