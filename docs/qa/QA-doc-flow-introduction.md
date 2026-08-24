# QA: 開発フロー導入の論点（#1）

`docs/original-docs/1-doc-flow-introduction.md` と `2-fullwidth-scoring-defect.md` を読み、
HVE 由来の開発フローを doc-query へ導入するにあたって判断が要る点を質問票にした。回答は 2026-08-23〜24
に確定。

---

## Q1. 取り込む範囲をどこまでにするか

**背景**: HVE のフル機能は Issue Template 駆動 → GitHub Actions → Prompt DAG → 成果物という
オーケストレータまで含む大規模なもの。`paddock` と `baseball-ticket` はいずれも一部だけを抜き出して
規模に読み替えている。doc-query は約 1,000 行（paddock は約 61,000 行）。

**選択肢**:
- (a) 中核 3 点のみ（REQ 表 / 決定ログ / ゴールデンクエリ計測）。D クラス体系と 2 層蒸留は入れない
- (b) paddock 準拠フル（2 層蒸留 + D クラス体系 + frontmatter + REQ-ID + 決定ログ）
- (c) 評価系のみ先行（ゴールデンクエリ計測と決定ログだけ）

**回答: (b) paddock 準拠フル。**

**根拠**: 既に 2 リポジトリで同じモデルを運用しており、規約を揃えることの利得が大きい。規模の差は
「何を削るか」で吸収する（`docs/knowledge/README.md` の「paddock から意図的に削ったもの」）。

---

## Q2. 機械検査をどこで走らせるか

**背景**: paddock は GitHub Actions、baseball-ticket はローカル bash 1 本。

**選択肢**: (a) Actions + pre-push の両方 / (b) ローカルスクリプトのみ / (c) 当面なし

**回答: (a) Actions + pre-push の両方。**

**根拠**: `docs/knowledge/ci-and-checks.md` の決定ログ `#1` に記載。baseball-ticket が CI を持たない
のは文書専用リポジトリだからで、コードと文書が同居する doc-query には当てはまらない。

---

## Q3. 評価コーパスをどう用意するか

**背景**: ゴールデンクエリ計測には検索対象の文書群が要るが、**実物の PDF はコミットできない**
（利用者の手元にある文書は PII を含みうる）。

**選択肢**:
- (a) `reportlab` で合成 PDF を生成し、生成元テキストのみコミットする
- (b) 抽出後のテキストを直接 fixture にし、抽出工程を飛ばして検索層だけ評価する
- (c) ライセンス上問題のない公開 PDF を同梱する

**回答: (a) 合成 PDF を生成する。**

**根拠**: (b) は抽出 → チャンク化の回帰を検出できず、「評価集の外に欠陥が残る」構図を自分で作る
ことになる（#2 がまさにそれ）。(c) はバイナリを抱えるうえ、日本語の全角を含む適切な PDF を探す
コストがかかる。(a) なら**全角英数・ローマ数字・全角記号を意図的に含める**こともできる。

---

## Q4. doc-query 固有の文書クラス（D22 以降）を追加するか

**背景**: paddock は D22〜D24 を追加している。判定基準は「既存クラスへ押し込むと必須項目が総 UNKNOWN に
なるか」。doc-query で器が要るのは「索引・検索・ランキングの仕様」と「検索品質の評価」の 2 つ。

**回答: 追加しない。**

**根拠**: 前者は D08 + D19、後者は D17 に必須項目が全部埋まる形で収まる。詳細と再開条件は
`docs/knowledge/doc-classes.md` の決定ログ `#1`。

---

## Q5. D05（ユースケース）と D18（Prompt ガバナンス）をどう扱うか

**背景**: 実質を担っているのは `.claude/skills/pdf-query/SKILL.md`。USE FOR / WHEN / DO NOT USE は
ユースケース定義そのもので、Prompt ガバナンスの資産でもある。paddock は両方 active-0（恒久 warning）に
している。

**選択肢**: (a) n/a 宣言して SKILL.md を正本とする / (b) active にして docs へ蒸留する

**回答: (a) n/a 宣言する。**

**根拠**: docs 側へ写すと SKILL.md との二重管理を `sources` 追従で抱えることになり、文書 2 本を増やす
対価がそれに見合わない。加えて、文書 8 本の規模で active-0 の恒久 warning を置くと本物の充足ギャップが
そこに埋もれる。

---

## Q6. GitHub リポジトリを public / private どちらで作るか

**回答: public。**

**根拠**: MIT ライセンスで `NOTICE.md` も整っており公開に支障がない。Actions が無料枠無制限で使え、
上流 mdq への欠陥還元もリンクで済む。

---

## 未解決のまま残した論点

- **上流 mdq へ #2 を還元するか。** doc-query 側の修正が固まってから判断する
  （`docs/knowledge/vendoring-and-upstream.md`）。
- **pptx / xlsx 対応の着手時期。** 汎用層の切り分けは済んでいるが、`indexer.py` は現状 PDF 専用で、
  拡張子ディスパッチの設計は未着手。実際に必要になるまで先送りする。
- **`stats` に最終索引時刻を持たせるか。** SKILL.md は「`stats` で索引が古いか確認する」と書いているが、
  `stats` が返すのは件数だけで鮮度は判定できない。記述と実装のどちらを直すか未決。
