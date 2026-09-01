---
status: Confirmed
kind: knowledge
doc_class: [D19, D08, D10]
tags: [D19, D08, D10]
sources:
  - docq/indexer.py
  - docq/search.py
  - docq/store.py
  - docq/tokenize.py
  - docs/original-docs/1-doc-flow-introduction.md
  - docs/original-docs/2-fullwidth-scoring-defect.md
distilled_from_sha: "94738c7"
updated: "2026-09-02"
---

# 索引と検索

## モジュールの分割（D19）

```
extractor_pdf.py   PDF → ページごとのテキスト        ← フォーマット固有
indexer.py         ページ → チャンク、走査と prune   ← フォーマット固有
--------------------------------------------------
store.py           チャンクの永続化（SQLite）        ← フォーマット非依存
search.py          BM25 ランキングと snippet 抽出    ← フォーマット非依存
tokenize.py        スコアリング語の生成              ← フォーマット非依存
tokens.py          トークン数の計上                  ← フォーマット非依存
cli.py             サブコマンドと JSON 出力
```

依存は上から下へ一方向。`store` は `search` を知らない。フォーマット非依存層は `mdq` から vendor した
もので、改変点は [vendoring-and-upstream.md](vendoring-and-upstream.md)。

## データモデル（D08）

**SoT は文書ファイルそのもの。索引は常に再生成できる派生物**である。だから索引 DB（`.docq/`）は
バックアップ対象にならず、壊れたら作り直せばよい（D15 を n/a にできる根拠）。`open_store` は
`.docq/` 作成時に `.gitignore`（内容 `*`）を自動生成し、DB の誤コミットを防ぐ。

`files` テーブルが 1 ファイル 1 行、`chunks` が 1 チャンク 1 行で `files(path)` を外部キー参照する
（`ON DELETE CASCADE`）。`chunks.scoring_terms` は索引時に計算した BM25 用のスコアリング語を JSON
配列で保持する（検索時の再トークナイズを回避するため）。`meta` は key-value で、現在の唯一のキーは
基準ディレクトリ。

### チャンクの単位

**PDF の 1 ページを 1000 文字窓 / 200 文字オーバーラップの固定窓で分割**する。`mdq` と同じ既定値。

PDF には Markdown のような見出し構造が無いので、`mdq` が使う見出しベースのチャンク化は成立しない。
代わりに**ページ番号を所在情報として使う**——呼び出し側へ返せて、文書を開けば人間が確認できる、
安定した単位だからである。`location` は `p.3` の形。

### 索引キー

**キーは基準ディレクトリからの相対パス**（`docs/a.pdf`、`../outside/a.pdf`）で、基準は
`meta.base_dir` に記録する。

`Path.relative_to` ではなく `os.path.relpath` を使う。前者は「基準の外」を表現できず例外を投げるが、
`--root ~/Documents` のように外部ディレクトリを指すのがこのツールの通常の使い方である。

**絶対パスをキーにしない**のは、`path` が全ヒットに載る＝Context Window を直接消費するため。ただし
相対キーは基準に依存し、基準はキーからは復元できないので、**書き込み時に基準を照合して不一致なら
拒否する**。読み取り（`search` / `get` / `list`）は照合しない——キーを返すだけなので不一致は表示上の
問題にとどまり、拒否すると索引を作った場所でしか読めなくなる。

### 増分と prune

`sha1` 一致で未変更と判定してスキップする。テキストレイヤーを持たない PDF（スキャン PDF）は
`IndexStats.no_text` で `skipped` と分離集計し、OCR 非対応の warning を出す。prune の対象は
**(1) 今回スキャンした root 配下にあり、かつ (2) ディスク上に無いことを確認できた**エントリに限る。

この 2 条件はどちらも事故から入った。(1) が無いと `index --root docs` の後の `index --root manuals` で
`docs/` の索引が全消えする。(2) が無いと、走査が取りこぼしただけのファイル（読めないサブディレクトリ、
競合）が「削除された」と判定される。

**「走査で見つからなかった」を「消えた」の証拠にしない。** 存在確認は `os.stat` で 3 値（確かに無い /
ある / 判定不能）に分け、判定不能は消さずに warning にする。

## スコアリング（D19）

### 語彙単位

連続する CJK 文字は**隣接 2 文字の bigram**、隣接する CJK を持たない 1 文字はそれ自体、**ASCII 英数の
連なりは分割しない**。Lucene の `CJKBigramFilter` と同じ考え方で、`mdq` から vendor している。

**この層に既知の欠陥がある**——全角英数・ローマ数字・全角記号がどの文字クラスにも属さず脱落する
（[#2](https://github.com/taito-station/doc-query/issues/2)、
[2-fullwidth-scoring-defect.md](../original-docs/2-fullwidth-scoring-defect.md)）。修正は NFKC 正規化だが、
**語彙照合の単位の変更＝ランキングの既定値変更**なので、
[search-quality-evaluation.md](search-quality-evaluation.md) の回帰計測でベースラインを取ってから通す。

### BM25

`search.py` の `_MiniBM25`。ランキングに効く定数は 2 つ。

| 定数 | 実際に使われる値 | 置き場所 |
|---|---:|---|
| 語頻度飽和 `k1` | 1.5 | `_MiniBM25.__init__` の既定値（単一） |
| 文書長正規化 `b` | 0.2 | `search.LENGTH_NORM_B`（`__init__` の既定値も同一） |

移植元の要求（`FR-MDQ-06`）は「係数は実装内の単一の定数として定義し、利用可能な BM25 実装のいずれにも
同じ値で適用する」と定めており、`_MiniBM25.__init__` の既定値を `LENGTH_NORM_B` に統一して
REQ-D19-017 を充足した。

どちらも REQ-D17-006 の「ランキングに影響する既定値」に含まれるので、変更するには回帰計測が要る。

**IDF は `log(1 + (N-n+0.5)/(n+0.5))` で平滑化する。** 教科書の Okapi 式は語がコーパスの半数に出現
すると厳密に 0、それ以上で負になる。数ファイル程度の索引ではこれは日常的に起き、実ヒットのスコアが
静かに消える。外部ライブラリ（`rank_bm25`）ではなく自前実装なのは、この 1 点のためである。

**スコアリング対象にはチャンク本文に加えてパスを含める。** ファイル名にしか現れない語でもそのチャンクへ
到達できる。この連結はスコアリングのためだけで、返す snippet には影響しない。スコアリング語は**索引時に
計算して `chunks.scoring_terms` に永続化**されており、検索時は再トークナイズせず JSON を読み出すだけで
済む。検索はチャンクの `text` を読まずにスコアリングを完了し、snippet 生成が必要な上位候補のみ `text` を
後から取得する（2 フェーズ読み込み）。

### snippet の選定

**BM25 経路**では、スコアリング語彙とは別のトークナイザ（`search.tokenize`、より粗い）でクエリを分割し、
一致語が最も多い行を中心に `--snippet-radius` 行の窓を返す。

**grep 経路**では、正規表現パターンにマッチした最初の行を中心にする。grep に来るクエリは `q_tokens` が
空（スコアリング語が取れなかった）なので、トークン重複による中心行選定が機能しない。パターンマッチを
使うことで、実際にヒットした箇所をスニペットに含める。

**2 つのトークナイザがあることが今回の欠陥の温床になっている。** 文字クラスの定義が `tokenize.py` と
`search.py` に重複しており、片方だけ直す事故が起きうる（REQ-D19-010）。

### grep へのフォールバック

**実際に分岐を決めているのは snippet 側のトークナイザ**（`search.tokenize(query)` の結果が空かどうか）
であって、スコアリング語彙ではない。現在は両者の文字クラス定義が同一なので結果は一致するが、
**REQ-D19-006（NFKC をスコアリング側に入れる）を先に実装した瞬間にこの一致が崩れる**——正規化した
スコアリング語は取れるのに、snippet 側が空でフォールバックする、という食い違いが起きる。

REQ-D19-010 が塞ごうとしているのはこの構造そのもの。**#2 の修正では、どちらを門番にするかを先に
決めてから正規化を入れる。**

## CLI の出力契約（D10）

全サブコマンドが**標準出力に JSON** を書く。`search` / `list` は 1 ヒット 1 行の JSONL、
`index` / `stats` / `get` は 1 オブジェクト。

`index` の出力は **`errors` と `warnings` を分ける**。

- **`errors`**: 要求どおりに実行できなかった。**終了コード 1**。ただし成功した分は索引に反映されている
  （per-file のエラーでも走査は続き、末尾で commit する）
- **`warnings`**: 実行は成立したが知っておくべきこと。**終了コードに影響しない**

分ける理由は、読めないディレクトリのような**自然に解消しない**条件を `errors` に入れると、以後の実行が
毎回失敗し、呼び出し側が終了コードを読まなくなるため。

## 要件

<!-- REQ:begin D19 -->
| REQ-ID | 要件 | 検証手段 | 出典 | status |
|---|---|---|---|---|
| REQ-D19-001 | 索引単位は文書の 1 ページを 1000 文字窓 / 200 文字オーバーラップで分割したチャンクとし、`location` は `p.{N}` とする | `tests/test_indexer.py::test_windows_splits_long_text_with_overlap` / `::test_index_one_file_creates_chunks_per_page` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-002 | BM25 の IDF は `log(1 + (N-n+0.5)/(n+0.5))` で平滑化する。語がコーパスの半数以上のチャンクに出現してもスコアを 0 以下にしない | `tests/test_search.py::test_idf_stays_positive_for_a_term_in_every_document` / `::test_search_finds_a_term_present_in_every_chunk` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-003 | 返却単位は `line` / `chunk` / `locations` を呼び出し側が選べ、既定は `line` とする。指定が無いときに他へ切り替えない | `tests/test_search.py::test_search_returns_snippet_by_default` / `::test_search_return_unit_locations_has_no_snippet` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-004 | 応答トークン予算の見積りは、返却する 1 ヒット分の JSON 全体に対して行う。snippet 本文の長さだけで見積もらない | `tests/test_search.py::test_budget_cost_covers_full_json_not_just_snippet` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-005 | スコアリング語彙は、連続する CJK を隣接 bigram、単独 CJK は 1 文字、ASCII 英数の連なりは分割しない | `tests/test_tokenize.py::test_cjk_sequence_yields_bigrams` / `::test_single_cjk_yields_itself` / `::test_ascii_run_kept_whole_and_lowered` / `::test_mixed_cjk_ascii` | [2-fullwidth-scoring-defect.md](../original-docs/2-fullwidth-scoring-defect.md) | Confirmed |
| REQ-D19-006 | スコアリング語彙の生成前に NFKC 正規化を適用する。全角英数・ローマ数字・全角記号が語として残り、`指定席Ａ` と `指定席Ｓ` が同一クエリにならない | `tests/test_tokenize.py::test_nfkc_fullwidth_alpha` / `::test_nfkc_fullwidth_digits` / `::test_nfkc_roman_numeral` / `::test_nfkc_different_fullwidth_produce_different_terms` | [2-fullwidth-scoring-defect.md](../original-docs/2-fullwidth-scoring-defect.md) | Confirmed |
| REQ-D19-007 | 正規化は照合のためだけに用い、返す snippet 本文とページ範囲へ影響させない | `tests/test_search.py::test_snippet_preserves_original_text` | [2-fullwidth-scoring-defect.md](../original-docs/2-fullwidth-scoring-defect.md) | Confirmed |
| REQ-D19-008 | grep モードは生の本文だけを照合し、スコアリング規約（bigram / 正規化）の対象外とする | `tests/test_search.py::test_grep_mode_matches_raw_text_not_scoring_terms` | [2-fullwidth-scoring-defect.md](../original-docs/2-fullwidth-scoring-defect.md) | Confirmed |
| REQ-D19-009 | クエリからスコアリング語が 1 つも得られないときに限り grep へフォールバックする。空クエリはフォールバックせず 0 件を返す | `tests/test_search.py::test_empty_query_returns_no_hits` / `::test_query_with_no_scoring_terms_falls_back_to_grep` / `::test_query_with_scoring_terms_stays_in_bm25` | [2-fullwidth-scoring-defect.md](../original-docs/2-fullwidth-scoring-defect.md) | Confirmed |
| REQ-D19-010 | snippet 選定のトークナイザとスコアリング語彙は、同一の文字クラス定義と同一の正規化を共有し、片方だけ変更できない構造とする | `tests/test_tokenize.py::test_snippet_tokens_normalizes_fullwidth`（`normalize()` と `CJK_CHAR_RANGES` を `tokenize.py` に集約し、`search.tokenize()` は `snippet_tokens()` に委譲） | [2-fullwidth-scoring-defect.md](../original-docs/2-fullwidth-scoring-defect.md) | Confirmed |
| REQ-D19-011 | 索引キーは基準ディレクトリからの相対パスとし、基準を索引に記録する。異なる基準からの書き込みは拒否する。読み取りは拒否しない | `tests/test_indexer.py::test_index_paths_refuses_a_store_bound_to_another_base_dir` / `tests/test_cli.py::test_index_from_another_directory_is_refused_but_search_is_not` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-012 | prune の対象は、今回スキャンした root 配下にあり、かつディスク上に無いことを確認できたエントリに限る。走査で見つからなかったことを削除の根拠にしない | `tests/test_indexer.py::test_index_paths_does_not_prune_files_under_other_roots` / `::test_index_paths_keeps_entries_it_cannot_verify` / `::test_index_paths_prunes_a_symlink_whose_target_is_gone` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-013 | 走査が読めなかったディレクトリ・ファイルは無言でスキップせず報告する。索引できない状態と空のディレクトリを区別できるようにする | `tests/test_indexer.py::test_index_paths_reports_an_unreadable_root` / `::test_index_paths_reports_a_directory_it_cannot_read` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-014 | `index` の出力は `errors`（実行が成立しなかった。終了コード 1）と `warnings`（成立したが知っておくべきこと。終了コードに影響しない）を分ける | `tests/test_cli.py::test_warnings_are_reported_without_failing_the_run` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-015 | 1 ファイル分の索引書き込みは原子的とする。途中で失敗したファイルが「登録済みだがチャンク 0 件」として残り、以後スキップされ続けることがない | `tests/test_indexer.py::test_index_one_file_leaves_no_partial_write_behind` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-016 | 索引スキーマはバージョンを持ち、既存索引のバージョン不一致を検出して再構築を要求する | `tests/test_store.py::test_open_store_raises_on_schema_version_mismatch` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D19-017 | BM25 の文書長正規化係数は実装内の単一の値として定義する。既定値と呼び出し側で異なる値が存在してはならない | `tests/test_search.py::test_minibm25_default_b_equals_length_norm_b` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
<!-- REQ:end D19 -->

### Tentative の内訳

Tentative の要件は現在ない。

---

<!-- decision-log:begin -->
## 決定ログ

<!-- この節は append-only です。既存エントリの変更・削除は CI が検出します。 -->

### #1-1: BM25 を自前実装し IDF を平滑化する (2026-08-24) — 採用

#### コンテキスト

移植当初は `rank_bm25` ライブラリの Okapi BM25 を使っていた。3 ページの日本語 PDF（2 チャンク）で
「東京」を検索したところ、1 チャンクにしか出現しない語であるにもかかわらず**ヒットが 0 件**になった。

原因は Okapi の IDF 式 `log((N - n + 0.5) / (n + 0.5))` である。`N=2, n=1` で厳密に 0 になり、
スコアが 0 のヒットは結果から落ちる。半数を超えると負になる。

#### 決定

`rank_bm25` への依存を削除し、`log(1 + ...)` で平滑化する自前実装（`_MiniBM25`）に統一する。

#### 理由

- **小さい索引では「語が半数のチャンクに出る」が日常的に起きる。** 数ファイルを索引した状態が
  このツールの標準的な使い方であって、例外的な状況ではない。
- **失敗の仕方が悪い。** スコア 0 は「一致しなかった」と区別が付かず、利用者は語を変えて再試行する。
  索引にあるのに見つからないという最も困る壊れ方をする。
- 平滑化した式は Lucene が採用しているものと同じで、大きいコーパスでの挙動も損なわない。

#### 却下した代替案

- **`rank_bm25` を使い、スコア 0 のヒットを落とさない。** 0 のヒットを残しても順位付けの情報が
  無いので、上位 k 件を選ぶ意味が失われる。負のスコアの扱いも別途決める必要がある。
- **IDF の下限を 0 でクリップする。** 半数以上に出る語がすべて同じスコアになり、識別力を失う。

#### 影響

- `pyproject.toml` から `rank_bm25` の optional dependency を削除
- `LENGTH_NORM_B` と IDF 式は**実装内の単一定数**とし、呼び出しごとに組み立てない。変更するときは
  [search-quality-evaluation.md](search-quality-evaluation.md) の回帰計測を伴う

### #1-2: 索引キーを基準ディレクトリ相対にし、基準を記録する (2026-08-24) — 採用

#### コンテキスト

キーの生成に `Path.relative_to` を使っていたため、`--root` に作業ディレクトリ外の絶対パスを渡すと
未捕捉の `ValueError` でトレースバックになった。`--root ~/Documents` は最も自然な使い方で、確実に踏む。

一方で絶対パスをキーにすると、`path` は全ヒットに載るので Context Window を直接消費する。これは
このツールの目的そのものと衝突する。

#### 決定

**キーは基準ディレクトリからの相対パス**（`os.path.relpath`。`..` を含みうる）とし、**基準を
`meta.base_dir` に記録して書き込み時に照合**する。不一致は拒否する。読み取りは照合しない。

#### 理由

- **短いキーは Context Window の予算に直接効く。** 1 ヒットあたり数十文字の差が、返せるヒット数を変える。
- **相対キーは基準に依存し、基準はキーからは復元できない。** 別の作業ディレクトリから同じ索引へ
  書き込むと、全キーが新しい基準で再解釈され、同一ファイルの二重登録と**生存エントリの prune** が起きる。
  記録して照合すれば fail-closed にできる。
- **読み取りまで拒否すると、索引を作った場所でしか読めなくなる。** 読み取りはキーを返すだけなので、
  不一致は表示上の問題にとどまる。書き込みと読み取りで非対称にするのが妥当。

#### 却下した代替案

- **絶対パスをキーにする。** 曖昧さは消えるが、応答トークンが増える。目的と衝突する。
- **基準を記録せず現状維持。** 実際にデータ喪失が起きる経路がある。
- **基準を DB ファイルの位置から導出する。** `--db` は任意の場所を指定できるので、`--db` と `--root` の
  関係を新たに制約することになり、かえって説明が増える。

#### 影響

- `store` に `meta` テーブルを追加、`SCHEMA_VERSION` を 2 へ
- 基準の記録は**最初の実書き込み時**に行う。実行開始時に記録すると、`index --root typo` を誤った
  ディレクトリで 1 回叩くだけで空の索引がそこに固定され、以後の正しい実行が全拒否される
- 基準が記録されていないがエントリがある索引（この変更より前に作られたもの）は**採用せず再構築を求める**。
  最初に走った作業ディレクトリへ暗黙に固定すると、防ごうとしたキー再解釈がその 1 回で起きる

### #1-3: prune は「走査で見つからない」ではなく「ディスク上に無い」で判断する (2026-08-24) — 採用

#### コンテキスト

prune は当初「今回の走査で見つからなかったエントリ」を削除していた。2 つの事故が出た。

1. `index --root docs` の後に `index --root manuals` を実行すると、**ディスク上に存在する** `docs/`
   配下の索引が全消えする（再現確認済み）
2. 走査が取りこぼしただけのファイルも「消えた」と判定される。`Path.rglob` は読めないサブディレクトリを
   例外も出さずスキップするので、権限の問題が削除として現れる

#### 決定

prune の対象を **(1) 今回スキャンした root 配下にあり、かつ (2) ディスク上に無いことを確認できた**
エントリに限る。存在確認は `os.stat` で 3 値（確かに無い / ある / **判定不能**）に分け、判定不能は
削除せず warning にする。

#### 理由

- **「見つからなかった」は「無い」の証拠にならない。** 走査が短く終わる理由は削除以外にいくつもある
  （権限、マウント、競合）。安い推定で不可逆な削除をしてはいけない。
- **`Path.exists` も `os.path.exists` も使えない。** 前者は `PermissionError` を送出して実行結果を
  丸ごと失わせ、後者は例外を握り潰して `False` を返す＝生存ファイルを削除する。3 値が要る。
- **`os.lstat` ではなく `os.stat`。** ターゲットを失った symlink は「無い」側に倒れるべきで、
  `lstat` はリンク自身を見るので「ある」と答えてしまい、削除済みファイルの本文が索引に残り続ける。

#### 却下した代替案

- **走査 0 件の root 配下は prune を丸ごとスキップする。** アンマウントされたマウントポイントを
  想定した案。しかしアンマウントと「全ファイル削除」はディスク上で区別できず、スキップすると prune
  本来の用途（空になった root）が壊れる。実装して既存テスト 3 件が落ちたことで確認した。
  代わりに、root 全体が prune 対象になったことを warning で可視化する。
- **`--no-prune` を既定にする。** 索引が単調増加し、削除したファイルの内容が返り続ける。

#### 影響

- `IndexStats` に `warnings` を追加し、終了コードは `errors` だけで決める
- 判定不能なエントリは索引に残るので、検索結果が古い可能性がある。SKILL.md にその旨を書く

### #1-4: スキーマバージョン不一致は reject + 手動再構築とする (2026-08-31) — 採用

#### コンテキスト

REQ-D19-016 は「索引スキーマはバージョンを持ち、既存索引のバージョン不一致を検出して再構築を
要求する」と定めていたが、実装が無かった（Tentative / 未実装）。バージョンは `PRAGMA user_version`
に記録していたが、既存索引の照合ロジックが欠落していた。

#### 決定

`open_store()` で `PRAGMA user_version` を DDL 適用前に検査し、0（新規）でも
`SCHEMA_VERSION` でもなければ `SchemaMismatch` 例外を送出する。自動マイグレーションは行わず、
ユーザーに索引ファイルの削除と `docq index` の再実行を案内する。

#### 理由

- **自動マイグレーションは、マイグレーションロジック自体のテストが必要になる。** 現時点で
  スキーマ変更は 1 回（v1→v2: meta テーブル追加）しかなく、マイグレーション基盤を整える
  利得がない。索引は `docq index` で再構築できるので、削除で済む。
- **DDL 適用前に検査する。** `executescript` は暗黙の commit を行うため、検査後に DDL を
  適用しないと、不一致の DB にスキーマ変更が永続化される。

#### 却下した代替案

- **自動マイグレーション。** 利得に対してテストと実装のコストが見合わない。スキーマ変更が
  頻繁になったら再検討する。
- **警告のみで続行。** fail-open になる。古いスキーマの索引を新しいコードで読み書きすると
  暗黙の不整合が起きる。

#### 影響

- REQ-D19-016 を Confirmed に昇格
- CLI の `main()` で `SchemaMismatch` を catch し、JSON エラーと rc=1 で報告
- DDL 適用順序を「バージョン検査 → DDL → バージョン書き込み」に変更

### #1-5: scoring terms を索引時に永続化し検索時の再トークナイズを排除する (2026-09-02) — 採用

#### コンテキスト

検索のたびに `all_chunks()` で全チャンクの `text` をロードし、`scoring_terms()` で再トークナイズして
BM25 を一から構築していた。CLI は毎回新プロセスなのでキャッシュも効かず、コストがコーパスの全文字数に
比例していた（[#5](https://github.com/taito-station/doc-query/issues/5)）。

#### 決定

`chunks` テーブルに `scoring_terms TEXT NOT NULL DEFAULT ''` カラムを追加（スキーマ v2→v3）し、
インデクサが索引時に `scoring_terms(path + "\n" + text)` を計算して JSON 配列で保存する。検索の
BM25 パスは `text` を読まずに `scoring_terms` だけをロードしてスコアリングを完了し、snippet 生成が
必要な上位候補のみ `get_chunks_by_ids()` で `text` を後から取得する。

#### 理由

- **再トークナイズが支配的コスト。** NFKC 正規化 + 正規表現 + CJK バイグラム生成が全チャンクの全文字に
  対して毎回走る。terms の JSON デシリアライズはこれよりはるかに安い。
- **text の全量ロードも不要。** BM25 スコアリングに `text` は使わないので、排除すれば SQLite の
  オーバーフローページ読み出しを省ける。snippet 生成は上位候補だけで済む。
- **スキーマ変更は既存の reject + 手動再構築パスに乗る。** #1-4 の決定通り、バージョン不一致で
  `SchemaMismatch` を出し、ユーザーに再インデクスを案内する。

#### 却下した代替案

- **tf / df / IDF も永続化して BM25 構築自体をスキップする。** 効果は大きいがスキーマが複雑になり、
  チャンクの追加・削除のたびに全体の df / IDF を再計算して更新する必要がある。現時点では terms の
  永続化だけで十分な改善が得られる。
- **in-memory キャッシュ（sqlite3 の shared cache / mmap 等）。** CLI が毎回新プロセスを立てるため
  プロセス内キャッシュは効かない。プロセス間キャッシュはデーモンが必要になり、ローカル完結の
  シンプルさを損なう。

#### 影響

- `SCHEMA_VERSION` を 3 へ。既存索引は再構築が必要
- `indexer.py` が `tokenize.scoring_terms` に依存（スコアリング語の計算式は `search.py:_scoring_text`
  と同一であり、片方だけ変更すると索引と検索で乖離する）
- 5,000 チャンク超で `search()` が stderr に警告を出す

<!-- decision-log:end -->
