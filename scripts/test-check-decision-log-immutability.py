#!/usr/bin/env python3
"""check-decision-log-immutability.py 自身の回帰テスト。

一時的な git リポジトリを作り、base コミットを置いてから決定ログを
いじって、append-only 違反が実際に落ちることを確かめる。
比較そのものが成立しない場合（マーカーが壊れている等）も落ちること。

標準ライブラリのみ。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check-decision-log-immutability.py"

DOC = """---
status: Confirmed
kind: knowledge
doc_class: [D01]
tags: [D01]
sources:
  - docs/original-docs/1-x.md
distilled_from_sha: "0000000"
updated: "2026-08-24"
---

# サンプル

本文。

---

<!-- decision-log:begin -->
## 決定ログ

<!-- この節は append-only です。 -->

### #1-1: 最初の決定 (2026-08-24) — 採用

#### コンテキスト

もとの本文。

### #1-2: 二つ目の決定 (2026-08-24) — 採用

#### コンテキスト

もう一つ。
<!-- decision-log:end -->
"""

results: list[tuple[bool, str, str]] = []


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def build(tmp: Path) -> Path:
    root = tmp / "repo"
    (root / "docs" / "knowledge").mkdir(parents=True)
    (root / "docs" / "knowledge" / "sample.md").write_text(DOC, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "work")
    return root


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), "--base", "main"],
        capture_output=True, text=True)


def commit(root: Path, msg: str = "change") -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg)


def case(name: str, mutate, expect_rc: int, expect_in: str = "") -> None:
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        mutate(root)
        commit(root)
        r = run(root)
        ok = r.returncode == expect_rc and (not expect_in or expect_in in r.stdout)
        results.append((ok, name,
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:200]}"))


def doc(root: Path) -> Path:
    return root / "docs" / "knowledge" / "sample.md"


def test_append_is_allowed() -> None:
    def mutate(root: Path) -> None:
        p = doc(root)
        p.write_text(p.read_text(encoding="utf-8").replace(
            "<!-- decision-log:end -->",
            "### #1-3: 三つ目 (2026-08-24) — 採用\n\n#### コンテキスト\n\n追記。\n"
            "<!-- decision-log:end -->"), encoding="utf-8")
    case("末尾への追記は通る", mutate, 0)


def test_body_edit_is_rejected() -> None:
    def mutate(root: Path) -> None:
        p = doc(root)
        p.write_text(p.read_text(encoding="utf-8").replace("もとの本文。", "書き換えた。"),
                     encoding="utf-8")
    case("既存エントリの改変を弾く", mutate, 1, "改変されている")


def test_entry_removal_is_rejected() -> None:
    def mutate(root: Path) -> None:
        p = doc(root)
        t = p.read_text(encoding="utf-8")
        i = t.index("### #1-2:")
        j = t.index("<!-- decision-log:end -->")
        p.write_text(t[:i] + t[j:], encoding="utf-8")
    case("エントリの削除を弾く", mutate, 1, "削除されている")


def test_section_removal_is_rejected() -> None:
    def mutate(root: Path) -> None:
        p = doc(root)
        t = p.read_text(encoding="utf-8")
        p.write_text(t[:t.index("<!-- decision-log:begin -->")], encoding="utf-8")
    case("決定ログ節ごとの削除を弾く", mutate, 1, "削除されている")


def test_file_removal_is_rejected() -> None:
    def mutate(root: Path) -> None:
        doc(root).unlink()
    case("決定ログを持つ文書の削除を弾く", mutate, 1, "削除されている")


def test_heading_rename_is_rejected() -> None:
    """見出しを変えるのも改変（ID を振り直せば履歴の参照が壊れる）。"""
    def mutate(root: Path) -> None:
        p = doc(root)
        p.write_text(p.read_text(encoding="utf-8").replace(
            "### #1-1: 最初の決定", "### #1-1: 最初の判断"), encoding="utf-8")
    case("見出しの書き換えを弾く", mutate, 1, "改変されている")


def test_broken_markers_are_rejected() -> None:
    """比較できないことを『違反なし』と読まない。"""
    def mutate(root: Path) -> None:
        p = doc(root)
        p.write_text(p.read_text(encoding="utf-8").replace(
            "<!-- decision-log:end -->", ""), encoding="utf-8")
    case("マーカーが壊れていたら弾く", mutate, 1, "1 組になっていない")


def test_unrelated_change_passes() -> None:
    """本文（決定ログ節より上）の書き換えは append-only の対象外。"""
    def mutate(root: Path) -> None:
        p = doc(root)
        p.write_text(p.read_text(encoding="utf-8").replace(
            "# サンプル\n\n本文。", "# サンプル\n\n本文を差分マージした。"),
            encoding="utf-8")
    case("決定ログ以外の変更は通る", mutate, 0)


def test_missing_base_is_rejected() -> None:
    """基準が見つからないことを『違反なし』と読まない。"""
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        r = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), "--base", "nonexistent"],
            capture_output=True, text=True)
        ok = r.returncode == 1
        results.append((ok, "存在しない基準を渡したら弾く",
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:200]}"))


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
