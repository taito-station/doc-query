---
status: Confirmed
kind: knowledge
doc_class: [D21, D17]
tags: [D21, D17]
sources:
  - .github/workflows/ci.yml
  - docs/original-docs/1-doc-flow-introduction.md
  - docs/qa/QA-doc-flow-introduction.md
  - scripts/check-doc-classes.py
distilled_from_sha: "29b7c11"
updated: "2026-08-26"
---

# CI と機械検査

**稼働している。** 実体は `scripts/check-doc-classes.py`（文書クラス・REQ 表・決定ログ）、
`scripts/check-decision-log-immutability.py`（append-only）、`scripts/check-no-pdf-committed.py`
（実物の文書・生成物の混入）の 3 本と、それぞれの回帰テスト。GitHub Actions（`.github/workflows/ci.yml`）
と pre-push（`scripts/git-hooks/pre-push`）が同じスクリプトを同じ順序で呼ぶ。

pre-push の導入は `sh scripts/install-git-hooks.sh`（`core.hooksPath` を張るので、フックの更新は
自動で反映される）。**引き換えに、作業ツリーにあるスクリプトが push のたびに実行される。**
信頼できないブランチ（fork からの PR 等）を checkout した状態で push すると、そのブランチ版の
フックが動く——checkout する前に diff を見る。`core.hooksPath` を張ると `.git/hooks/` 配下の
既存フックは呼ばれなくなるので、導入スクリプトは上書き前に警告を出す。

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

- マーカーの欠落。**6 種類**（`doc-classes` / `doc-classes-na` / `doc-classes-index` /
  `req-index` / `REQ` / `decision-log`）。正本は [README.md](README.md) の「何が機械検査されるか」
- 検査対象の文書が 0 件
- 入口の `CLAUDE.md` / `README.md` が無い（リンク検査が黙って 0 件になる）
- append-only 検査で、base にも HEAD にも `docs/knowledge/` の `.md` が無い（初回導入と区別が付かない）
- 表の書式が崩れた行（黙って落とすと、そのクラスが「未定義」になって参照側が全部 error になり、
  原因が読めなくなる）

## 実行順序

**「検査自身の回帰テスト → 本番検査」の順に走らせる。** 本番検査を先にすると、落ちた瞬間に判定器の
健全性を確かめる手段を同時に失う。

CI と pre-push の両方で同じスクリプトを同じ順序で呼ぶ。

**pre-push のスキップ判定は検査の単位ごとに行う。** 文書検査は標準ライブラリだけで動くので条件は
`python3` の有無だけ。評価計測は `reportlab` が要る。**まとめて 1 つの条件にすると、文書検査に無関係な
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
| `docs` | 検査スクリプト 3 本の回帰テスト → 本番検査 → 実物文書の混入検査 |

**ゴールデンクエリの回帰計測（`eval`）はまだ無い。** `scripts/eval-golden.py` が未作成で、
pre-push 側も「スクリプトが無い」と表示して飛ばす。計測の設計は
[search-quality-evaluation.md](search-quality-evaluation.md) にあるが、**実体が無いものを
ジョブ表に現在形で載せない**——文書と実体の乖離はそれ自体が fail-open（決定ログ `#1-3`）。

**`docs` ジョブは全履歴を取得する必要がある。** stale 検査が `git log` と `merge-base` を使うので、
shallow clone では判定できず warning に退化する——これも fail-open の一種。

**`test` を 2 通りで回すのは、`tiktoken` が optional だから。** 未導入時は文字数からの近似に落ちる
経路があり、そちらだけが壊れる変更を検出できるようにする。

**append-only 検査の比較基準はイベントで変える。** `pull_request` では `origin/<base_ref>`、
`push` では `HEAD^`。push で `origin/main` を渡すと `merge-base(origin/main, HEAD)` が HEAD 自身に
なり、**自分と自分を比べて必ず通る**——検査が走っているように見えて何も見ていない。

## 意図的に入れないもの

doc-query は約 1,000 行、paddock は約 61,000 行。規約は規模に読み替える
（[README.md](README.md) の「paddock から意図的に削ったもの」）。

| 入れないもの | 理由 | 再検討の条件 |
|---|---|---|
| `bump-distilled-sha.py`（stale 追従の一括コマンド） | 追従対象が 8 本。1 コマンド化の利得より、frontmatter を書き換えるスクリプトのバグ risk が大きい | **文書が 15 本を超えたとき** |
| stale 検査のコミット除外（メタデータのみの変更等） | 偽陽性を減らす最適化だが、除外ロジック自体が fail-open の温床（除外対象のコミットを積むほど検査が消える） | 偽陽性が実際に運用の妨げになったとき |
| `docs/qa/` `docs/original-docs/` のリンク検査 | 一次資料は転記の忠実性が優先で、リンク切れで push を止める価値が薄い | — |

## 要件

<!-- REQ:begin D21 -->
| REQ-ID | 要件 | 検証手段 | 出典 | status |
|---|---|---|---|---|
| REQ-D21-001 | 文書規約の機械検査は GitHub Actions と pre-push の両方で、同じスクリプトを同じ順序で走らせる | `.github/workflows/ci.yml` の `docs` ジョブ / `scripts/git-hooks/pre-push` | [QA-doc-flow-introduction.md](../qa/QA-doc-flow-introduction.md) | Confirmed |
| REQ-D21-002 | 検査自身の回帰テストを本番検査より先に走らせる。判定器の健全性を、本番検査が落ちる前に確かめる | `.github/workflows/ci.yml` の `docs` ジョブのステップ順 / `scripts/test-check-doc-classes.py` / `scripts/test-check-decision-log-immutability.py` | [QA-doc-flow-introduction.md](../qa/QA-doc-flow-introduction.md) | Confirmed |
| REQ-D21-003 | マーカーの欠落・検査対象 0 件・表の書式崩れは「違反」ではなく「検査が成立していない」として扱い、`--warn-only` でも抑止しない | `scripts/test-check-doc-classes.py::test_no_targets` / `::test_marker_missing` / `::test_broken_table_row`（いずれも `--warn-only` で rc=1 を検証） | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D21-004 | 検査スクリプトは標準ライブラリのみで動く。`python3` があれば実行できる性質を保つ | `scripts/test-check-doc-classes.py::test_runs_without_site_packages`（`-I -S` で site を切って実行） | [QA-doc-flow-introduction.md](../qa/QA-doc-flow-introduction.md) | Confirmed |
| REQ-D21-005 | pre-push のスキップ判定は検査の単位ごとに行う。ある検査に無関係な依存が欠けただけで別の検査が飛ばない | 未整備 | [QA-doc-flow-introduction.md](../qa/QA-doc-flow-introduction.md) | Tentative |
| REQ-D21-006 | CI は `tiktoken` 有無の両方で `pytest` を回す。optional 依存の片側だけが壊れる変更を検出できるようにする | `.github/workflows/ci.yml` の `test` ジョブの matrix | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
| REQ-D21-007 | stale 検査を行う CI ジョブは全履歴を取得する。shallow clone で判定できないことを「変更なし」と読まない | `.github/workflows/ci.yml` の `docs` ジョブの `fetch-depth: 0` | [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |
<!-- REQ:end D21 -->

**REQ-D21-005 が Tentative なのは、スキップ経路を自動で踏むテストが無いため。** `python3` や
`reportlab` を欠いた環境を作って検証する必要があり、実装は満たしているが測れていない。

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

### #1-2: 検査不成立を違反と区別し、`--warn-only` でも抑止しない (2026-08-24) — 採用

#### コンテキスト

検査には 2 種類の失敗がある。「違反が見つかった」と「**検査が成立しなかった**」である。後者は
マーカーの欠落・検査対象 0 件・表の書式崩れで起き、いずれも**「違反が無い」ことの証明にならない**。

同じ型の欠陥を実装側で 5 巡にわたって潰してきた（`--root` の走査が短く終わる理由を「対象が無い」と
解釈して不可逆な削除をする、など）。検査スクリプト自身が同じ罠を踏まないようにする必要があった。

#### 決定

`Report` を error / warning / **fatal** の 3 系統に分け、fatal は `--warn-only` でも終了コード 1 に
する。fatal に振るのは次の 3 つ。

- 必須マーカーの欠落
- 検査対象の文書が 0 件
- 表の書式が崩れた行（黙って落とすと一意性検査や件数の突合から消えて、違反が通る）

**マーカーを両方消せば append-only 検査が消える**経路も、`## 決定ログ` 見出しがマーカー外にあれば
fatal にすることで塞いだ。

#### 理由

- **`--warn-only` は「全件を眺める」ための道具であって、検査を無効化する手段ではない。** 違反を
  警告に落とすのは意味があるが、検査が成立していないことまで警告に落とすと、`--warn-only` を付ければ
  何でも通る抜け道になる。
- **判定器の健全性は、判定結果とは別に確かめる必要がある。** だから回帰テストを本番検査より先に走らせ、
  違反を注入して落ちることを 54 パターンで確認している。

#### 却下した代替案

- **すべてを error にして fatal を作らない。** `--warn-only` で全件を眺める用途が失われる。
  規約を大きく変えるときに 1 件ずつ潰す進め方ができなくなる。
- **マーカー欠落を warning にする。** paddock が stale 検査で実証したとおり、警告は無視される。
  しかも「マーカーが無い＝検査していない」を警告で流すと、検査していない状態が常態化する。
- **検査対象 0 件を正常終了にする。** ディレクトリ名の変更や検査条件の取り違えで検査が丸ごと無効化
  されても気づけない。**これが最も典型的な fail-open。**

#### 影響

- `--warn-only` を付けても、規約の骨格が壊れていれば CI は落ちる
- 検査を追加するときは「違反」か「検査不成立」かを先に決める
- 回帰テストは `--warn-only` での終了コードも検証する（`case(..., warn_only_rc=...)`）

### #1-3: 判定器のセルフレビューで見つかった fail-open をまとめて塞ぐ (2026-08-25) — 採用

#### コンテキスト

`#1-2` で「検査不成立を違反と区別する」と決めたが、独立レビューを回したところ、**その決定を実装した
判定器の側に同じ型の穴が複数残っていた**。決定を書いただけでは守られない、という実例になった。

- push イベントの append-only 検査が `merge-base(origin/main, HEAD) == HEAD` になり、自分と自分を
  比べて必ず通っていた
- base に `docs/knowledge/` が無いときを無条件に「初回導入」として rc=0 にしていた（ディレクトリの
  改名と区別が付かない）
- 入口の `CLAUDE.md` / `README.md` が無ければリンク検査を黙って飛ばしていた
- append-only 検査が**正規化後のテキスト**を比較しており、コードフェンスとインラインコードの中身は
  書き換え放題だった
- 検査対象の 3 本目（`check-no-pdf-committed.py`）にだけ回帰テストが無いのに、文書は「3 本と、
  それぞれの回帰テスト」と書いていた
- `--no-stale` を全ケースに渡していたため、stale 検査が 1 度も実行されていなかった

#### 決定

**判定できない条件はすべて fail-close に倒す。** 上記をすべて塞ぎ、あわせて次を規約に加える。

- **`req-index` マーカー**を必須にし、README の「REQ 表のある文書（索引）」を実在する REQ マーカーの
  集合と突合する。番号空間がクラス内グローバルなので、索引の欠落は採番の重複を招く
- **一次資料は `docs/original-docs/` と `docs/qa/` の両方**。REQ の出典が名指しした一次資料は
  `sources` にも要る、という封じを qa 側にも広げる
- **`.gitignore` は綴りでなく効果で検査する。** `git check-ignore` に判定させ、等価な記法への
  書き換えを違反にしない
- **決定ログの status に `Superseded by #N-M` を許す。** 規約が「覆すときは新エントリを積む」と
  している以上、その表記が書式違反になるのは矛盾していた
- 既存エントリの**並べ替え・間への挿入**も append-only 違反として検出する

#### 理由

- **判定器の穴は、判定結果からは見えない。** 5 巡のセルフレビューで実装側に見つけたのと同じ型の欠陥が
  判定器側にも入っていた。「規約を機械で守らせる仕組み」自体を、独立したレビューにかける必要がある。
- **文書と実体の乖離は、それ自体が fail-open。** 「3 本と、それぞれの回帰テスト」と書いてあれば、
  読み手はテストがある前提で判断する。書いた通りにするか、書き直すかの二択しかない。
- **正規化は検出のための道具で、比較の道具ではない。** 長さを保つマスクに変えて、検出はマスク側・
  比較は生テキスト側と役割を分けた。

#### 却下した代替案

- **push イベントでは append-only 検査をしない。** 直 push を禁じている以上ほぼ通らない経路だが、
  「走っているのに何も見ていない」より「走らない」ほうが良いとは言えない。base を変えれば済む。
- **`.gitignore` の行を完全一致で見続ける。** 実装は単純だが、検査しているのは規約ではなく綴り。
- **REQ 索引を手書きのままにする。** README 自身が「突合していない」と限界を明記していたが、
  限界を書くことは限界を塞ぐことの代わりにならない。

#### 影響

- `scripts/test-check-no-pdf-committed.py` を追加し、CI と pre-push の回帰テストは 3 本になる
- 回帰テストは 73 + 17 + 9 パターン。stale 検査は一時 git リポジトリを作って実測する
- REQ-D21-004 の検証手段を `-I -S`（site を切った実行）に変更。`sys.executable` での実行は
  site-packages 込みなので「標準ライブラリのみ」の証明になっていなかった
- pre-push の依存判定を「どの python でその依存を import できるか」に統一し、`.venv` の有無で
  分岐しない
- **`Report` の warning 系統を削る。** `#1-2` は error / warning / fatal の 3 系統と書いたが、
  warning は produce 側が一度も書かれず dead code のままだった。`#1-2` の核（fatal を
  `--warn-only` でも抑止しない）は変わらない。**必要になったら最初の利用箇所と一緒に戻す**

### #1-4: 手書きの索引・集計は置かず、必ず実数と突合する (2026-08-26) — 採用

#### コンテキスト

`#1-3` で REQ 索引（`req-index`）を機械突合にしたが、2 巡目のレビューで**同型の乖離がもう 1 つ**
見つかった。ルート `README.md` の「Confirmed 10 件 / Tentative 18 件」が実数（17 / 18）とずれており、
機械検査の対象外なので CI では捕まらない状態だった。加えて、`ci-and-checks.md` のジョブ構成表が
**実在しない `eval` ジョブ**を現在形で載せていた。

#### 決定

**文書の中に置く「集計」と「索引」は、機械で実数と突合できる形にする。** できないものは書かない。

- ルート `README.md` の REQ 集計を `req-counts` マーカーで囲い、status 別の実数と突合する
- 実体の無いジョブ・スクリプトを表に現在形で載せない（`eval` は「まだ無い」と明記した）

#### 理由

- **同じ型の欠陥が 2 巡続けて出た。** 1 度目は「限界として明記する」で済ませていたが、
  限界を書くことは限界を塞ぐことの代わりにならない、というのが `#1-3` の結論だった。
- **数字は最も腐りやすい。** 要件を 1 行足すたびに全ての集計が古くなる。人手で追う前提を置くと、
  「文書は信用できない」が常態化する。

#### 却下した代替案

- **集計を README から消す。** 腐らないが、入口から要件の規模が見えなくなる。突合できるなら残す。
- **集計を検査せず「参考値」と断る。** 断り書きは読まれない。paddock の warning と同じ末路になる。

#### 影響

- マーカーは 7 種類になる（`req-counts` を追加）。1 組しか置けないマーカーの**二重化**も
  「検査が成立していない」として fatal にする
- REQ 表も他の表と同じく `table_rows()` を通す。区切り行の実在を確かめないまま先頭のデータ行が
  黙って落ちる経路を塞いだ
- CI の `run:` へ context を直接展開せず `env:` 経由にする。push の比較基準は
  `github.event.before`（空・全 0 なら error）
- 回帰テストの一時 git リポジトリは `GIT_CONFIG_GLOBAL=/dev/null` で利用者の設定から切り離す

<!-- decision-log:end -->
