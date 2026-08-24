---
status: Tentative
kind: knowledge
doc_class: [D21, D17]
tags: [D21, D17]
sources:
  - docs/original-docs/1-doc-flow-introduction.md
  - docs/qa/QA-doc-flow-introduction.md
distilled_from_sha: "5f5f0a3"
updated: "2026-08-24"
---

# CI と機械検査

> **status: Tentative。** ここに書かれた検査は
> [#1](https://github.com/taito-station/doc-query/issues/1) の後続 PR で実装する。**文書 → 検査の順に
> しか導入できない**——検査を先に入れると「検査対象 0 件 → error」で自分自身が落ちるため。実装が
> 入った時点で Confirmed に上げる。

## 何を機械で守るか

規約は人手では守れない、という前提に立つ。paddock で実証されたのは次の 2 点である。

- **警告は無視される。** stale 検査を warning のまま運用したところ、写した量に比例して追従漏れが
  静かに溜まった。error へ昇格させて初めて機能した。
- **検査の壊れ方は「例外で落ちる」ではなく「対象 0 件で静かに通る」。** だから**検査スクリプト自身の
  回帰テスト**が要る。

## fail-open を作らない

この原則が最も重要で、doc-query の実装側でも同じ型の欠陥を 5 巡にわたって潰してきた
（実測の記録は [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md)、判断は
[index-and-search.md](index-and-search.md) の決定ログ `#1-3`）。**「何も見つからなかった」を
「問題なし」と報告する経路を作らない。**

具体的には次を「違反」ではなく**「検査が成立していない」**として扱い、`--warn-only` でも抑止しない。

- マーカーの欠落。**5 種類**（`doc-classes` / `doc-classes-na` / `doc-classes-index` / `REQ` /
  `decision-log`）。正本は [README.md](README.md) の「何が機械検査されるか」
- 検査対象の文書が 0 件
- 表の書式が崩れた行（黙って落とすと、そのクラスが「未定義」になって参照側が全部 error になり、
  原因が読めなくなる）

## 実行順序

**「検査自身の回帰テスト → 本番検査」の順に走らせる。** 本番検査を先にすると、落ちた瞬間に判定器の
健全性を確かめる手段を同時に失う。

CI と pre-push の両方で同じスクリプトを同じ順序で呼ぶ。

**pre-push のスキップ判定は検査の単位ごとに行う。** 文書検査は標準ライブラリだけで動くので条件は
`python3` の有無だけ。評価計測は `reportlab` を要る。**まとめて 1 つの条件にすると、文書検査に無関係な
依存が欠けただけで文書検査まで黙って飛ぶ**——この文書自身が禁じている fail-open になる。

| 検査 | スキップ条件 |
|---|---|
| 文書検査（`check-doc-classes.py` ほか） | `python3` が無い |
| 評価計測（ゴールデンクエリ） | `reportlab` を import できない |

スキップしたときは**理由を出す**。未セットアップの環境で push を止めない代わりに、担保は CI 側にある。

## ジョブ構成

| ジョブ | 内容 |
|---|---|
| `test` | Python 3.10（`[dev]` のみ＝**tiktoken 無しのフォールバック経路**）と 3.13（`[tokens,dev]`）の 2 通りで `pytest` |
| `docs` | 検査スクリプトの回帰テスト → 本番検査 → 実物文書の混入検査 |
| `eval` | ゴールデンクエリの回帰計測（[search-quality-evaluation.md](search-quality-evaluation.md)） |

**`docs` ジョブは全履歴を取得する必要がある。** stale 検査が `git log` と `merge-base` を使うので、
shallow clone では判定できず warning に退化する——これも fail-open の一種。

**`test` を 2 通りで回すのは、`tiktoken` が optional だから。** 未導入時は文字数からの近似に落ちる
経路があり、そちらだけが壊れる変更を検出できるようにする。

## 意図的に入れないもの

doc-query は約 1,000 行、paddock は約 61,000 行。規約は規模に読み替える
（[README.md](README.md) の「paddock から意図的に削ったもの」）。

| 入れないもの | 理由 | 再検討の条件 |
|---|---|---|
| `bump-distilled-sha.py`（stale 追従の一括コマンド） | 追従対象が 8 本。1 コマンド化の利得より、frontmatter を書き換えるスクリプトのバグ risk が大きい | **文書が 15 本を超えたとき** |
| stale 検査のコミット除外（メタデータのみの変更等） | 偽陽性を減らす最適化だが、除外ロジック自体が fail-open の温床（除外対象のコミットを積むほど検査が消える） | 偽陽性が実際に運用の妨げになったとき |
| `docs/qa/` `docs/original-docs/` のリンク検査 | 一次資料は転記の忠実性が優先で、リンク切れで push を止める価値が薄い | — |

---

<!-- decision-log:begin -->
## 決定ログ

<!-- この節は append-only です。既存エントリの変更・削除は CI が検出します。 -->

### #1-1: 機械検査を GitHub Actions と pre-push の両方で走らせる (2026-08-24) — 採用

#### コンテキスト

同じ蒸留モデルを導入した 2 つのリポジトリで扱いが分かれていた。paddock は GitHub Actions の CI ジョブ
として強制し、baseball-ticket は CI を持たずローカルの bash 1 本で運用している。

#### 決定

**GitHub Actions と pre-push の両方**で同じスクリプトを走らせる。pre-push は実行環境が整っていなければ
スキップし、担保は CI 側に置く。

#### 理由

- **baseball-ticket が CI を持たないのは、そちらが文書専用リポジトリだから。** コード変更に伴う stale が
  構造的に発生しない。doc-query はコードと文書が同居するので、追従漏れを人手の規律に委ねると必ず腐る。
- **pre-push だけでは強制にならない。** フックは環境ごとの設定で、新しい clone では入っていない。
- **CI だけでは遅い。** 文書を触るたびに push してから落ちるのは、規約の学習コストを不必要に上げる。
- 両方に置いても**同じスクリプトを呼ぶ限り二重管理にならない**。

#### 却下した代替案

- **CI のみ**。手元で気づけない。規約に慣れるまでの往復が増える。
- **pre-push のみ**（baseball-ticket 方式）。強制力が環境依存になる。
- **pre-commit**。コミットのたびに全文書を検査するのは重く、WIP コミットを妨げる。push の単位で十分。

#### 影響

- `scripts/git-hooks/pre-push` と `scripts/install-git-hooks.sh` を置く
- 検査スクリプトは**標準ライブラリのみ**で書く。PyYAML を要求すると CI と pre-push の両方で依存
  インストールが要り、「`python3` があれば動く」性質を失う。その制約のために `doc_class` / `tags` は
  フロースタイル 1 行に強制する
- 検査スクリプト自身の回帰テストを持ち、本番検査より先に走らせる

<!-- decision-log:end -->
