#!/usr/bin/env python3
"""実物の文書ファイルと生成物がコミットされていないことを検査する（REQ-D01-004）。

索引 DB には対象文書の本文が平文で入り、評価コーパスの PDF も生成物である。
どちらもリポジトリへ出さないことが、docs/knowledge/doc-classes.md が D13 / D20 を
n/a で閉じている根拠なので、その境界を機械で押さえる。

終了コード:
  0  混入なし
  1  混入あり、または検査そのものが成立しなかった
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# 追跡されていてはいけないパターン。実物の文書と、index DB / 評価コーパスの
# 生成物。git のパススペックは大小を区別するので `:(icase)` を付ける——
# `*.pdf` だけだと `.PDF` が素通りする。
FORBIDDEN_GLOBS = (
    ":(icase)*.pdf",
    ":(icase)*.docx",
    ":(icase)*.xlsx",
    ":(icase)*.pptx",
    ".docq/*",
    ".docq-eval/*",
)
# 無視されていてほしいパス。`.gitignore` の行と文字列比較すると、`/.docq/` の
# ような等価な記法へ書き換えただけで「無い」と報告する——それは規約ではなく
# 綴りの検査になる。無視されるかどうかは git 自身に答えさせる。
REQUIRED_IGNORED_PATHS = (".docq/probe", ".docq-eval/probe")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # encoding を明示しないとロケール依存になる。core.quotePath=false は
    # 非 ASCII のパスが quote されて読めなくなるのを防ぐ。
    return subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false", *args],
                          capture_output=True, text=True, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    errors: list[str] = []

    for pattern in FORBIDDEN_GLOBS:
        r = git(root, "ls-files", "--", pattern)
        if r.returncode != 0:
            # git が動かないことを「混入なし」と読むのは fail-open。
            errors.append(f"git ls-files が失敗した（{pattern}）: {r.stderr.strip()}")
            continue
        for path in r.stdout.splitlines():
            if path.strip():
                errors.append(f"追跡されている: {path}")

    for probe in REQUIRED_IGNORED_PATHS:
        r = git(root, "check-ignore", "-q", "--no-index", "--", probe)
        if r.returncode == 0:
            continue
        if r.returncode == 1:
            errors.append(f"{probe} が git に無視されない（.gitignore を確認）")
        else:
            # 判定できないことを「無視されている」と読むのは fail-open。
            errors.append(f"git check-ignore が失敗した（{probe}）: {r.stderr.strip()}")

    for m in errors:
        print(f"error: {m}")
    if errors:
        print(f"\n混入検査: {len(errors)} 件")
        return 1
    print("OK: 実物の文書・生成物の混入なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
