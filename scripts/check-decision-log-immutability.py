#!/usr/bin/env python3
"""決定ログが append-only であることを検査する。

決定ログは「いつ・なぜそう決めたか」の記録で、後から書き換えると
判断の履歴が失われる。決定を覆すときは新しいエントリを積む——
これが守られているかを、base との差分で見る。

既存エントリの本文を 1 文字でも変えた場合、エントリごと消した場合、
決定ログ節そのものを消した場合を error にする。**末尾への追記だけが通る。**

比較対象は `git merge-base <base> HEAD`。base は既定で origin/main、
無ければ main。CI では PR の base、pre-push では push 先を渡す。

終了コード:
  0  append-only が保たれている
  1  改変・削除がある、または比較そのものが成立しなかった
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

TARGET_DIR = "docs/knowledge"
BEGIN = "<!-- decision-log:begin -->"
END = "<!-- decision-log:end -->"
ENTRY_RE = re.compile(r"^### (#\d+-\d+):", re.M)
FENCE_RE = re.compile(r"^```.*?^```", re.S | re.M)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def normalize(text: str) -> str:
    """規約の見本を実データと取り違えないための正規化。

    check-doc-classes.py と同じ扱いにする——フェンスの中身は無視し、
    マーカーの検出ではインラインコードも潰す。
    """
    text = FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return INLINE_CODE_RE.sub("``", text)


def decision_section(raw: str) -> str | None:
    """決定ログ節の中身。節が無ければ None、マーカーが壊れていれば例外。"""
    det = normalize(raw)
    if det.count(BEGIN) == 0 and det.count(END) == 0:
        return None
    if det.count(BEGIN) != 1 or det.count(END) != 1:
        raise ValueError("decision-log マーカーが対で 1 組になっていない")
    return det.split(BEGIN, 1)[1].split(END, 1)[0]


def split_entries(section: str) -> dict[str, str]:
    """見出し ID -> エントリ本文。"""
    out: dict[str, str] = {}
    marks = [(m.group(1), m.start()) for m in ENTRY_RE.finditer(section)]
    for i, (eid, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(section)
        out[eid] = section[start:end].strip()
    return out


def show(root: Path, ref: str, path: str) -> str | None:
    r = git(root, "show", f"{ref}:{path}")
    return r.stdout if r.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--base", default=None,
                    help="比較の基準（既定: origin/main、無ければ main）")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    base = args.base
    if base is None:
        for cand in ("origin/main", "main"):
            if git(root, "rev-parse", "--verify", "--quiet", cand).returncode == 0:
                base = cand
                break
    if base is None:
        # 比較できないことを「違反なし」と読むのは fail-open。
        print("error: 比較の基準が見つからない（origin/main / main のいずれも無い）")
        return 1

    mb = git(root, "merge-base", base, "HEAD")
    if mb.returncode != 0:
        print(f"error: merge-base({base}, HEAD) を求められない: {mb.stderr.strip()}")
        return 1
    ref = mb.stdout.strip()

    ls = git(root, "ls-tree", "-r", "--name-only", ref, TARGET_DIR)
    if ls.returncode != 0:
        print(f"error: {ref} のツリーを読めない: {ls.stderr.strip()}")
        return 1
    base_files = [l for l in ls.stdout.splitlines() if l.endswith(".md")]

    if not base_files:
        # base に対象が無い＝この PR が最初の導入。検査対象が無いのは正常。
        print(f"OK: {ref} には {TARGET_DIR} が無い（初回導入）")
        return 0

    errors: list[str] = []
    for path in base_files:
        old_raw = show(root, ref, path)
        if old_raw is None:
            errors.append(f"{path}: {ref} 側を読めない")
            continue
        try:
            old = decision_section(old_raw)
        except ValueError as e:
            errors.append(f"{path}: {ref} 側の {e}")
            continue
        if old is None:
            continue   # base 側に決定ログが無い文書は対象外

        cur_path = root / path
        if not cur_path.exists():
            errors.append(f"{path}: 決定ログを持つ文書が削除されている")
            continue
        try:
            new = decision_section(cur_path.read_text(encoding="utf-8"))
        except ValueError as e:
            errors.append(f"{path}: {e}")
            continue
        if new is None:
            errors.append(f"{path}: 決定ログ節ごと削除されている")
            continue

        old_entries = split_entries(old)
        new_entries = split_entries(new)
        for eid, body in old_entries.items():
            if eid not in new_entries:
                errors.append(f"{path}: 決定ログのエントリ {eid} が削除されている")
            elif new_entries[eid] != body:
                errors.append(f"{path}: 決定ログのエントリ {eid} が改変されている"
                              "（覆すときは新しいエントリを積む）")

    for m in errors:
        print(f"error: {m}")
    if errors:
        print(f"\nappend-only 違反: {len(errors)} 件")
        return 1
    print(f"OK: 決定ログは append-only（{ref} と比較、{len(base_files)} 文書）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
