---
status: Confirmed
kind: knowledge
doc_class: [D01, D02]
tags: [D01, D02]
sources:
  - docs/original-docs/1-doc-flow-introduction.md
  - docs/qa/QA-doc-flow-introduction.md
distilled_from_sha: "7681fc1"
updated: "2026-08-24"
---

# 目的・成功条件・対象境界

## 目的

**LLM が文書を読むときの Context Window 消費を最小化する。**

LLM に文書の内容を渡す素朴な方法は、ファイル全体をコンテキストへ載せることである。これは (a) 大きい
文書 1 本で予算を使い切る (b) 複数文書の横断ができない (c) 答えと無関係な大半のテキストにコストを
払う、という 3 つの問題を同時に起こす。

doc-query は文書を索引し、**質問に関連する小さな snippet だけを返す**ことでこれを解く。

## 成功条件

実測（3 ページの日本語 PDF、`5f5f0a3` 時点）:

| | トークン数 | 全文比 |
|---|---:|---:|
| 全文をそのまま渡す | 10,566 | 100% |
| `docq search --top-k 3 --max-tokens 800` の応答 | 647〜790 | 6.1〜7.5% |

**92〜94% の削減**。移植元の `mdq` は Markdown で 99.8% を報告しているが、**同じ土俵の数字ではない**
——PDF はページ単位の固定窓チャンクで見出し構造を持てないぶん 1 ヒットが大きく、加えて上流の実測は
トークン計上が近似（`tiktoken` なしのフォールバック）で、こちらは `tiktoken` 実測である。
[search-quality-evaluation.md](search-quality-evaluation.md) が「カウンタが違う比較は無意味」
（REQ-D17-007）と定めているとおり、この 2 つを直接比べてはいけない。桁の目安として並べているだけ。

削減率そのものは目標値にしない。**応答トークン数を呼び出し側が予算として指定でき、その予算が守られる
こと**が満たすべき性質で、削減率はコーパスと質問に依存する結果でしかない。

## 対象境界（D02）

### 対象

- **テキストレイヤーを持つ文書**。現時点で対応しているのは PDF のみ
- **ローカル完結**。索引も検索も、外部 API・ネットワークアクセスを持たない
- **単独利用者**。索引はその人の作業ディレクトリに閉じる

### 非目標

- **OCR / スキャン画像 PDF**。テキストレイヤーが無い文書は抽出できない。これは実装の未完成ではなく
  意図的な線引きで、OCR を入れるとローカル完結（重い依存）と精度保証（誤認識の扱い）の両方が
  別の問題になる
- **クラウド / 埋め込みベースの意味検索**。BM25 による語彙照合に限定する。埋め込みは外部 API か
  重いローカルモデルを要求し、ローカル完結と衝突する
- **pptx / xlsx**。汎用の索引・検索コアはフォーマット非依存に作ってあり、抽出モジュールを足せば
  対応できる構造だが、**現時点では未実装**（[vendoring-and-upstream.md](vendoring-and-upstream.md)）
- **大規模コーパス**。検索のたびに全チャンクを読み直す実装なので、コストはコーパス全体に比例する
  （[#5](https://github.com/taito-station/doc-query/issues/5)）

## 要件

<!-- REQ:begin D01 -->
| REQ-ID | 要件 | 検証手段 | 出典 | status |
|---|---|---|---|---|
| REQ-D01-001 | 検索応答は 1 ヒット 1 行の JSON で返し、応答トークン数を呼び出し側が指定した予算に収める。予算を超える場合も先頭 1 件は必ず返す（0 件を返すと呼び出し側が索引の有無と一致の有無を区別できない） | `tests/test_search.py::test_search_respects_max_tokens_budget` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D01-002 | 索引・検索のいずれも外部 API・ネットワークへアクセスしない | 未整備 | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Tentative |
| REQ-D01-003 | 索引対象はテキストレイヤーを持つ文書のみとする。スキャン画像の OCR は非目標で、テキストの取れないページは索引に載せない | `tests/test_extractor.py::test_extract_pages_blank_page_yields_empty_string` / `tests/test_indexer.py::test_index_one_file_skips_blank_pages` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D01-004 | 実物の文書ファイルをリポジトリへコミットしない。評価コーパスは生成元テキストのみをコミットし、文書そのものは生成物として扱う | `scripts/check-no-pdf-committed.py`（CI の `docs` ジョブと pre-push） | [QA-doc-flow-introduction.md](../qa/QA-doc-flow-introduction.md) | Confirmed |
<!-- REQ:end D01 -->

**REQ-D01-002 が Tentative なのは、実装は満たしているが測る手段が無いため。** 検証手段の無い要件を
Confirmed にしないのは [README.md](README.md) の規約で、「達成した」と言えるのは測り方が決まっている
ときだけ、という線を引くためにある。後続 PR で検証手段を与えて Confirmed へ上げる。

REQ-D01-004 は `scripts/check-no-pdf-committed.py` が入った時点で Confirmed へ上げた——**Tentative は
恒久的な状態ではなく、測る手段を作れば解消する**という運用の実例。

---

<!-- decision-log:begin -->
## 決定ログ

<!-- この節は append-only です。既存エントリの変更・削除は CI が検出します。 -->

### #1-1: 削減率ではなく予算遵守を成功条件にする (2026-08-24) — 採用

#### コンテキスト

このツールの価値は「Context Window の消費を減らすこと」で、実測では 92〜94% の削減が出ている。
移植元の `mdq` は Markdown に対して 99.8% を報告しており、数字を目標値として掲げたくなる。

#### 決定

**削減率を目標値にしない。** 満たすべき性質は「応答トークン数を呼び出し側が予算として指定でき、
その予算が守られること」（REQ-D01-001）とする。

#### 理由

- **削減率はコーパスと質問に依存する結果でしかない。** 短い文書ばかりのコーパスでは削減率が下がるが、
  それはツールが劣化したのではない。目標にすると、改善したかどうかを判断できない指標を追うことになる。
- **予算遵守は実装の性質として測れる。** 与えた `--max-tokens` に対して応答が収まるかは、コーパスに
  依存せず検証できる。
- 検索の**品質**（正しいページを返せているか）は別軸で、[search-quality-evaluation.md](search-quality-evaluation.md)
  のゴールデンクエリ計測が担う。削減率だけを追うと、何も返さないのが最も「良い」ことになってしまう。

#### 却下した代替案

- **削減率 90% 以上を受入基準にする。** 上記のとおりコーパス依存。しかも達成は自明（`--max-tokens` を
  小さくすればいくらでも下がる）なので、基準として機能しない。
- **mdq の 99.8% と直接比較する。** PDF はページ単位の固定窓で見出し構造を持てず、1 ヒットが構造的に
  大きい。同じ土俵ではない。

#### 影響

- README の記述を「削減率の実測値」として提示し、目標値としては書かない
- 検索品質の受入基準は D17 側（ゴールデンクエリの top-1 / top-k / MRR@k）に置く

<!-- decision-log:end -->
