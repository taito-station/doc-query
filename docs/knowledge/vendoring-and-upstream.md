---
status: Confirmed
kind: knowledge
doc_class: [D09]
tags: [D09]
sources:
  - NOTICE.md
  - docs/original-docs/1-doc-flow-introduction.md
  - docs/original-docs/2-fullwidth-scoring-defect.md
distilled_from_sha: "3e83512"
updated: "2026-08-24"
---

# vendor 元と責任境界

## 何をどこから取ったか

doc-query は [HVE](https://github.com/dahatake/HypervelocityEngineering)（MIT）の `mdq`
（markdown-query）を PDF 向けに移植したものである。帰属表記は `NOTICE.md` が正本。

| ファイル | 由来 | 改変の程度 |
|---|---|---|
| `docq/tokenize.py` | mdq の `scoring_terms`（CJK bigram） | ほぼそのまま |
| `docq/tokens.py` | mdq のトークン計上 | ほぼそのまま |
| `docq/store.py` | mdq の `store.py` | **簡素化して移植**。FTS5 ミラー・embeddings・pageindex・tags を削除。`meta` テーブルは doc-query で追加 |
| `docq/search.py` | mdq の `search.py` | **簡素化して移植**。embeddings 融合・pageindex ツリー・親/近傍/分割片の展開を削除。BM25 は自前実装に差し替え |
| `docq/extractor_pdf.py` | — | 新規 |
| `docq/indexer.py` | — | 新規（チャンク化の既定値のみ mdq と同一） |
| `docq/cli.py` | mdq の CLI 体系 | サブコマンド名を踏襲 |

**フォーマット非依存層（store / search / tokenize / tokens）を vendor し、フォーマット固有部分
（extractor / indexer）だけを新規実装する**という切り分けになっている。pptx / xlsx へ広げるときも、
この境界は変わらない想定である。

## 責任境界（D09）

- **doc-query は外部システムと連携しない。** ネットワークアクセスを持たず、呼び出し側との境界は
  CLI の JSON 出力だけ（[index-and-search.md](index-and-search.md) の D10 節）。
- **索引の内容に対する責任は利用者にある。** 索引対象は利用者が `--root` で指定したファイルに限られ、
  ツールが勝手に探索範囲を広げることはない。
- **上流 mdq に対して追従義務を負わない。** vendor であってサブモジュールではないので、mdq の更新が
  自動で入ることはない。取り込むかどうかは都度の判断になる。

## ライセンス

MIT（HVE 由来）を継承する。`NOTICE.md` に vendor 元を明記している。

**PDF 抽出に `pdfplumber`（MIT）を採用し、`PyMuPDF` を避けたのはライセンス上の判断である。**
PyMuPDF は AGPL で、公開・配布の可能性を考えると採れない。

## 上流に同じ欠陥がある

[#2](https://github.com/taito-station/doc-query/issues/2)（全角英数・ローマ数字がスコアリング語彙から
落ちる）は**移植時に持ち込んだバグではなく、vendor 元から継承したものである**。

```
mdq.tokenize.scoring_terms('指定席Ａ') -> ['指定', '定席']   # doc-query と同一の出力
```

上流で検出されていない理由は、mdq のゴールデンクエリに**全角英数を含むクエリが 1 件も無い**ため
（日本語クエリ自体は開発用 40 件中 20 件、ホールドアウト 20 件中 19 件と十分にある）。
**評価集がカバーしない領域には欠陥が残り続ける**ことの実例になっており、
[search-quality-evaluation.md](search-quality-evaluation.md) を導入する根拠のひとつでもある。

**還元するかどうかは未決。** doc-query 側の修正が固まってから判断する
（[#2](https://github.com/taito-station/doc-query/issues/2)）。

---

<!-- decision-log:begin -->
## 決定ログ

<!-- この節は append-only です。既存エントリの変更・削除は CI が検出します。 -->

### #1-1: 汎用層を vendor し、フォーマット固有部分だけを実装する (2026-08-24) — 採用

#### コンテキスト

`mdq` は Markdown 向けの索引・検索ツールで、BM25 ランキング・トークン予算・snippet 返却という中核部分は
フォーマットに依存しない。PDF 向けに同じ仕組みが要るとき、取りうる形は複数あった。

#### 決定

**汎用層（store / search / tokenize / tokens）をコードごと vendor し、フォーマット固有部分
（extractor / indexer）だけを新規実装する。** ライセンス（MIT）を継承し `NOTICE.md` に明記する。

#### 理由

- **中核の設計判断（トークン予算・snippet 返却・CJK bigram）に実績がある。** 書き直す理由が無い。
- **PDF 固有の部分は本当に固有。** ページという単位も、テキストレイヤーの有無という問題も Markdown には
  無い。ここを共有しようとすると、どちらのフォーマットにも合わない抽象になる。
- **サブモジュールにしない**のは、簡素化して移植したかったため。mdq の FTS5 ミラー・embeddings・
  pageindex は doc-query では使わず、そのまま抱えると読む量と壊れる面が無用に増える。

#### 却下した代替案

- **mdq をそのまま依存として使い、PDF を Markdown に変換して食わせる。** 変換の忠実性が新たな問題に
  なり、ページ番号という所在情報も失われる。
- **フォーマットごとに別リポジトリを作る**（`pdf-query` / `pptx-query` …）。汎用層の vendor が
  リポジトリ数だけ重複する。PDF / PPTX / XLSX はどれも「テキストを抽出してチャンク化する」同じ
  パターンに収まるので、1 つのリポジトリにフォーマット別の extractor を足す形にした
  （これが `pdf-query` → `doc-query` のリネームの理由）。
- **サブモジュールで mdq を取り込む。** 上流の更新に追従できる代わりに、使わない機能を抱え続ける。
  vendor + NOTICE のほうが読む量が少ない。

#### 影響

- `NOTICE.md` に vendor 元と改変点を記載
- 上流の更新は自動で入らない。取り込むかどうかは都度判断する
- **上流に存在する欠陥も継承する。** 実際に #2 がそれにあたる

### #1-2: PDF 抽出に pdfplumber を採用する (2026-08-24) — 採用

#### コンテキスト

PDF からテキストを抽出するライブラリは複数あり、抽出品質・速度・ライセンスが異なる。doc-query は
MIT で公開する前提なので、依存のライセンスが配布可能性を直接左右する。

#### 決定

**`pdfplumber`（MIT）を採用する。**

#### 理由

- **`PyMuPDF` は AGPL。** 抽出品質と速度では最有力だが、AGPL の伝播条件は「MIT で公開する」という
  前提と両立しない。商用ライセンスは個人プロジェクトの規模に見合わない。
- **必要なのはページ単位のプレーンテキストだけ。** レイアウト解析・表抽出・座標情報は使っていないので、
  抽出器に求める性能の幅が狭い。ライセンスを最優先して選べる。
- `pdfplumber` は `pdfminer.six` の上に立っており、日本語のテキストレイヤーを実 PDF で問題なく
  抽出できることを確認した。

#### 却下した代替案

- **`PyMuPDF`（AGPL）**。上記のとおりライセンスで却下。
- **`pdfminer.six` を直接使う。** `pdfplumber` の依存そのもので、ライセンス（MIT）も問題ない。ページ
  単位の `extract_text()` を自前で組む手間が増えるだけなので、薄いラッパである `pdfplumber` を採った。
- **`pypdf`**。純 Python で軽いが、テキスト抽出の品質——特に日本語の CID フォント——が
  `pdfminer` 系に劣る。索引の入力が劣化すると検索品質が上限で頭打ちになる。
- **外部コマンド（`pdftotext`）に委ねる。** 抽出品質は高いが、Python 以外の実行時依存が増え、
  「`pip install` で完結する」性質を失う。

#### 影響

- `pyproject.toml` の必須依存は `pdfplumber` 1 本
- **抽出器を差し替えるときはライセンスを先に確認する。** この判断は品質ではなくライセンスで決まって
  いるので、「もっと良い抽出器がある」だけでは覆らない
- 大きい PDF でのメモリ挙動（`pdfplumber` はページごとの解析結果をキャッシュする）は未計測

<!-- decision-log:end -->
