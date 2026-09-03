# テーブル構造の抽出改善調査 (Issue #22)

調査日: 2026-09-03

## 調査目的

pdfplumber は `extract_tables()` を持つが、現状 `extract_text()` のみ使用している。
罫線付きテーブルを含む PDF でセル構造が潰れて検索精度が落ちている可能性を調査する。

## 実験方法

1. 既存 eval コーパス 5 PDF に `extract_tables()` を適用
2. reportlab の `Table` クラスで罫線付き料金表 PDF を合成（ticket-prices と同じデータ）
3. 同じデータを `drawString()` で描画した PDF と比較
4. `extract_text()` / `extract_tables()` の出力、トークナイズ結果、検索スコアを比較

## 実験結果

### 1. 既存コーパスのテーブル検出

```
categories.pdf:     2 pages, 0 tables detected
common-terms.pdf:   2 pages, 0 tables detected
contact-info.pdf:   1 pages, 0 tables detected
product-catalog.pdf:2 pages, 0 tables detected
ticket-prices.pdf:  3 pages, 0 tables detected
```

全 PDF でテーブル検出 0 件。drawString で描画されたプレーンテキストのため。

### 2. extract_text() の出力比較

テーブル PDF（罫線付き Table オブジェクト）:
```
席種 大人 小児
指定席Ａ ￥５，４００ ￥２，７００
指定席Ｓ ￥７，２００ ￥３，６００
指定席Ｂ ￥３，６００ ￥１，８００
```

drawString PDF（プレーンテキスト行）:
```
席種 大人 小児
指定席Ａ ￥５，４００ ￥２，７００
指定席Ｓ ￥７，２００ ￥３，６００
指定席Ｂ ￥３，６００ ￥１，８００
```

**`extract_text()` の出力は同一。** pdfplumber はテーブルの有無に関わらず
テキストを正しく行単位で抽出する。

### 3. extract_tables() の出力

テーブル PDF:
```
1 table(s)
  Table 0:
    ['席種', '大人', '小児']
    ['指定席Ａ', '￥５，４００', '￥２，７００']
    ['指定席Ｓ', '￥７，２００', '￥３，６００']
    ['指定席Ｂ', '￥３，６００', '￥１，８００']
```

drawString PDF:
```
0 table(s)
```

`extract_tables()` は罫線付き Table のみ検出する。drawString テキストは検出対象外。

### 4. トークナイズ結果

テーブル PDF: 27 terms（ファイル名部分 `table`, `prices` を除き一致）
drawString PDF: 27 terms（ファイル名部分 `drawstring`, `prices` を除き一致）

scoring terms は同一。

### 5. 検索スコア比較

| クエリ | テーブル PDF | drawString PDF |
|---|---|---|
| 指定席Ａ 料金 | 1.2466 | 1.2466 |
| 小児 料金 | 0.2877 | 0.2877 |
| 指定席Ｓ 大人 | 1.5343 | 1.5343 |

**全クエリで完全に同一スコア。**

## 結論

- `extract_text()` は罫線付きテーブルでもプレーンテキストでも同一のテキストを抽出する
- テーブル構造の有無は BM25 スコアリングに影響しない
- `extract_tables()` の導入は現時点で不要
- 将来、複雑なマルチカラムレイアウトや結合セルを含む PDF が対象になった場合に再検討する
