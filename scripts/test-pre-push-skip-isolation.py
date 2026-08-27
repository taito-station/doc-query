#!/usr/bin/env python3
"""REQ-D21-005: pre-push のスキップ判定が検査単位ごとに独立していることを検証する。

pre-push を実際に実行するテストではない。git リポジトリ環境・PATH 制御・
stdin 模擬が必要になり、標準ライブラリだけでは安定しないため、スクリプトの
テキスト構造を解析して「スキップ判定が検査ブロックごとに閉じているか」を
確かめる。

標準ライブラリのみ。`python3 scripts/test-pre-push-skip-isolation.py` で走る。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "git-hooks" / "pre-push"

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name, "" if ok else detail))


def followed_by(text: str, cond_substr: str, expect_substr: str,
                 window: int = 12) -> tuple[bool, str]:
    """`cond_substr` を含む行の直後 `window` 行以内に `expect_substr` があるか。

    if/else/fi をネスト込みで厳密に対応付けようとすると壊れやすいので、
    「スキップ判定のすぐ後で対応する検査コマンドが呼ばれている」ことを
    近傍の行ウィンドウで近似的に確かめる。
    """
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines) if cond_substr in l), None)
    if idx is None:
        raise AssertionError(f"前提が崩れている: {cond_substr!r} を含む行が無い")
    snippet = "\n".join(lines[idx: idx + window])
    return expect_substr in snippet, snippet


def test_skip_blocks_are_independent() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    invocations = re.findall(r"py_with (\w+)", text)
    ok = len(invocations) >= 2
    check(ok, "py_with 呼び出しが 2 箇所以上ある（pytest 用と reportlab 用）",
          f"実際の呼び出し: {invocations}")

    cmd_v_count = text.count("command -v python3")
    check(cmd_v_count >= 1, "command -v python3 のチェックが 1 箇所以上ある（文書検査用）",
          f"実際の件数: {cmd_v_count}")

    ok, snippet = followed_by(text, "py_with pytest", "-m pytest")
    check(ok, "pytest のスキップ判定の直後に pytest 実行がある", snippet)

    ok, snippet = followed_by(text, "command -v python3", "check-doc-classes.py")
    check(ok, "文書検査のスキップ判定の直後に文書検査スクリプトの実行がある", snippet)

    ok, snippet = followed_by(text, "py_with reportlab", "eval-golden.py")
    check(ok, "評価計測のスキップ判定の直後に eval-golden.py の呼び出しがある", snippet)

    global_skip = re.search(r"^\s*exit 0\s*$", text, re.M)
    check(global_skip is None,
          "全検査をまとめてバイパスするグローバルな exit 0 が無い",
          "exit 0 の単独行が見つかった")


def test_no_global_skip_guard() -> None:
    """関数定義・変数定義を除いた実行部分の先頭に、全検査をバイパスする exit 0 が無い。

    先頭の `echo "==> ..."` が最初の検査ブロックの開始を示す。それより前は
    `set -e` / `cd` / 関数定義など前段の準備であり、ここに `exit 0` があると
    条件次第で全検査が黙ってバイパスされる。
    """
    text = SCRIPT.read_text(encoding="utf-8")
    lines = text.splitlines()

    first_exec = next(
        (i for i, l in enumerate(lines) if l.strip().startswith('echo "==>')),
        None,
    )
    if first_exec is None:
        raise AssertionError("前提が崩れている: 実行部分の開始行（==> の echo）が無い")

    preamble = "\n".join(lines[:first_exec])
    ok = not re.search(r"^\s*exit\s+0", preamble, re.M)
    check(ok, "実行部分の先頭（関数・変数定義部）に全検査バイパスの exit 0 が無い",
          preamble)


def test_skip_comment_documents_intent() -> None:
    """スキップ判定を検査単位ごとに独立させる設計意図がコメントに残っている。

    このコメントが消えると、将来の変更で「まとめて 1 条件にする」誘惑に
    歯止めが効かなくなる（docs/knowledge/ci-and-checks.md が禁じる fail-open）。
    """
    text = SCRIPT.read_text(encoding="utf-8")
    ok = "検査の単位ごと" in text
    check(ok, "スキップ判定の設計意図を示すコメントが存在する",
          "「検査の単位ごと」というキーワードが見つからない")


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
