# 一次資料: 全角英数がスコアリング語彙から落ちる欠陥の観測

## 発端の Issue

原本は [#2](https://github.com/taito-station/doc-query/issues/2)（転記しない）。
本文は `gh issue view 2` で取得する。

## 観測の経緯

手元の実 PDF（日本語の入場券販売概要、3 ページ）を索引して検索し、抽出品質とトークン削減率を
確かめていたときに発覚した。**PDF そのものはリポジトリに置かない**（REQ-D01-004）ので、ここには
観測結果と再現手順だけを残す。

最初の兆候は「指定席Ａ 料金」で検索したときに、料金表そのものではなく見出し部分の snippet が
返ったことだった。同じチャンクを「オレンジシート」で引くと料金表が返ったため、チャンクの選択では
なく語彙の側を疑った。

## `scoring_terms` の実測出力

```
>>> from docq.tokenize import scoring_terms
>>> scoring_terms('指定席Ａ')
['指定', '定席']
>>> scoring_terms('指定席Ｓ')
['指定', '定席']
>>> scoring_terms('指定席Ｂ')
['指定', '定席']
>>> scoring_terms('カテゴリⅠ')
['カテ', 'テゴ', 'ゴリ']
>>> scoring_terms('０５０－３０６６－９６９０')
[]
>>> scoring_terms('オレンジシート')
['オレ', 'レン', 'ンジ', 'ジシ', 'シー', 'ート']
>>> scoring_terms('GIANTS')
['giants']
```

**全角英数（Ａ-Ｚ / ０-９）・ローマ数字（Ⅰ Ⅱ）・全角記号（－）が、どの文字クラスにも属さず
セグメント分割の時点で脱落している。** ASCII と CJK（ひらがな・カタカナ・CJK 統合漢字）は正しく
拾えている。

## 検索での実害

3 席種はそれぞれ別の料金を持つが、クエリとしては完全に同一になる。

```
$ docq search --q "指定席Ａ" --top-k 2 --max-tokens 400
{"chunk_id": "2a9176...", "location": "p.1", "score": 6.7795, ...}
$ docq search --q "指定席Ｓ" --top-k 2 --max-tokens 400
{"chunk_id": "2a9176...", "location": "p.1", "score": 6.7795, ...}
$ docq search --q "指定席Ｂ" --top-k 2 --max-tokens 400
{"chunk_id": "2a9176...", "location": "p.1", "score": 6.7795, ...}
```

**スコアまで完全に一致している。** 席種を指定した質問には答えられない。

## フォールバックが効く場合と効かない場合

`search.py` には `if mode == "grep" or not q_tokens:` の分岐があり、クエリからトークンが 1 つも
取れないときは grep 経路へ落ちる。

**全角のみのクエリは偶然これに救われる。**

```
$ docq search --q "０５０－３０６６－９６９０" --top-k 2
{"chunk_id": "0f9814...", "location": "p.3", "score": 1.0,
 "snippet": "...【電話】 グランドスラム・ゴールドメンバー専用 ０５０－３０６６－９６９０"}
```

スコア 1.0 は grep のマッチ件数であって BM25 のスコアではない。

**和字が混ざるとフォールバックが効かない。** `指定席Ａ` は `['指定', '定席']` が残るので `q_tokens` が
非空になり、BM25 経路に入って静かに精度だけ落ちる。**こちらが実害の中心。**

## snippet 側にも同じ穴がある

`search.py` の `_TOKEN_RE`（snippet の中心行を選ぶためのトークナイザ）は、`tokenize.py` の
`CJK_CHAR_RANGES` を参照しつつ文字クラスを**独立に組み立てている**。つまり同じ欠陥が 2 箇所にあり、
片方だけ直すことが構造的に可能になっている。

## 上流 mdq にも同じ欠陥がある

```
$ python -c "import sys; sys.path.insert(0,'.'); from mdq.tokenize import scoring_terms; \
             print(scoring_terms('指定席Ａ'), scoring_terms('指定席Ｓ'))"
['指定', '定席'] ['指定', '定席']
```

（`~/workspace/HypervelocityEngineering` で実行）

**移植時に持ち込んだバグではなく、vendor 元から継承したもの。**

上流で検出されていない理由を、ゴールデンクエリ集を集計して確かめた。

```
mdq/golden-queries.json:         全40件 / 日本語 20件 / 全角英数記号 0件
mdq/golden-queries-holdout.json: 全20件 / 日本語 19件 / 全角英数記号 0件
```

**日本語が足りないのではなく、全角英数を含むクエリが 1 件も無い。** 日本語クエリの実例:

```
"APP-009 推薦アーキテクチャ Webフロントエンド クラウド"
"SVC-03 リワード管理サービス"
"サービス × データストア 所有権 マトリクス"
```

型番や ID を含むものもあるが、いずれも半角。**「日本語を入れたから大丈夫」では、この欠陥は捉えられ
なかった。**

## 既存テストが素通りした理由

MVP 時点のテスト 18 件はすべて PASS していた。テスト用の合成 PDF が**半角英数のみ**で構成されており、
全角を含むケースが 1 件も無かったため。

## 再現手順

実 PDF は不要。次で足りる。

```python
from docq.tokenize import scoring_terms
assert scoring_terms('指定席Ａ') == scoring_terms('指定席Ｓ')   # 現状は成立してしまう
```

## 環境

- Python 3.13.12（pyenv）、macOS
- doc-query `5f5f0a3` 時点
