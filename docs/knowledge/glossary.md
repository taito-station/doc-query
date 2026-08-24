---
status: Confirmed
kind: knowledge
doc_class: [D07]
tags: [D07]
sources:
  - docs/original-docs/2-fullwidth-scoring-defect.md
distilled_from_sha: "5f5f0a3"
updated: "2026-08-24"
---

# 用語集

定義の正本がどこにあるかを引くための索引。**同じ語が別の意味で使われている箇所を先に固定する**のが
この文書の主目的で、[#2](https://github.com/taito-station/doc-query/issues/2) の欠陥が「2 つの
トークナイザの取り違え」から生まれたことが直接の動機になっている。

## トークンをめぐる 3 つの別物

| 用語 | 意味 | 実装 |
|---|---|---|
| **scoring term**（スコアリング語） | BM25 のランキングが照合する単位。CJK は隣接 bigram、ASCII 英数は分割しない | `docq/tokenize.py` の `scoring_terms()` |
| **snippet token** | 返す snippet の中心行を選ぶために使う、より粗い分割。ランキングには使わない | `docq/search.py` の `tokenize()` |
| **token**（トークン数） | LLM のコンテキスト消費量。応答予算の単位 | `docq/tokens.py` の `count_tokens()` |

**3 つは互いに無関係。** `tokenize.py` と `tokens.py` は名前がほぼ同じだが責務は「語の分割」と
「消費量の計上」で別物である。

**scoring term と snippet token を混同すると #2 の欠陥が再発する。** 両者は現在それぞれ独立に文字
クラスを定義しており、片方だけ直すことが構造的に可能になっている（REQ-D19-010 が塞ぐ対象）。

## 索引の構造

| 用語 | 意味 |
|---|---|
| **chunk** | 索引と検索の最小単位。1 ページを固定窓で分割した本文の断片 |
| **location** | チャンクの所在を人間可読に表した文字列。現在は `p.3` の形 |
| **base directory**（基準ディレクトリ） | 索引キーの相対パスが基準とするディレクトリ。`meta.base_dir` に記録される。**リポジトリルートではない**（コード内の変数名 `repo_root` は歴史的経緯） |
| **prune** | ディスクから消えた文書のエントリを索引から削除すること。「走査で見つからなかった」ことは根拠にしない |

## 検索の応答

| 用語 | 意味 |
|---|---|
| **return unit**（返却単位） | 1 ヒットで何を返すか。`line`（既定・snippet）/ `chunk`（本文全体）/ `locations`（本文なし） |
| **token budget**（トークン予算） | `--max-tokens`。1 ヒット 1 行の JSON 全体のトークン数で判定する。超過しても先頭 1 件は返す |
| **grep モード** | BM25 を使わず、クエリを literal として本文に照合するモード。スコアリング規約の対象外 |
| **フォールバック** | クエリからスコアリング語が 1 つも得られないときに grep 経路へ落ちること。**利用者が意図して選ぶ grep モードとは別物** |

## 状態を表す語

`errors` と `warnings` は `index` の出力で意味が違う（[index-and-search.md](index-and-search.md)）。

| 用語 | 意味 | 終了コード |
|---|---|---|
| **error** | 要求どおりに実行できなかった。ただし成功した分は索引に反映されている | 1 |
| **warning** | 実行は成立したが知っておくべきこと。自然に解消しない条件を含む | 影響しない |

文書側の `status`（`Confirmed` / `Tentative` / `Conflict` / `Retired`）は
[README.md](README.md) が正本。
