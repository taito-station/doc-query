# knowledge — 蒸留済み確定知の規約

[dahatake/HypervelocityEngineering](https://github.com/dahatake/HypervelocityEngineering)（HVE, MIT）の
original-docs → qa → knowledge 蒸留モデルを doc-query に導入したもの。**蒸留は Claude Code が担う**
（HVE 本体の LLM オーケストレータは持ち込まない）。同じモデルを先に導入した
[taito-station/paddock](https://github.com/taito-station/paddock) の規約を、doc-query の規模に読み替えている。

## 2 層モデル

```
docs/original-docs/  読み取り専用の一次資料（実測ログ・調査所見・issue 由来の生素材）
        │
        │ [Claude が読取・欠落/不整合を検出]
        ▼
docs/qa/             質問票 + 回答
        │  [Claude が差分マージ]
        ▼
docs/knowledge/      status 付き確定知（＝この層。読むのはここ）
                     末尾に **決定ログ**（append-only の決定記録）を持つ
```

- **確定知を読む入口は knowledge**。決定を辿るのも同じファイルの末尾で完結する。
- **一次資料層に残るのは転記できないもの**——実測ログ・調査時点のコード所見・外部ツールの挙動観察。
  ファイル名は **GitHub issue 番号（0 埋めしない）**（`1-`, `2-` …）。
  **GitHub Issue 本文は転記しない**——原本は Issue とし、リンクと `gh issue view <N>` の 1 行を置く。
  転記は原本として機能しないうえ、GitHub 側の編集は git に現れないので同期切れを機械検査できない。
- **paddock と違って `docs/specifications/` を作らない。** paddock は既存の仕様書群を昇格させた歴史的
  経緯で 2 ディレクトリを持つが、doc-query は最初から knowledge 1 層で足りる。ディレクトリを増やさない。

## 決定ログの書き方

`docs/knowledge/` の各文書は、本文の末尾に `## 決定ログ` 節を持てる。

```markdown
---

## 決定ログ

<!-- この節は append-only です。既存エントリの変更・削除は CI が検出します。 -->

### #1: 2 層蒸留と D 体系の採用 (2026-08-24) — 採用

#### コンテキスト
#### 決定
#### 理由
#### 却下した代替案
#### 影響
```

- **見出しは `### #NNN: 要約 (YYYY-MM-DD) — ステータス`**（`NNN` は GitHub issue 番号）。
  **独立した ADR ファイルは作らない。**
- **append-only**。既存エントリの本文を書き換えない・消さない（**CI が検出する**）。決定を変えるときは
  **新しいエントリを追記して、旧エントリを supersede した旨を新エントリに書く**。
- **どの文書に書くか**は「その決定が効く確定知」で決める。**読む人が辿り着く場所**に置く。
  複数文書にまたがる決定は、主たる文書 1 本に書いて他からは相対リンクで指す（写しを増やさない）。
- **本文の規約（この節より上）と決定ログは別物**。本文は「今どうなっているか」を常に最新へ差分マージし、
  決定ログは「いつ・なぜそう決めたか」を積むだけ。決定が覆ったら**本文を直し、決定ログには
  新エントリを積む**（過去エントリは訂正しない）。
- **エントリは書いた本人がその場で書き切る**（コンテキスト・決定・理由・却下した代替案・影響）。
  ここは機械検査が届かない範囲で、後から補完する機会は実質来ない。

## frontmatter 規約

```yaml
---
status: Confirmed        # Confirmed（確定）/ Tentative（暫定）/ Conflict（矛盾・要解消）
kind: knowledge
doc_class: [D19, D08]    # 文書クラス。第 1 要素が主クラス。定義は docs/knowledge/doc-classes.md
tags: [D19, D08]         # doc_class のミラー（完全一致。checker が強制）
sources:                 # 由来。qa / original-docs のほか、確定知層や主題そのものである
                         # ファイル（ci.yml 等）も可。判定は「その文書の本文が動いたら、
                         # この知の見直しが要るか」
  - docs/original-docs/N-....md    # issue 番号（0 埋めしない）
  - docs/qa/QA-....md
distilled_from_sha: "<short-sha>"  # この知が反映するリポジトリ状態の git SHA
updated: "YYYY-MM-DD"    # 内容を実質更新した日（YAML の date 型を避けるため必ずクォート）
---
```

> **注意**: `updated` は必ずダブルクォートで囲む。クォートしないと YAML が `date` 型に解釈する。

- **`doc_class` / `tags` はフロースタイル 1 行で書く。** checker を標準ライブラリのみで実装するため
  （`^doc_class:\s*\[…\]$` の 1 正規表現でパースできる）。`sources` はブロックスタイル。
- **`tags` へのミラーは検索のため。** `docq` は frontmatter を検索に使わないので、クラスで絞り込める
  ようにするには同値を `tags` に置く必要がある。二重管理の drift は checker が防ぐ。
- **status**: `Confirmed`=検証済みで運用の前提にしてよい / `Tentative`=検証中・暫定 /
  `Conflict`=source 間で矛盾があり要解消（放置しない）。
- **参照 SHA**: この知を蒸留した時点のリポジトリ HEAD を `git rev-parse --short HEAD` で記録する。
  `sources` に挙げたファイルを**内容ごと**変更する PR は、参照元の `distilled_from_sha` を同じ PR で
  現 HEAD へ更新する（**stale は機械検査の対象**）。
  **同一コミットに自分の sha は書けない**ので、上流を触った PR は「本文コミット → sha 追従コミット」の
  2 コミットになる。
- **変更履歴は git log を正とする。** 本文末尾に `## 変更履歴` 節は置かない。

## REQ-ID（要件 ID）の規約

要件・成功条件に**安定した参照子**を与える。決定ログ・issue・PR から `REQ-D19-006` の 1 語で名指しでき、
文書を書き換えても参照が壊れない。

```markdown
<!-- REQ:begin D01 -->
| REQ-ID | 要件 | 検証手段 | 出典 | status |
|---|---|---|---|---|
| REQ-D01-001 | 検索応答は 1 ヒット 1 行の JSON で返す | `tests/test_search.py::test_x` | [#1](https://github.com/taito-station/doc-query/issues/1) | Confirmed |
<!-- REQ:end D01 -->
```

- **形式は `REQ-D{NN}-{NNN}`**。`D{NN}` は [doc-classes.md](doc-classes.md) の文書クラス、`{NNN}` は
  3 桁ゼロ埋めの連番。クラスは**その要件を載せている文書のクラス＝番号空間の持ち主**を表す
  （関心事の分類ではない）。
- **一意性はクラス内グローバル**。同じ `D{NN}` の番号はリポジトリ全体で 1 つ。
- **番号は再利用しない**。廃止した要件は行を消さず `status: Retired` にして残す。消して番号を空けると、
  過去の決定ログ / issue が指す ID が別の要件を指すようになる。
- **マーカーで囲む**。`<!-- REQ:begin D{NN} -->` … `<!-- REQ:end D{NN} -->`。表の位置を本文構造に
  依存させないため。マーカーのクラスは**その文書の `doc_class` に含まれていること**。
- **列は 5 列固定**（`REQ-ID | 要件 | 検証手段 | 出典 | status`）。**見出し行と区切り行も必須**で、
  順序も変えない。書式が崩れた行は黙って落とさず error にする（落とすと一意性検査から消えて重複が通る）。
  セル内にパイプを書くときは GFM どおり `\|` とエスケープする。
- **`status` は `Confirmed` / `Tentative` / `Conflict` / `Retired`**。
- **`要件` と `出典` は空にできない。**
- **検証手段が空なら `Confirmed` にできない**。「達成した」と言えるのは測り方が決まっているときだけで、
  検証手段の無い Confirmed は願望と区別が付かない。空欄のほか
  `-` / `–` / `—` / `TBD` / `UNKNOWN` / `n/a` / `未定` / `なし` / `未整備` も空扱い（大小文字は問わない）。
  **全部 Confirmed の REQ 表は、規約が機能していない兆候**。測れないものは Tentative で起票する。

### REQ 表のある文書（索引）

番号空間はクラス内グローバルなので、**新しい REQ を採番する前にここを見る**。

| クラス | 文書 | 範囲 |
|---|---|---|
| D01 | [product-goals.md](product-goals.md) | 目的・成功条件・非目標 |
| D17 | [search-quality-evaluation.md](search-quality-evaluation.md) | 検索品質の計測方法と受入基準 |
| D19 | [index-and-search.md](index-and-search.md) | 索引単位・スコアリング・返却単位・トークン予算 |

**決定ログのエントリに REQ-ID は書かない。** 決定ログは append-only なので後から ID を差し込めない
——紐付けは REQ 表の `出典` 列が担う（決定 → REQ ではなく REQ → 決定の一方向）。

## 何が機械検査されるか

`scripts/check-doc-classes.py` が CI と pre-push で走る。**error** で検査するのは:

- 3 つのマーカー（`doc-classes` / `doc-classes-na` / `doc-classes-index`）の対応と書式
- クラス一覧・N/A 宣言表・割当索引の書式と相互の突合
- frontmatter のキー、`doc_class` の実在・重複・n/a クラス指定の禁止、`tags` の完全一致
- `sources` の実在・リポジトリルート相対・**大文字小文字の完全一致**
- **stale**（`sources` に挙げたファイルが `distilled_from_sha` より後に内容変更されている）
- REQ 表の全項目（マーカー外の REQ 表・列数・ID 形式・番号重複・status 値域・
  **Confirmed の検証手段非空**・リンク実在）
- **REQ の `出典` が `docs/original-docs/` を名指ししたら `sources` にも載っていること**
- 本文の相対リンクの実在
- `docs/knowledge/` のサブディレクトリに `.md` を置くこと（1 階層下げるだけで無検査域になる）
- **検査対象が 0 件**（違反ではなく「検査が成立していない」）

`scripts/check-decision-log-immutability.py` が**決定ログの append-only 性**を error で検査する。

`--warn-only` は**ローカルで全件を眺めるための確認用**で、CI も pre-push もフラグ無しで呼ぶ。
**マーカー欠落と検査対象 0 件は `--warn-only` でも落ちる**（検査そのものが成立しないため）。

## 機械検査できないもの

- **番号の再利用禁止**。検査が見るのは現時点のスナップショットだけなので、`Retired` 行ごと削除して
  同じ番号を別の要件に振り直しても検出されない。
- **`sources` の網羅性**。stale 検査は「挙げた出典」に追従しているかしか見ないので、
  **`sources` から行を消せば stale も消える**。塞いであるのは REQ の `出典` が名指しした一次資料だけ。
  **出典は減らさない**——減らすときは、その知がもうその資料に依存していないことを本文で示す。
- **`出典` をリンクで書かなかった場合の突合**。プレーンテキストやインラインコードで書いた出典は
  突合されない。つまり「出典のリンクを外す」のが最も安い回避策になっている。
- **決定ログの中身**。append-only 検査が見るのは「既存エントリが改変・削除されていないか」だけで、
  新しい決定を書いたか・書いた内容が十分か（コンテキスト・理由・却下案・影響）は機械では分からない。
- **リンクの指し先の「中身」**。実在するのはファイルまでで、`#` 以降のアンカーと散文で書いた節名は
  未検査。
- **`docs/original-docs/` と `docs/qa/` の中身**。リンク検査もリンク切れ検査も行わない。
- **コードフェンスで囲んだ REQ ブロック・表・リンク**。フェンス内は「規約の見本」として全面的に
  無視する（この文書の例がまさにそれ）。囲まれた表は GitHub でも表として描画されないので、実データを
  そこに置くことは無い前提。
- **この README 自身の記述の鮮度**。README は frontmatter を持たない（`sources` も
  `distilled_from_sha` も無い）ので、`scripts/check-doc-classes.py` を書き換えても
  **ここが stale にならない**。検査の仕様を変えたら、この節を手で直す。

## paddock から意図的に削ったもの

doc-query は約 1,000 行、paddock は約 61,000 行。規約は規模に読み替える。

| paddock にあるもの | doc-query での扱い | 理由 |
|---|---|---|
| `scripts/bump-distilled-sha.py`（26KB） | **入れない** | 追従対象が 8 本。1 コマンド化の利得より、frontmatter を書き換えるスクリプトのバグ risk が大きい。**文書が 15 本を超えたら再検討する** |
| stale 検査のコミット除外（`is_metadata_only_change` / `is_pin_only_change`、300 行相当） | **入れない** | 偽陽性を減らす最適化だが、除外ロジック自体が fail-open の温床。この規模では偽陽性を手で解消するほうが安い |
| `docs/specifications/` | **入れない** | knowledge 1 層で足りる |
| active だが 0 本のクラス | **作らない** | paddock は D05/D16/D18 を active-0 で抱えて恒久 warning を出しているが、文書 8 本で恒久 warning を置くと本物の充足ギャップが埋もれる |

---

## 決定ログ

<!-- この節は append-only です。既存エントリの変更・削除は CI が検出します。 -->

### #1: HVE 由来の 2 層蒸留と文書クラス体系を採用する (2026-08-24) — 採用

#### コンテキスト

doc-query には要求定義も決定記録も無く、設計判断（BM25 の IDF を自前で平滑化した理由、pdfplumber を
選び PyMuPDF を避けた理由など）がコードコメントとセッションの記憶にしか残っていなかった。要件に安定
した参照子が無いため、「この変更で何が壊れないことを保証したいのか」を名指しできない状態だった。

直接の契機は、実 PDF での検証で見つかった欠陥（[#2](https://github.com/taito-station/doc-query/issues/2)
全角英数がスコアリング語彙から落ちる）である。修正自体は NFKC 正規化で足りるが、語彙照合の単位の
変更＝ランキングの既定値変更であり、**変更前の品質を数値で固定してからでないと「下がっていない」ことを
示せない**。18 件のテストがこの欠陥を素通りしたのも同じ根だった。

同じ蒸留モデルは `taito-station/paddock` と `taito-station/baseball-ticket` に導入済みで、いずれも
HVE のフル機能ではなく一部を抜き出して規模に読み替えている。

#### 決定

HVE 由来の 2 層蒸留（original-docs → qa → knowledge）、文書クラス体系（D01〜D21）、frontmatter 規約、
REQ-ID（`REQ-D{NN}-{NNN}`）、append-only の決定ログを採用する。整合は標準ライブラリのみで書いた
検査スクリプトが GitHub Actions と pre-push の両方で強制する。

paddock 準拠だが、`docs/specifications/` は作らず knowledge 1 層とし、`bump-distilled-sha.py` と
stale 検査のコミット除外は入れない（上表「paddock から意図的に削ったもの」）。

#### 理由

- **要件に安定した参照子が要る。** 文書を書き換えても壊れない ID が無いと、決定ログや issue から
  「どの要件のことか」を指せない。
- **検証手段の無い Confirmed を機械で禁じられる。** 「達成した」と言えるのは測り方が決まっているとき
  だけ、という規律を人手に委ねずに済む。
- **決定の理由が残る。** 却下した代替案まで書かせる書式にしないと、同じ議論を繰り返すか、過去の判断を
  根拠なく覆すことになる。
- **前例が 2 つある。** paddock / baseball-ticket で運用実績があり、規模に応じた削り方の判断基準も
  そちらに残っている。

#### 却下した代替案

- **doc-query 固有の文書クラス（D22 等）を切る。** paddock は D22〜D24 を追加しているが、その判定基準は
  「既存クラスへ押し込むと必須項目が総 UNKNOWN になるか」である。doc-query の資産を当てはめると、
  索引・検索・ランキングの仕様は **D08（データモデル・SoT）+ D19（アーキテクチャ）** に、検索品質の
  評価は **D17（品質保証・受入）** に必須項目が全部埋まる形で収まる。BM25 の 3 定数程度では paddock の
  追加基準を満たさない。
  **再開条件**: 学習型・意味検索（埋め込み・リランカ）を導入し、素性定義・重み・較正パラメータを持つ
  ようになったら、その時点で D22 相当の追加を再判定する。
- **要求定義書を単独ファイルで持つ**（HVE の `hve-dev/requirement-definition.md` 方式）。文書 8 本の
  規模では、要件をその要件が効く文書から切り離すほうが読みにくい。paddock も REQ 表を各文書に埋め込む
  方式を採っている。
- **`REQ-D{NN}-{NNN}` ではなく `FR-DOCQ-01` 形式にする。** 移植元の mdq が `FR-MDQ-01` を使っており
  対応は取りやすいが、番号空間の持ち主が曖昧になる。paddock と揃えて文書クラスを番号空間にする。
- **機械検査を入れず規約文書だけ置く。** baseball-ticket は CI を持たずローカル bash 1 本で運用して
  いるが、そちらは文書専用リポジトリで、コード変更に伴う stale が発生しない。doc-query はコードと
  文書が同居するので、追従漏れを人手の規律に委ねると必ず腐る。

#### 影響

- `docs/{knowledge, original-docs, qa}/` を新設。knowledge 8 本、一次資料 2 本、質問票 1 本
- `CLAUDE.md` を新設（探索規律と文書の書き方の入口）
- 以降、コードの変更は対応する REQ の `status` と `検証手段` の更新を伴う
- 機械検査スクリプトと CI は後続 PR（[#1](https://github.com/taito-station/doc-query/issues/1) の一部）。
  **検査を先に入れると「検査対象 0 件 → error」で自分自身が落ちる**ので、文書 → 検査の順にする
