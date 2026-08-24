# 一次資料: MVP 実装とセルフレビューの実測記録

## 発端の Issue

原本は [#1](https://github.com/taito-station/doc-query/issues/1)（転記しない）。
本文は `gh issue view 1` で取得する。

## トークン削減の実測（2026-08-23）

対象は 3 ページの日本語 PDF（入場券の販売概要、11,269 文字）。索引は 15 チャンク、所要 1.3 秒。

```
全文の抽出テキスト        10,566 トークン
docq search --top-k 3 --max-tokens 800 の応答:
  "オレンジシート"           647 トークン  （全文比  6.1%）
  "先行販売 抽選"            682 トークン  （全文比  6.5%）
  "電話 問い合わせ"          790 トークン  （全文比  7.5%）
```

トークン計上は `tiktoken` 導入済みの環境での実測。

## 実装中に踏んだ不具合（MVP 期）

いずれも実行して再現したもの。

1. **`FOREIGN KEY constraint failed`**。`store.py` でチャンク挿入をファイルの upsert より先に実行して
   いた。`upsert_file` を先に呼ぶ順序へ修正。
2. **`rank_bm25` の IDF が 0 になり検索結果が消える**。3 ページのテスト PDF で「東京」が 2 チャンク中
   1 チャンクにのみ出現する状態を作ったところ、スコアが 0 になりヒットが返らなかった。標準の Okapi
   IDF 式は `N=2, n=1` で厳密に 0 になる。`log(1 + ...)` による平滑化の自前実装へ統一して解決。
3. **`reportlab` で日本語が文字化けする**。デフォルトフォント（Helvetica）では CJK が
   `nnnnnnnnnnn` のような出力になった。`UnicodeCIDFont("HeiseiMin-W3")` へ切り替えて解決。
4. **`reportlab` の `Canvas.save()` が余分な空白ページを追加する**。各ページ描画後に毎回
   `showPage()` を呼んでいたため。最終ページの後は呼ばないよう修正。
5. **`--root` に相対パスを渡すと `ValueError`**。`Path.cwd()`（絶対パス）に対する `relative_to()` が
   失敗していた。pytest では常に絶対パスを渡していたため検出できていなかった。

## セルフレビューで見つかった不具合（2026-08-23〜24）

独立レビュアー 2 名 + 親による再現確認を 5 巡。**すべて実コマンドで再現を確認してから修正した。**

### 1 巡目

- **`--root` に作業ディレクトリ外の絶対パスを渡すとトレースバック**。`relative_to()` が try の外に
  あり、未捕捉の `ValueError` になる。実行例:
  ```
  $ docq index --root /elsewhere/docs
  ValueError: '/elsewhere/docs/x.pdf' is not in the subpath of '/cwd'
  ```
- **prune が他 root の索引を消す**。実行例:
  ```
  $ docq index --root docs      # {"indexed":1,"pruned":0,"chunks":15}
  $ docq index --root manuals   # {"indexed":1,"pruned":1,...}  ← docs/ が消えた
  $ docq list --paths 'docs/*' | wc -l   # 0（ディスク上には存在する）
  ```

### 2 巡目（1 巡目の修正が持ち込んだ退行を含む）

- **`--root` にファイルを渡すとそのファイルの索引だけが消える**。root ガードが `exists()` 止まり
  だったため。実行例:
  ```
  $ docq index --root docs/a.pdf
  {"scanned":0,"indexed":0,"pruned":1,"errors":[]}   ← rc=0 のまま索引が空に
  ```
- **`archive.pdf` という名前のディレクトリ**が候補に入り、`IsADirectoryError` で以後の索引が恒久的に
  失敗する。
- **`--db` を別ディレクトリから開くと生存エントリが prune される**。

### 3 巡目（2 巡目の修正が持ち込んだ退行）

- **`Path.exists()` が `PermissionError` を送出**。読めないサブディレクトリを含む再索引で
  トレースバックになり、末尾の `conn.commit()` に到達せず**その実行の索引結果が丸ごと失われる**。
  ```
  $ chmod 000 docs/locked && docq index --root docs
  PermissionError: [Errno 13] Permission denied: '.../docs/locked/x.pdf'
  ```
  `os.path.exists()` に替えても解決しない——例外を握り潰して `False` を返すので、生存ファイルを
  prune する元の fail-open に戻る。実測:
  ```
  Path.exists() raised: PermissionError
  os.path.exists() -> False
  ```

### 4 巡目（3 巡目の修正が持ち込んだ退行）

- **`os.lstat` がダングリング symlink を「存在する」と判定**。走査側は `is_file()` が偽なので候補から
  落ち、prune もされず errors にも出ず、**削除済みファイルの本文が索引に残り続ける**。実測:
  ```
  lstat -> 成功（存在扱い）
  stat  -> FileNotFoundError
  ```

### 5 巡目

- **`p.is_file()` が `chmod 400` のディレクトリで `PermissionError`**。同じ欠陥クラスの 3 箇所目。
  `sorted()` が try の外にあるため実行結果が全損する。
- **`chmod 000` の root を指定しても「空のディレクトリ」と区別できず rc=0**。`Path.rglob` が読めない
  ディレクトリを無言でスキップするため。

### 観測されたパターン

**5 巡すべてで同じ型の欠陥が出た**——「誤りが無言で成功に見える」。走査が短く終わる理由（権限・
マウント・競合・パスの種別違い）を「対象が無い」と解釈し、その推定に基づいて不可逆な削除を行う、
という構図が実装のあちこちに埋まっていた。

修正後のテストは 47 件（MVP 時点 18 件 + 回帰 29 件）。

## 環境

- Python 3.13.12（pyenv）、macOS
- 依存: pdfplumber, tiktoken, pytest, reportlab
