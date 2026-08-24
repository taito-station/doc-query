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

# 追跡されていてはいけないパターン。index DB と評価コーパスの生成物。
FORBIDDEN_GLOBS = ("*.pdf", ".docq/*", ".docq-eval/*")
# .gitignore に必ず載っていてほしい行。
REQUIRED_IGNORES = (".docq/", ".docq-eval/")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


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

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        errors.append(".gitignore が無い")
    else:
        lines = {l.strip() for l in gitignore.read_text(encoding="utf-8").splitlines()}
        for entry in REQUIRED_IGNORES:
            if entry not in lines:
                errors.append(f".gitignore に {entry} が無い")

    for m in errors:
        print(f"error: {m}")
    if errors:
        print(f"\n混入検査: {len(errors)} 件")
        return 1
    print("OK: 実物の文書・生成物の混入なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
