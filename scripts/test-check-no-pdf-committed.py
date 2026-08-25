#!/usr/bin/env python3
"""check-no-pdf-committed.py 自身の回帰テスト。

一時的な git リポジトリを作り、実物の文書や生成物を追跡させて、
検査が実際に落ちることを確かめる。**混入が無いから通った**のか
**検査が働いていないから通った**のかは、違反を注入しないと分からない。

標準ライブラリのみ。`python3 scripts/test-check-no-pdf-committed.py` で走る。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check-no-pdf-committed.py"

GITIGNORE = ".docq/\n.docq-eval/\n"

results: list[tuple[bool, str, str]] = []


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """git を実行する。失敗を素通りさせるとテストの前提が黙って崩れる。"""
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} が失敗: {r.stderr.strip()}")
    return r


def build(tmp: Path) -> Path:
    root = tmp / "repo"
    root.mkdir()
    (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (root / "README.md").write_text("# sample\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


def run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECKER), "--root", str(root)],
                          capture_output=True, text=True)


def add(root: Path, rel: str, force: bool = False) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4\n")
    git(root, "add", *(["-f"] if force else []), "--", rel)
    git(root, "commit", "-q", "-m", f"add {rel}")


def case(name: str, mutate, expect_rc: int, expect_in: str = "") -> None:
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td))
        mutate(root)
        r = run(root)
        ok = r.returncode == expect_rc and (not expect_in or expect_in in r.stdout)
        results.append((ok, name,
                        "" if ok else f"rc={r.returncode} out={r.stdout.strip()[:200]}"))


# --- 対照 -----------------------------------------------------------------
def test_clean() -> None:
    case("混入が無ければ通る", lambda root: None, 0)


# --- 実物の文書の混入 ------------------------------------------------------
def test_pdf_is_rejected() -> None:
    case("PDF の追跡を弾く", lambda root: add(root, "docs/sample.pdf"),
         1, "追跡されている")


def test_uppercase_pdf_is_rejected() -> None:
    """拡張子の大文字。git のパススペックは大小を区別する。"""
    case("大文字 .PDF の追跡を弾く", lambda root: add(root, "docs/SAMPLE.PDF"),
         1, "追跡されている")


def test_office_document_is_rejected() -> None:
    case("Office 文書の追跡を弾く", lambda root: add(root, "docs/sample.docx"),
         1, "追跡されている")


def test_nested_pdf_is_rejected() -> None:
    """深い階層でも捕まること（パススペックが階層を跨ぐことの確認）。"""
    case("入れ子の PDF の追跡を弾く", lambda root: add(root, "a/b/c/deep.pdf"),
         1, "追跡されている")


# --- 生成物の混入 ----------------------------------------------------------
def test_index_db_is_rejected() -> None:
    def mutate(root: Path) -> None:
        add(root, ".docq/index.sqlite", force=True)
    case("索引 DB の追跡を弾く", mutate, 1, "追跡されている")


# --- .gitignore ------------------------------------------------------------
def test_missing_ignore_is_rejected() -> None:
    def mutate(root: Path) -> None:
        (root / ".gitignore").write_text(".docq-eval/\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "drop ignore")
    case(".docq/ が無視されなくなったら弾く", mutate, 1, "無視されない")


def test_equivalent_ignore_notation_passes() -> None:
    """等価な記法へ書き換えただけで落とさない。

    検査するのは「無視されるか」であって、`.gitignore` の綴りではない。
    """
    def mutate(root: Path) -> None:
        (root / ".gitignore").write_text("/.docq/\n/.docq-eval/**\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "rewrite ignore")
    case("等価な .gitignore の記法は通る", mutate, 0)


# --- 検査が成立しない条件 --------------------------------------------------
def test_outside_git_repo_is_rejected() -> None:
    """git が使えないことを「混入なし」と読まない。"""
    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / "plain"
        plain.mkdir()
        (plain / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
        r = run(plain)
        ok = r.returncode == 1
        results.append((ok, "git リポジトリでなければ弾く",
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
