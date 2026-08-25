#!/usr/bin/env python3
"""決定ログが append-only であることを検査する。

決定ログは「いつ・なぜそう決めたか」の記録で、後から書き換えると
判断の履歴が失われる。決定を覆すときは新しいエントリを積む——
これが守られているかを、base との差分で見る。

既存エントリの本文を 1 文字でも変えた場合、エントリごと消した場合、
既存エントリの順序を入れ替えた場合、決定ログ節そのものを消した場合を
error にする。**末尾への追記だけが通る。**

比較は「コミット同士」で行う。base 側も現在側も `git show` から読む——
作業ツリーを現在側にすると、未コミットの手元状態が判定に混ざる。

比較対象は `git merge-base <base> HEAD`。base は既定で origin/main、
無ければ main。CI では PR の base を渡す。pre-push は既定のまま使う
（push 先の ref は remote 名の解決が要り、origin/main と実質同じになる）。

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
# エントリ見出しの ID とは衝突しない鍵。節の前書きを表す。
PREAMBLE = "\x00preamble"
FENCE_RE = re.compile(r"^```.*?^```", re.S | re.M)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # encoding を明示する。省くとロケール依存になり、C ロケールの環境では
    # 日本語の決定ログ全文を読む `git show` が UnicodeDecodeError で落ちる。
    # core.quotePath=false は、非 ASCII のパスを git が quote して
    # 後続の `git show ref:path` が「読めない」と誤検知するのを防ぐ。
    return subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false", *args],
                          capture_output=True, text=True, encoding="utf-8")


def mask(text: str) -> str:
    """フェンスとインラインコードを、**同じ長さの空白**へ潰す。

    規約の見本を実データと取り違えないための正規化だが、**長さを変えない**
    のが要点。正規化した文字列そのものを比較すると、フェンスの中身や
    インラインコードを書き換えても append-only 検査を素通りしてしまう。
    長さを保てば、検出はマスク側・比較は生テキスト側に分けられる。
    """
    def blank(m: re.Match) -> str:
        return "".join(c if c == "\n" else " " for c in m.group(0))
    return INLINE_CODE_RE.sub(blank, FENCE_RE.sub(blank, text))


def decision_section(raw: str) -> tuple[str, str] | None:
    """決定ログ節の (生テキスト, マスク) を返す。

    節が無ければ None、マーカーが壊れていれば例外。
    """
    m = mask(raw)
    if m.count(BEGIN) == 0 and m.count(END) == 0:
        return None
    if m.count(BEGIN) != 1 or m.count(END) != 1:
        raise ValueError("decision-log マーカーが対で 1 組になっていない")
    a = m.index(BEGIN) + len(BEGIN)
    b = m.index(END)
    if b < a:
        raise ValueError("decision-log マーカーの順序が逆")
    return raw[a:b], m[a:b]


def split_entries(section: str, masked: str) -> dict[str, str]:
    """見出し ID -> エントリの生テキスト。

    先頭のエントリより前（`## 決定ログ` 見出しと注記）も PREAMBLE として
    比較対象に含める。含めないと、その領域だけは書き換え放題になる。
    """
    out: dict[str, str] = {}
    marks = [(m.group(1), m.start()) for m in ENTRY_RE.finditer(masked)]
    out[PREAMBLE] = section[:marks[0][1] if marks else len(section)].strip()
    for i, (eid, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(section)
        out[eid] = section[start:end].strip()
    return out


def label(eid: str) -> str:
    return "節の前書き" if eid == PREAMBLE else f"エントリ {eid}"


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

    # -z で受ける。改行やクォートを含むパスで一覧が崩れると、読めなかった
    # ものを「対象が無い」と取り違える。
    ls = git(root, "ls-tree", "-r", "--name-only", "-z", ref, TARGET_DIR)
    if ls.returncode != 0:
        print(f"error: {ref} のツリーを読めない: {ls.stderr.strip()}")
        return 1
    base_files = [l for l in ls.stdout.split("\0") if l.endswith(".md")]

    if not base_files:
        # 「base に対象が無い」は初回導入かもしれないが、TARGET_DIR の改名や
        # パスの取り違えでも同じ形になる。区別できるのは HEAD 側だけ——
        # HEAD にも無ければ、それは検査が成立していない。
        head_ls = git(root, "ls-tree", "-r", "--name-only", "-z", "HEAD", TARGET_DIR)
        if head_ls.returncode != 0:
            print(f"error: HEAD のツリーを読めない: {head_ls.stderr.strip()}")
            return 1
        if not [l for l in head_ls.stdout.split("\0") if l.endswith(".md")]:
            print(f"error: {ref} にも HEAD にも {TARGET_DIR} の .md が無い"
                  "（初回導入ではなく、検査が成立していない）")
            return 1
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

        cur_raw = show(root, "HEAD", path)
        if cur_raw is None:
            errors.append(f"{path}: 決定ログを持つ文書が削除されている")
            continue
        try:
            new = decision_section(cur_raw)
        except ValueError as e:
            errors.append(f"{path}: {e}")
            continue
        if new is None:
            errors.append(f"{path}: 決定ログ節ごと削除されている")
            continue

        old_entries = split_entries(*old)
        new_entries = split_entries(*new)
        for eid, body in old_entries.items():
            if eid not in new_entries:
                errors.append(f"{path}: 決定ログの{label(eid)}が削除されている")
            elif new_entries[eid] != body:
                errors.append(f"{path}: 決定ログの{label(eid)}が改変されている"
                              "（覆すときは新しいエントリを積む）")

        # 追記は末尾のみ。既存 ID の並びが新しい側の先頭に保たれていること。
        old_ids = [k for k in old_entries if k != PREAMBLE]
        new_ids = [k for k in new_entries if k != PREAMBLE]
        if all(i in new_ids for i in old_ids) and new_ids[:len(old_ids)] != old_ids:
            errors.append(f"{path}: 決定ログの既存エントリの順序が変わっている"
                          "（既存の間に挿入せず、末尾に積む）")

    for m in errors:
        print(f"error: {m}")
    if errors:
        print(f"\nappend-only 違反: {len(errors)} 件")
        return 1
    print(f"OK: 決定ログは append-only（{ref} と比較、{len(base_files)} 文書）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
