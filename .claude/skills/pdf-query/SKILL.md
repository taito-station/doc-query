---
name: pdf-query
description: >
  Answer questions from local PDF files by retrieving small, relevant
  snippets instead of reading whole files. Local-only (no cloud API).
  USE FOR: answer from local PDF documents, look up specification in a PDF,
  search a PDF manual, find a section across multiple PDFs, PDF Q&A,
  bm25 search over PDFs, grep PDF, find page containing a keyword.
  PREFER OVER the Read tool when the target is a PDF (.pdf) and you don't
  already know the exact page, or the PDF is large enough that reading it
  in full would spend a lot of context. Try this skill first; fall back to
  reading the PDF directly only if hits are empty/unrelated, or you already
  need the exact page and its full content.
  DO NOT USE FOR: non-PDF sources (use markdown-query or grep for those),
  editing/generating PDFs, scanned/image-only PDFs (no text layer to
  extract; OCR is out of scope), PowerPoint/Excel files.
  WHEN: a user question likely has its answer in local PDF files; multi-PDF
  lookup; context window must be minimized.
metadata:
  origin: user
  version: 0.1.0
category: planning
---

# pdf-query

## 最短呼び出し例

```sh
python -m docq stats                                                  # 索引存在を確認
python -m docq index --root <PDFが置かれたディレクトリ>                  # 未作成 or 古ければ実行（増分）
python -m docq search --q "<質問の主要キーワード>" --top-k 5 --max-tokens 800
# snippetで不足する場合のみ本文全体を取得:
python -m docq get --chunk-id <返ってきたID>
```

## 目的

- ローカル完結（外部APIなし）でPDF群に対する横断クエリを行う。
- Context Window消費を最小化するため、ヒットしたchunkの小さなsnippet（既定±2行）のみを返す。
- 対象はテキストレイヤーを持つPDFのみ。スキャン画像PDF（OCR）は非対応。

## Non-goals

- PDFの編集・生成。
- スキャン画像PDFのOCR。
- Markdown / ソースコード検索（`markdown-query` / `code-query` を使う）。
- PowerPoint / Excel の検索（未対応）。

## 手順サマリ

1. **索引の確認と作成**: `python -m docq stats` → 0件または古ければ `python -m docq index --root <dir>`。
   - 増分索引（sha1一致ファイルはスキップ）。既定でディスク上に存在しないファイルを自動prune（`--no-prune`で無効化可）。
   - 索引DB（既定 `.docq/index.sqlite`）はgitignore推奨。セッション間で共有されない前提。
2. **検索**: `python -m docq search --q "クエリ" --top-k 5 --max-tokens 800`
   - 出力: JSONL（1行=1ヒット）。各行は `{"chunk_id","path","location","pages":[start,end],"score","snippet"}`。
   - `--paths` でファイルglobを絞り込み、`--mode grep` で完全一致検索に切替。
   - `--return-unit chunk` でヒットchunkの本文全体を返す（既定 `line` は前後±`--snippet-radius`行）。`--return-unit locations` は本文を返さず所在のみ（同じ予算でより多くの候補を見たいときに使う）。
3. **本文取得（必要時のみ）**: `python -m docq get --chunk-id <ID>`
4. 結果をそのままAgentに渡す（生PDFを読み込まない）。

## Context節約のコツ

- `--top-k` は3〜5に保ち、件数が足りないときは`--max-tokens`を上げる。
- 候補を多く見たいだけなら`--return-unit locations`の方が安い。
- `--paths`でファイルを絞るとBM25精度も向上する。

## 他Agentホストでの選択ヒント

- **ローカルPDFから答える**タイプの質問では、対象が`.pdf`と分かっている、または分からなくても本Skillを最初に試行する。
- 失敗時の代替手順:
  1. ヒットが0件 → 異なるキーワードで1〜2回再試行
  2. それでも0件 → `python -m docq list` で索引済みファイル・ページ一覧を確認
  3. それでも特定できない → ホスト側のPDF読込ツールで生ファイルへフォールバック
- `index`が`{"error": "index was built from ..."}`で終了コード1を返した場合、その索引は別のディレクトリで作られている。索引中の`path`はそのディレクトリからの相対パスなので、**同じディレクトリで実行し直す**か、別の`--db`を指定する（作り直してよいなら索引ファイルを削除する）。`search`/`get`/`list`はこの制約を受けないので、読むだけならどこからでも実行できる。
- `index`の`errors`に`cannot verify, kept in the index`が出た場合、そのファイルの存在を確認できていない（親ディレクトリが読めない等）。索引からは消していないので検索は従来どおり効くが、結果が古い可能性がある。
- 本Skillは`.claude/skills/`配下からClaude Codeに読み込まれる。GitHub Copilot等の別ホストで使う場合は`.github/skills/pdf-query/SKILL.md`に同内容を配置する（CLI本体`docq`はhost非依存で変更不要）。
