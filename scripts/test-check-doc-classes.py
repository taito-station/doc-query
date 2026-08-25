#!/usr/bin/env python3
"""check-doc-classes.py 自身の回帰テスト。

検査の壊れ方は「例外で落ちる」ではなく「**対象 0 件で静かに通る**」形で入る。
だから検査を回すだけでは健全性が分からず、**違反を注入して落ちること**を
確かめる必要がある。本番検査より先に走らせる——本番が落ちた瞬間に、判定器が
まともかどうかを確かめる手段を同時に失わないため。

標準ライブラリのみ。`python3 scripts/test-check-doc-classes.py` で走る。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHECKER = HERE / "check-doc-classes.py"

results: list[tuple[bool, str, str]] = []


def isolated_env() -> dict[str, str]:
    """利用者の git 設定から切り離した環境。

    global の `commit.gpgsign` や `core.hooksPath` を継承すると、テストの
    前提が環境ごとに崩れる（他所のフックを実行してしまうことすらある）。
    """
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def tracked_files() -> list[str]:
    """追跡ファイルの一覧。コピー対象を列挙で持たない。

    列挙で持つと、`sources` が新しいディレクトリを指した瞬間に**このテスト
    だけ**が「sources が実在しない」で落ちる。対象の二重管理をやめて、
    リポジトリが実際に持っているものをそのまま写す。
    """
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git ls-files が失敗した（検査対象を組み立てられない）: "
                         f"{r.stderr.strip()}")
    files = [p for p in r.stdout.split("\0") if p]
    if not files:
        raise SystemExit("追跡ファイルが 0 件（検査対象を組み立てられない）")
    return files


TRACKED = tracked_files()


def build(tmp: Path) -> Path:
    root = tmp / "repo"
    for rel in TRACKED:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(ROOT / rel, dst)
        except OSError as e:
            # 追跡されているのに写せない＝作業ツリーが壊れている。黙って
            # 飛ばすと、欠けたファイルを前提に「通った」ことになる。
            raise SystemExit(f"追跡ファイルを写せない: {rel} ({e})")
    return root


def run(root: Path, *extra: str) -> subprocess.CompletedProcess:
    # git 履歴を持たないコピーなので stale は対象外にする。
    # stale 自体は test_stale_* が一時 git リポジトリで確かめる。
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), "--no-stale", *extra],
        capture_output=True, text=True)


def edit(path: Path, old: str, new: str) -> None:
    t = path.read_text(encoding="utf-8")
    if old not in t:
        raise AssertionError(f"前提が崩れている: {path.name} に {old[:40]!r} が無い")
    path.write_text(t.replace(old, new, 1), encoding="utf-8")


def bump_req_count(root: Path, label: str, delta: int) -> None:
    """ルート README の REQ 集計を delta だけ動かす。件数は書き固めない。"""
    p = root / "README.md"
    m = re.search(rf"{label} (\d+) 件", p.read_text(encoding="utf-8"))
    if m is None:
        raise AssertionError(f"前提が崩れている: README.md に {label} の件数が無い")
    edit(p, m.group(0), f"{label} {int(m.group(1)) + delta} 件")


def case(name: str, mutate, expect_in_output: str, expect_rc: int = 1,
         warn_only_rc: int | None = None) -> None:
    """`mutate(root)` で違反を作り、検査が落ちることを確かめる。

    warn_only_rc を渡すと `--warn-only` での終了コードも検証する
    （検査不成立は --warn-only でも 1 でなければならない）。
    """
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        mutate(root)
        r = run(root)
        ok = r.returncode == expect_rc and expect_in_output in r.stdout
        detail = "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:200]}"
        results.append((ok, name, detail))
        if warn_only_rc is not None:
            r2 = run(root, "--warn-only")
            ok2 = r2.returncode == warn_only_rc
            results.append((ok2, f"{name}（--warn-only で rc={warn_only_rc}）",
                            "" if ok2 else f"rc={r2.returncode}"))


K = "docs/knowledge"


# --- 対照: 手を加えなければ通る ------------------------------------------
def test_clean() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        r = run(root)
        ok = r.returncode == 0
        results.append((ok, "無改変なら通る",
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:300]}"))


# --- 検査が成立しない条件（--warn-only でも落ちる）------------------------
def test_no_targets() -> None:
    def mutate(root: Path) -> None:
        for p in (root / K).glob("*.md"):
            p.unlink()
    case("検査対象 0 件", mutate, "検査が成立していない", warn_only_rc=1)


def test_marker_missing() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "doc-classes.md", "<!-- doc-classes-index:begin -->", "")
    case("マーカー欠落", mutate, "マーカー doc-classes-index が無い", warn_only_rc=1)


def test_broken_table_row() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "doc-classes.md",
             "| D01 | 事業意図・成功条件定義書 | active | 1 |",
             "| D01 | 事業意図・成功条件定義書 | active |")
    case("クラス一覧の列数が崩れる", mutate, "4 列固定", warn_only_rc=1)


def test_req_table_outside_marker() -> None:
    def mutate(root: Path) -> None:
        p = root / K / "glossary.md"
        p.write_text(p.read_text(encoding="utf-8")
                     + "\n| REQ-ID | 要件 | 検証手段 | 出典 | status |\n|---|---|---|---|---|\n",
                     encoding="utf-8")
    case("マーカー外の REQ 表", mutate, "マーカーの外に REQ 表", warn_only_rc=1)


def test_decision_log_heading_outside_marker() -> None:
    def mutate(root: Path) -> None:
        p = root / K / "glossary.md"
        p.write_text(p.read_text(encoding="utf-8") + "\n## 決定ログ\n\n### #1-1: x (2026-08-24) — 採用\n",
                     encoding="utf-8")
    case("マーカー外の決定ログ見出し", mutate, "マーカーの外に決定ログ見出し", warn_only_rc=1)


def test_decision_log_markers_both_removed() -> None:
    def mutate(root: Path) -> None:
        p = root / K / "product-goals.md"
        edit(p, "<!-- decision-log:begin -->", "")
        edit(p, "<!-- decision-log:end -->", "")
    # マーカーを両方消しても、見出しが残るので「マーカー外」として捕まる
    case("decision-log マーカーを両方削除", mutate, "マーカーの外に決定ログ見出し",
         warn_only_rc=1)


# --- 違反（--warn-only なら 0）--------------------------------------------
def test_tags_mismatch() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "glossary.md", "tags: [D07]", "tags: [D08]")
    case("tags が doc_class と一致しない", mutate, "一致しない", warn_only_rc=0)


def test_confirmed_without_verification() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "product-goals.md",
             "`tests/test_search.py::test_search_respects_max_tokens_budget`", "TBD")
    case("Confirmed の検証手段が空扱い", mutate, "Confirmed なのに検証手段が空扱い",
         warn_only_rc=0)


def test_confirmed_with_inline_code_tbd() -> None:
    """インラインコードで書いた TBD も空扱いにする。

    検出のためにインラインコードを潰した状態で空判定すると、
    `tests/...::test_x` も `TBD` もどちらも空になってしまう。
    """
    def mutate(root: Path) -> None:
        edit(root / K / "product-goals.md",
             "`tests/test_search.py::test_search_respects_max_tokens_budget`", "`TBD`")
    case("検証手段を `TBD` とインラインコードで書く",
         mutate, "Confirmed なのに検証手段が空扱い", warn_only_rc=0)


def test_verification_in_inline_code_is_not_empty() -> None:
    """逆方向: インラインコードの検証手段を空扱いにしてはいけない。"""
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        r = run(root)
        ok = "検証手段が空扱い" not in r.stdout
        results.append((ok, "インラインコードの検証手段を空扱いにしない",
                        "" if ok else r.stdout.strip()[:200]))


def test_index_missing_row() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "doc-classes.md", "| knowledge/glossary.md | [D07] |\n", "")
    case("割当索引から 1 行削除", mutate, "割当索引に欠落", warn_only_rc=0)


def test_index_not_sorted() -> None:
    def mutate(root: Path) -> None:
        p = root / K / "doc-classes.md"
        t = p.read_text(encoding="utf-8")
        a = "| knowledge/ci-and-checks.md | [D21, D17] |\n"
        b = "| knowledge/glossary.md | [D07] |\n"
        p.write_text(t.replace(a + b, b + a, 1), encoding="utf-8")
    case("割当索引がパス昇順でない", mutate, "パス昇順でない", warn_only_rc=0)


def test_class_count_mismatch() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "doc-classes.md",
             "| D07 | 用語集・ドメインモデル定義書 | active | 1 |",
             "| D07 | 用語集・ドメインモデル定義書 | active | 2 |")
    case("クラス一覧の現行が実態と違う", mutate, "実態=", warn_only_rc=0)


def test_na_class_used() -> None:
    def mutate(root: Path) -> None:
        p = root / K / "glossary.md"
        edit(p, "doc_class: [D07]", "doc_class: [D06]")
        edit(p, "tags: [D07]", "tags: [D06]")
        edit(root / K / "doc-classes.md",
             "| knowledge/glossary.md | [D07] |", "| knowledge/glossary.md | [D06] |")
        edit(root / K / "doc-classes.md",
             "| D07 | 用語集・ドメインモデル定義書 | active | 1 |",
             "| D07 | 用語集・ドメインモデル定義書 | active | 0 |")
    case("n/a のクラスを doc_class に指定", mutate, "n/a のクラスを doc_class",
         warn_only_rc=0)


def test_active_zero() -> None:
    """クラスを active のまま 0 本にする。

    「まだ書いていない」と「そもそも要らない」を区別する方針なので、
    運用しないクラスは n/a で閉じさせる。
    """
    def mutate(root: Path) -> None:
        (root / K / "glossary.md").unlink()
        reg = root / K / "doc-classes.md"
        edit(reg, "| knowledge/glossary.md | [D07] |\n", "")
        edit(reg, "| D07 | 用語集・ドメインモデル定義書 | active | 1 |",
             "| D07 | 用語集・ドメインモデル定義書 | active | 0 |")
        # 消した文書へのリンクは別の違反になるので、入口からも外す
        for name in ("CLAUDE.md", "README.md"):
            p = root / name
            p.write_text(
                re.sub(r"^.*docs/knowledge/glossary\.md.*$\n?", "",
                       p.read_text(encoding="utf-8"), flags=re.M),
                encoding="utf-8")
    case("active かつ 0 本", mutate, "active かつ 0 本", warn_only_rc=0)


def test_na_row_missing_resume_condition() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "doc-classes.md",
             "| 複数人で開発・運用するようになったとき |", "|  |")
    case("N/A 表の再開条件が空", mutate, "再開条件が空", warn_only_rc=0)


def test_req_id_duplicate_across_files() -> None:
    """クラス内グローバルな一意性は、ファイル横断で集めないと検出できない。"""
    def mutate(root: Path) -> None:
        edit(root / K / "search-quality-evaluation.md", "REQ-D17-001", "REQ-D17-007")
    case("REQ-ID がファイル跨ぎで重複", mutate, "REQ-ID の重複", warn_only_rc=0)


def test_req_status_out_of_range() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "product-goals.md",
             "| [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | Confirmed |",
             "| [1-doc-flow-introduction.md](../original-docs/1-doc-flow-introduction.md) | たぶん |")
    case("REQ の status が値域外", mutate, "status の値域外", warn_only_rc=0)


def test_req_source_not_in_sources() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "product-goals.md",
             "  - docs/original-docs/1-doc-flow-introduction.md\n", "")
    case("REQ の出典が sources に無い", mutate, "sources に無い", warn_only_rc=0)


def test_broken_link() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "glossary.md", "(index-and-search.md)", "(nope.md)")
    case("本文のリンク切れ", mutate, "リンク先が実在しない", warn_only_rc=0)


def test_root_readme_broken_link() -> None:
    """検査対象はリポジトリルートの CLAUDE.md / README.md にも及ぶ。"""
    def mutate(root: Path) -> None:
        edit(root / "README.md", "(docs/knowledge/glossary.md)", "(docs/knowledge/nope.md)")
    case("ルート README のリンク切れ", mutate, "リンク先が実在しない", warn_only_rc=0)


def test_missing_source_file() -> None:
    def mutate(root: Path) -> None:
        (root / "docq" / "search.py").unlink()
    case("sources のファイルが実在しない", mutate, "sources が実在しない", warn_only_rc=0)


def test_doc_status_out_of_range() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "glossary.md", "status: Confirmed", "status: Retired")
    case("文書の status に Retired を使う", mutate, "status の値域外", warn_only_rc=0)


def test_updated_not_quoted() -> None:
    def mutate(root: Path) -> None:
        # 日付を書き固めない。文書を更新するたびにテストだけが落ちる。
        p = root / K / "glossary.md"
        m = re.search(r'^updated: "(\d{4}-\d{2}-\d{2})"$',
                      p.read_text(encoding="utf-8"), re.M)
        if m is None:
            raise AssertionError("前提が崩れている: glossary.md に updated が無い")
        edit(p, m.group(0), f"updated: {m.group(1)}")
    case("updated がクォートされていない", mutate, "クォートした YYYY-MM-DD",
         warn_only_rc=0)


def test_subdirectory_md() -> None:
    def mutate(root: Path) -> None:
        sub = root / K / "sub"
        sub.mkdir()
        (sub / "hidden.md").write_text("# 無検査域\n", encoding="utf-8")
    case("knowledge のサブディレクトリに .md", mutate, "サブディレクトリに .md",
         warn_only_rc=0)


def test_decision_entry_duplicate_id() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "index-and-search.md", "### #1-2:", "### #1-1:")
    case("決定ログの見出し ID が重複", mutate, "見出し ID が重複", warn_only_rc=0)


def test_decision_status_out_of_range() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "product-goals.md",
             "### #1-1: 削減率ではなく予算遵守を成功条件にする (2026-08-24) — 採用",
             "### #1-1: 削減率ではなく予算遵守を成功条件にする (2026-08-24) — たぶん")
    case("決定ログの status が値域外", mutate, "決定ログの status", warn_only_rc=0)


def test_req_blocks_two_in_one_doc() -> None:
    """1 文書に REQ ブロックが 2 つあっても「マーカー外」にしない。

    マーカー内を連結した文字列で除去すると、2 つ目以降で空振りして
    正常な表が fatal になる。
    """
    def mutate(root: Path) -> None:
        p = root / K / "ci-and-checks.md"
        t = p.read_text(encoding="utf-8")
        block = ("\n<!-- REQ:begin D17 -->\n\n"
                 "| REQ-ID | 要件 | 検証手段 | 出典 | status |\n"
                 "|---|---|---|---|---|\n"
                 "| REQ-D17-009 | 二つ目のブロック | `scripts/check-doc-classes.py` |"
                 " [QA](../qa/QA-doc-flow-introduction.md) | Tentative |\n\n"
                 "<!-- REQ:end D17 -->\n")
        p.write_text(t + block, encoding="utf-8")
        # 索引は D17 / ci-and-checks.md の組を新たに持つ
        edit(root / K / "README.md",
             "| D21 | [ci-and-checks.md](ci-and-checks.md) | CI と機械検査の構成・実行順序 |",
             "| D17 | [ci-and-checks.md](ci-and-checks.md) | 二つ目のブロック |\n"
             "| D21 | [ci-and-checks.md](ci-and-checks.md) | CI と機械検査の構成・実行順序 |")
        bump_req_count(root, "Tentative", 1)
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        mutate(root)
        r = run(root)
        ok = r.returncode == 0
        results.append((ok, "1 文書に REQ ブロックが 2 つでも通る",
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:300]}"))


def test_decision_status_superseded_is_allowed() -> None:
    """`Superseded by #N-M` は規約が前提にしている表記。書式違反にしない。"""
    def mutate(root: Path) -> None:
        edit(root / K / "product-goals.md",
             "### #1-1: 削減率ではなく予算遵守を成功条件にする (2026-08-24) — 採用",
             "### #1-1: 削減率ではなく予算遵守を成功条件にする (2026-08-24)"
             " — Superseded by #1-9")
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        mutate(root)
        r = run(root)
        ok = r.returncode == 0
        results.append((ok, "決定ログの status に Superseded by #N-M を使える",
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:300]}"))


def test_decision_marker_without_heading() -> None:
    """見出しを 1 行消すだけでマーカー内の検査が全部消える経路を塞ぐ。"""
    def mutate(root: Path) -> None:
        edit(root / K / "product-goals.md", "## 決定ログ\n", "")
    case("decision-log マーカーがあるのに見出しが無い", mutate,
         "`## 決定ログ` 見出しが無い", warn_only_rc=1)


def test_req_index_missing_row() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "README.md",
             "| D21 | [ci-and-checks.md](ci-and-checks.md) | CI と機械検査の構成・実行順序 |\n",
             "")
    case("REQ 索引から 1 行削除", mutate, "REQ 索引に欠落", warn_only_rc=0)


def test_req_index_extra_row() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "README.md",
             "| D21 | [ci-and-checks.md](ci-and-checks.md) | CI と機械検査の構成・実行順序 |",
             "| D21 | [ci-and-checks.md](ci-and-checks.md) | CI と機械検査の構成・実行順序 |\n"
             "| D21 | [glossary.md](glossary.md) | 実在しない REQ 表 |")
    case("REQ 索引に余剰の行", mutate, "REQ 索引に余剰の行", warn_only_rc=0)


def test_req_index_marker_missing() -> None:
    def mutate(root: Path) -> None:
        edit(root / K / "README.md", "<!-- req-index:begin -->", "")
    case("REQ 索引のマーカー欠落", mutate, "マーカー req-index が無い", warn_only_rc=1)


def test_req_counts_mismatch() -> None:
    """ルート README の REQ 集計が実数とずれたら落ちる。"""
    def mutate(root: Path) -> None:
        bump_req_count(root, "Confirmed", 3)
    case("README の REQ 集計が実数と違う", mutate, "実数は", warn_only_rc=0)


def test_req_counts_marker_missing() -> None:
    def mutate(root: Path) -> None:
        edit(root / "README.md", "<!-- req-counts:begin -->", "")
    case("REQ 集計のマーカー欠落", mutate, "マーカー req-counts が無い", warn_only_rc=1)


def test_duplicate_single_pair_marker() -> None:
    """1 組しか置けないマーカーの二重化を検出する（2 組目が無検査域になる）。"""
    def mutate(root: Path) -> None:
        p = root / K / "doc-classes.md"
        p.write_text(p.read_text(encoding="utf-8")
                     + "\n<!-- doc-classes-index:begin -->\n"
                       "| 文書 | doc_class |\n|---|---|\n"
                       "<!-- doc-classes-index:end -->\n",
                     encoding="utf-8")
    case("1 組しか置けないマーカーの二重化", mutate, "対で 1 組になっていない",
         warn_only_rc=1)


def test_req_table_separator_removed() -> None:
    """REQ 表の区切り行を消したら、黙って 1 行落とさずに落ちる。"""
    def mutate(root: Path) -> None:
        edit(root / K / "product-goals.md",
             "| REQ-ID | 要件 | 検証手段 | 出典 | status |\n|---|---|---|---|---|\n",
             "| REQ-ID | 要件 | 検証手段 | 出典 | status |\n")
    case("REQ 表の区切り行が無い", mutate, "区切り行でない", warn_only_rc=1)


def test_req_source_in_qa_not_in_sources() -> None:
    """一次資料は original-docs だけではない。qa 出典の抜け道も塞ぐ。"""
    def mutate(root: Path) -> None:
        edit(root / K / "ci-and-checks.md",
             "  - docs/qa/QA-doc-flow-introduction.md\n", "")
    case("REQ の出典（qa）が sources に無い", mutate, "sources に無い", warn_only_rc=0)


def test_entry_link_target_absent() -> None:
    """入口の文書が消えたら、リンク検査が 0 件になるのではなく落ちる。"""
    def mutate(root: Path) -> None:
        (root / "CLAUDE.md").unlink()
    case("入口の CLAUDE.md が無い", mutate, "入口リンクの検査が成立しない",
         warn_only_rc=1)


def test_link_with_title_is_not_broken() -> None:
    """`](path "title")` のタイトルをパスの一部と読まない。"""
    def mutate(root: Path) -> None:
        edit(root / K / "glossary.md", "(index-and-search.md)",
             '(index-and-search.md "索引と検索")')
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        mutate(root)
        r = run(root)
        ok = "リンク先が実在しない" not in r.stdout
        results.append((ok, "タイトル付きリンクを壊れたリンクにしない",
                        "" if ok else r.stdout.strip()[:200]))


def test_runs_without_site_packages() -> None:
    """標準ライブラリだけで動くこと（REQ-D21-004）を実測する。

    `sys.executable` でそのまま起動すると site-packages 込みで動くので、
    「標準ライブラリのみ」の証明にならない。`-I -S` で site を切って測る。
    """
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        r = subprocess.run(
            [sys.executable, "-I", "-S", str(CHECKER),
             "--root", str(root), "--no-stale"],
            capture_output=True, text=True)
        ok = r.returncode == 0
        results.append((ok, "site-packages 無し（-I -S）でも動く",
                        "" if ok else f"rc={r.returncode} err={r.stderr.strip()[:200]}"))


# --- stale 検査（一時 git リポジトリで確かめる）----------------------------
def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       env=isolated_env())
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} が失敗: {r.stderr.strip()}")
    return r


def build_git(tmp: Path) -> Path:
    """コピーを git リポジトリにして、全文書の sha を base コミットへ揃える。"""
    root = build(tmp)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    sha = _git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    for p in sorted((root / K).glob("*.md")):
        t = p.read_text(encoding="utf-8")
        t2 = re.sub(r'^(distilled_from_sha: )".*"$', rf'\1"{sha}"', t, flags=re.M)
        if t2 != t:
            p.write_text(t2, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "align sha")
    return root


def run_stale(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECKER), "--root", str(root)],
                          capture_output=True, text=True, env=isolated_env())


def test_stale_clean_passes() -> None:
    """対照: 出典が sha より後に変わっていなければ通る。"""
    with tempfile.TemporaryDirectory() as td:
        root = build_git(Path(td))
        r = run_stale(root)
        ok = r.returncode == 0
        results.append((ok, "stale: 出典に変更が無ければ通る",
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:300]}"))


def test_stale_source_changed_after_sha() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = build_git(Path(td))
        p = root / "docq" / "search.py"
        p.write_text(p.read_text(encoding="utf-8") + "\n# 変更\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "touch source")
        r = run_stale(root)
        ok = r.returncode == 1 and "STALE" in r.stdout
        results.append((ok, "stale: 出典が sha より後に変更されたら落ちる",
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:300]}"))


def test_stale_sha_not_in_history() -> None:
    """記録された sha が履歴に無いのを「変更なし」と読まない。"""
    with tempfile.TemporaryDirectory() as td:
        root = build_git(Path(td))
        p = root / K / "glossary.md"
        t = p.read_text(encoding="utf-8")
        p.write_text(re.sub(r'^distilled_from_sha: ".*"$',
                            'distilled_from_sha: "0000000"', t, flags=re.M),
                     encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "bogus sha")
        r = run_stale(root)
        ok = r.returncode == 1 and "履歴に無い" in r.stdout
        results.append((ok, "stale: sha が履歴に無ければ落ちる",
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:300]}"))


def main() -> int:
    for fn in sorted(
        (v for k, v in globals().items() if k.startswith("test_")),
        key=lambda f: f.__code__.co_firstlineno,
    ):
        fn()

    failed = [(n, d) for ok, n, d in results if not ok]
    for ok, name, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n      {detail}" if detail else ""))
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
