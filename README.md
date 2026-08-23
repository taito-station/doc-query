# pdf-query

ローカル完結（外部APIなし）でPDF群を横断検索し、ヒット箇所の小さなsnippetのみを返すツールです。LLMのContext Window消費を最小化することが目的です。`HypervelocityEngineering`の`mdq`（markdown-query）をPDF向けに移植したものです。

対象はテキストレイヤーを持つPDFのみ（スキャン画像PDFのOCRは非対応）。

## セットアップ

```bash
pip install -e ".[bm25,tokens,dev]"
```

## 使い方

```bash
# 索引対象PDFのディレクトリを走査して索引を作成（増分）
python -m pdfq index --root <PDFが置かれたディレクトリ>

# 検索
python -m pdfq search --q "<キーワード>" --top-k 5 --max-tokens 800

# 索引統計
python -m pdfq stats

# chunk本文の取得
python -m pdfq get --chunk-id <ID>
```

## Claude Code Skill

`.claude/skills/pdf-query/SKILL.md` にSkill定義がある。このリポジトリ配下（または`.claude/skills/`にコピーした先）でClaude Codeを使うと、PDFに関する質問に対して自動的にこのツールが優先利用される。

## ライセンス

MIT。`pdfq/tokenize.py`・`pdfq/tokens.py`・`pdfq/store.py`・`pdfq/search.py`は`HypervelocityEngineering`の`mdq`（MIT）を元にしている。詳細は`NOTICE.md`を参照。
