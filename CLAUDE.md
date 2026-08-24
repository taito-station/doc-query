# doc-query プロジェクト CLAUDE.md

作業時の判断規律のみを扱う。構成と手順は [README.md](README.md)、文書規約の全体は
[docs/knowledge/README.md](docs/knowledge/README.md) にあるので、ここには重複を書かない。

## ドキュメント / ナレッジ運用

doc-query の文書は HVE（[dahatake/HypervelocityEngineering](https://github.com/dahatake/HypervelocityEngineering), MIT）の
蒸留モデルを取り入れている。同じモデルを先に導入した `taito-station/paddock` の規約を規模に読み替えたもの。

- **2 層**: `docs/original-docs/`（RO 一次資料・実測ログ・調査所見）＋ `docs/qa/`（質問票 + 回答）→
  `docs/knowledge/`（status 付き確定知・**決定ログ付き**）。蒸留は Claude が回す。
- **確定知を読む入口は `docs/knowledge/`。** 決定を辿るのも同じファイルの末尾で完結する。
- **決定は「決定ログ」に書く**（独立した ADR ファイルは作らない）。新規の決定——ルール変更・設計判断・
  実験の採用/棄却——は、**その決定が効く文書**の決定ログへ append する。**append-only** で、覆すときは
  新エントリを積む。**同じ PR で本文側も直す**（決定ログ＝いつ・なぜ決めたか、本文＝今どうなっているか）。
  書式の詳細は [docs/knowledge/README.md](docs/knowledge/README.md)「決定ログの書き方」。
- **`sources` に挙げたファイルを内容ごと変更したら、参照元の `distilled_from_sha` を同じ PR で追従させる。**
  追従漏れは CI が落とす。**同一コミットに自分の sha は書けない**ので「本文コミット → sha 追従コミット」の
  2 コミットになる。
- **knowledge を 1 本足す・消す・`doc_class` を変えるときは、同じ PR で
  [docs/knowledge/doc-classes.md](docs/knowledge/doc-classes.md) のクラス一覧と割当索引も直す。**
- **用語で迷ったら [docs/knowledge/glossary.md](docs/knowledge/glossary.md)。** 特に scoring term /
  snippet token / token（消費量）は別物で、混同が過去に実害を出している。
- **`docs/original-docs/` の命名は issue 番号・0 埋めしない**（`1-`, `2-` …）。置くのは転記できないもの
  ——実測ログ・調査時点のコード所見・外部ツールの挙動観察。**GitHub Issue 本文は転記しない**
  （リンクと `gh issue view <N>` の 1 行を置く）。

## 要件の扱い

- **コードと規範要件が矛盾したら、コードを暗黙の正解として要件を上書きしない。** バグ修正か仕様変更かを
  明示して解消する。仕様変更なら実装前に要件を改訂する。
- **検証手段の無い要件を Confirmed にしない。** 測り方が決まっていないなら Tentative で起票する。
  全部 Confirmed の REQ 表は、規約が機能していない兆候。
- **ランキングに影響する既定値**（BM25 定数 / 語彙単位 / 正規化 / フォールバック条件）を変えるときは、
  [docs/knowledge/search-quality-evaluation.md](docs/knowledge/search-quality-evaluation.md) の
  回帰計測でベースラインを取ってから、開発用集とホールドアウト集の双方で下回らないことを確認する。

## 実装の規律

- **「何も見つからなかった」を「問題なし」と報告しない。** 走査が短く終わる理由は対象の不在以外にも
  ある（権限・マウント・競合・パスの種別違い）。この型の欠陥は 5 巡のセルフレビューで繰り返し出ており、
  最も踏みやすい（[docs/original-docs/1-doc-flow-introduction.md](docs/original-docs/1-doc-flow-introduction.md)）。
- **不可逆な操作（prune）は、安い推定ではなく確認した事実に基づいて行う。** 確認できないときは
  実行せず warning にする。
- **`Path.exists()` / `Path.is_dir()` / `Path.is_file()` を判定に使わない。** これらは
  `PermissionError` を送出して実行を中断させる。`os.path.exists()` は逆に例外を握り潰して `False` を
  返す。**「無い」と「判定できない」を区別できる形**（`indexer._stat_or_none`）を使う。
- **`errors` と `warnings` を混ぜない。** 自然に解消しない条件を `errors` に入れると、以後の実行が
  毎回失敗し、呼び出し側が終了コードを読まなくなる。

## 探索の規律

- **生読み前に `docq` で検索する。** PDF 内の答えを探すときは
  `python -m docq search --q "..."` でヒットチャンクだけ取り、必要なときだけ生ファイルへ。
  索引 `.docq/` は gitignore 済みで、`python -m docq index --root <dir>` で作り直せる。
- **コード探索は serena**（`mcp__serena__*`）。既知のファイル名や行番号がわかっている場合の Read は OK。
