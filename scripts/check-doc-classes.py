#!/usr/bin/env python3
"""docs/knowledge/ の規約適合を検査する。

規約の正本は docs/knowledge/README.md。このスクリプトはそこに書かれた契約を
実行するだけで、規約を定義しない。仕様を変えたら README も同じ PR で直す。

標準ライブラリのみで動く。PyYAML を要求すると CI と pre-push の両方で依存
インストールが要り、「python3 があれば動く」性質を失うため。その制約のために
frontmatter の doc_class / tags はフロースタイル 1 行に強制している。

終了コード:
  0  違反なし
  1  違反あり、または検査が成立しなかった

--warn-only はローカルで全件を眺めるための確認用。違反を警告扱いにして 0 で
終わるが、**検査そのものが成立しない条件は抑止しない**——マーカーの欠落、
検査対象 0 件、表の書式崩れは「違反が無い」ことの証明にならない。
"""
from __future__ import annotations

import argparse
import posixpath
import re
import stat as statmod
import subprocess
import sys
from pathlib import Path

KNOWLEDGE_DIR = Path("docs/knowledge")
ORIGINAL_DOCS_DIR = Path("docs/original-docs")
QA_DIR = Path("docs/qa")
# 一次資料として扱う場所。2 層モデルでは original-docs と qa の両方が
# 一次資料側なので、片方だけを見ると sources の抜け道が残る。
# 末尾の区切りまで含めて比較する——付けないと docs/original-docs-old/ の
# ような別ディレクトリを一次資料と誤認する。
PRIMARY_PREFIXES = (f"{ORIGINAL_DOCS_DIR}/", f"{QA_DIR}/")
# 1 文書に 1 組しか置けないマーカーと、その置き場。二重に置くと 2 組目が、
# 置き場を外れると全体が無検査域になる（読みに行くのは正本 1 本だけなので）。
# 値が None のものは knowledge の外（リポジトリルートの README.md）。
MARKER_HOME = {
    "doc-classes": "knowledge/doc-classes.md",
    "doc-classes-na": "knowledge/doc-classes.md",
    "doc-classes-index": "knowledge/doc-classes.md",
    "req-index": "knowledge/README.md",
    "req-counts": None,
}
SINGLE_PAIR_MARKERS = tuple(MARKER_HOME)
# ルート README の REQ 集計。手書きの集計は必ず腐るので機械で突合する。
REQ_COUNTS_RE = re.compile(r"Confirmed (\d+) 件 / Tentative (\d+) 件")
REGISTRY = KNOWLEDGE_DIR / "doc-classes.md"
CONVENTION = KNOWLEDGE_DIR / "README.md"
# 本文リンクの検査だけはリポジトリルートの 2 本にも及ぶ。文書の改名で
# 入口のリンクが黙って壊れるのを防ぐため。
EXTRA_LINK_TARGETS = (Path("CLAUDE.md"), Path("README.md"))

# doc_class を持たない 2 本。除外されるのは doc_class / tags の必須性と
# 割当索引への掲載だけで、マーカー・書式・sources・stale は適用する。
NO_DOC_CLASS = {"knowledge/README.md", "knowledge/doc-classes.md"}
# frontmatter 自体を持たないのは規約文書 1 本のみ。
NO_FRONTMATTER = {"knowledge/README.md"}

REQ_HEADER = "| REQ-ID | 要件 | 検証手段 | 出典 | status |"
DOC_STATUS = {"Confirmed", "Tentative", "Conflict"}
REQ_STATUS = DOC_STATUS | {"Retired"}
DECISION_STATUS = {"採用", "却下"}
# 「検証手段が書かれていない」と読むべき値。大小文字は問わない。
EMPTY_MEANS = {"", "-", "–", "—", "tbd", "unknown", "n/a",
               "未定", "なし", "未整備"}

FENCE_RE = re.compile(r"^```.*?^```", re.S | re.M)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# `](path "title")` のタイトルはパスの一部ではない。付けたまま実在を見ると
# 必ず「リンク先が実在しない」になる。
LINK_TITLE_RE = re.compile(r'\s+"[^"]*"$')
DECISION_HEADING_RE = re.compile(r"^## 決定ログ$", re.M)
# status は `Superseded by #1-3` のように空白を含む。単一トークンで受けると
# 規約が前提にしている表記が「書式違反」になり、Superseded の許可分岐にも
# 到達しない。
DECISION_ENTRY_RE = re.compile(r"^### (#\d+-\d+): .+ \(\d{4}-\d{2}-\d{2}\) — (\S.*)$", re.M)
DECISION_HEADING_FORMAT_RE = re.compile(r"#\d+-\d+: .+ \(\d{4}-\d{2}-\d{2}\) — \S.*$")
ANY_H3_RE = re.compile(r"^### (.*)$", re.M)
REQ_BLOCK_RE = re.compile(r"<!-- REQ:begin (D\d\d) -->(.*?)<!-- REQ:end \1 -->", re.S)


class Report:
    """error / fatal を集める。

    fatal は「検査が成立していない」——違反の不在を主張できない状態で、
    --warn-only でも抑止しない。
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.fatals: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def fatal(self, msg: str) -> None:
        self.fatals.append(msg)


# --------------------------------------------------------------------------
# ファイルの実在判定
#
# Path.exists() / is_dir() / is_file() は PermissionError を送出して検査を
# 中断させ、os.path.exists() は逆に例外を握り潰して False を返す。どちらも
# 「無い」と「判定できない」を混ぜるので、三値で返して後者は fatal にする。
# --------------------------------------------------------------------------

FOUND, MISSING, UNKNOWN = "found", "missing", "unknown"


def probe(p: Path, rep: Report, where: str) -> str:
    """実在を FOUND / MISSING / UNKNOWN で返す。UNKNOWN は fatal も積む。"""
    try:
        p.stat()
    except FileNotFoundError:
        return MISSING
    except NotADirectoryError:
        # 途中の要素がファイル。「無い」と同じに扱ってよい。
        return MISSING
    except OSError as e:
        rep.fatal(f"{where}: 実在を判定できない: {p} ({e})")
        return UNKNOWN
    return FOUND


def probe_dir(p: Path, rep: Report, where: str) -> str:
    try:
        st = p.stat()
    except FileNotFoundError:
        return MISSING
    except NotADirectoryError:
        return MISSING
    except OSError as e:
        rep.fatal(f"{where}: 実在を判定できない: {p} ({e})")
        return UNKNOWN
    return FOUND if statmod.S_ISDIR(st.st_mode) else MISSING


def listdir(p: Path, rep: Report, where: str) -> set[str] | None:
    """ディレクトリの名前一覧。読めなければ fatal を積んで None。"""
    try:
        return {c.name for c in p.iterdir()}
    except OSError as e:
        rep.fatal(f"{where}: ディレクトリを読めない: {p} ({e})")
        return None


def strip_fences(text: str) -> str:
    """フェンスの中身は規約の見本であって実データではない。行数は保つ。"""
    return FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def for_detection(text: str) -> str:
    """マーカー・表・リンクを『検出』するための正規化。

    インラインコードを潰すのはここだけ。セルの中身（特に検証手段が空扱いか）は
    生のテキストで判定する——剥がしてから見ると `tests/x.py::test_y` と `TBD` が
    どちらも空になり、Confirmed の検査が意味を失う。
    """
    return INLINE_CODE_RE.sub("``", text)


def split_row(line: str) -> list[str] | None:
    """表の 1 行をセルへ分ける。GFM のエスケープ `\\|` は分割しない。"""
    s = line.strip()
    if not s.startswith("|") or not s.endswith("|"):
        return None
    cells, cur, i = [], [], 0
    body = s[1:-1]
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if body[i] == "|":
            cells.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(body[i])
        i += 1
    cells.append("".join(cur).strip())
    return cells


def is_separator(line: str) -> bool:
    # GFM はハイフン 1 本の `|-|` や `|:-:|` も区切り行として認める。
    # 3 本以上を強いると、正当な表が「区切り行でない」で fatal になる。
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells)


def table_rows(block: str, rep: Report, where: str) -> list[list[str]]:
    """マーカーブロックから見出し行・区切り行を除いたデータ行を返す。

    書式が崩れた行は黙って落とさず fatal にする。落とすと一意性検査や
    件数の突合から消えて、違反が通ってしまう。
    """
    # 先頭の `|` を欠いた行は GFM では表として描画されるが、規約では表行と
    # 認めない。黙って落とすと、その行の検査が丸ごと消える。
    for l in block.splitlines():
        s = l.strip()
        if not s.startswith("|") and s.count("|") >= 2:
            rep.fatal(f"{where}: 表の書式が崩れた行がある（先頭が `|` でない）: {s[:40]}")
    lines = [l for l in block.splitlines() if l.strip().startswith("|")]
    if len(lines) < 2:
        rep.fatal(f"{where}: 表の見出し行・区切り行が無い")
        return []
    if not is_separator(lines[1]):
        rep.fatal(f"{where}: 2 行目が区切り行でない")
        return []
    out = []
    for l in lines[2:]:
        cells = split_row(l)
        if cells is None:
            rep.fatal(f"{where}: 表の書式が崩れた行がある: {l[:40]}")
            continue
        out.append(cells)
    return out


def extract_block(text: str, name: str) -> str | None:
    m = re.search(rf"<!-- {name}:begin -->(.*?)<!-- {name}:end -->", text, re.S)
    return m.group(1) if m else None


def parse_frontmatter(raw: str) -> tuple[str | None, str]:
    if not raw.startswith("---\n"):
        return None, raw
    end = raw.find("\n---\n", 3)
    if end == -1:
        return None, raw
    return raw[4:end], raw[end + 5:]


def flow_list(fm: str, key: str) -> list[str] | None:
    m = re.search(rf"^{key}:\s*\[(.*)\]\s*$", fm, re.M)
    if not m:
        return None
    inner = m.group(1).strip()
    return [x.strip() for x in inner.split(",")] if inner else []


def scalar(fm: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*(.+?)\s*$", fm, re.M)
    return m.group(1) if m else None


def block_list(fm: str, key: str) -> list[str]:
    m = re.search(rf"^{key}:\s*\n((?:[ \t]+-\s*\S.*\n?)+)", fm, re.M)
    if not m:
        return []
    return [re.sub(r"^\s*-\s*", "", l).strip()
            for l in m.group(1).splitlines() if l.strip()]


class Doc:
    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.rel = f"knowledge/{path.name}"
        raw = path.read_text(encoding="utf-8")
        self.fm, body = parse_frontmatter(raw)
        self.body = strip_fences(body)
        self.detect = for_detection(self.body)
        self.doc_class = flow_list(self.fm, "doc_class") if self.fm else None
        self.tags = flow_list(self.fm, "tags") if self.fm else None
        self.sources = block_list(self.fm, "sources") if self.fm else []


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # encoding を明示する。省くとロケール依存になり、C ロケールの環境で
    # 日本語を含む出力が UnicodeDecodeError になる。
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8")


# --------------------------------------------------------------------------
# 検査
# --------------------------------------------------------------------------

def check_frontmatter(doc: Doc, rep: Report) -> None:
    if doc.rel in NO_FRONTMATTER:
        if doc.fm is not None:
            rep.error(f"{doc.rel}: frontmatter を持たない規約なのに存在する")
        return
    if doc.fm is None:
        rep.error(f"{doc.rel}: frontmatter が無い")
        return

    st = scalar(doc.fm, "status")
    if st not in DOC_STATUS:
        rep.error(f"{doc.rel}: status の値域外 {st!r}（{sorted(DOC_STATUS)}）")
    if scalar(doc.fm, "kind") != "knowledge":
        rep.error(f"{doc.rel}: kind は knowledge 固定")
    upd = scalar(doc.fm, "updated")
    if not (upd and re.fullmatch(r'"\d{4}-\d{2}-\d{2}"', upd)):
        rep.error(f"{doc.rel}: updated はクォートした YYYY-MM-DD にする（{upd!r}）")
    sha = scalar(doc.fm, "distilled_from_sha")
    if not (sha and re.fullmatch(r'"[0-9a-f]{7,40}"', sha)):
        rep.error(f"{doc.rel}: distilled_from_sha はクォートした短縮 SHA にする")

    if doc.rel in NO_DOC_CLASS:
        if doc.doc_class is not None:
            rep.error(f"{doc.rel}: この文書は doc_class を持たない規約")
    else:
        if doc.doc_class is None:
            rep.error(f"{doc.rel}: doc_class がフロースタイル 1 行で書かれていない")
        if doc.tags is None:
            rep.error(f"{doc.rel}: tags がフロースタイル 1 行で書かれていない")
        if doc.doc_class is not None and doc.doc_class != doc.tags:
            rep.error(f"{doc.rel}: doc_class {doc.doc_class} と "
                      f"tags {doc.tags} が一致しない")
        if doc.doc_class is not None and len(set(doc.doc_class)) != len(doc.doc_class):
            rep.error(f"{doc.rel}: doc_class にクラスの重複がある")
    if not doc.sources:
        rep.error(f"{doc.rel}: sources が空")


def check_sources_exist(doc: Doc, root: Path, rep: Report) -> None:
    for s in doc.sources:
        # 正規形そのものと突き合わせる。`./` `/` の前方一致だけを見ると
        # `../` や途中の `./` が素通りする。
        if s.startswith("/") or s.startswith("../") or s != posixpath.normpath(s):
            rep.error(f"{doc.rel}: sources はリポジトリルート相対の正規形で書く: {s}")
            continue
        target = root / s
        state = probe(target, rep, doc.rel)
        if state == UNKNOWN:
            continue
        if state == MISSING:
            rep.error(f"{doc.rel}: sources が実在しない: {s}")
            continue
        check_case_exact(root, s, rep, f"{doc.rel}: sources")


def check_case_exact(root: Path, rel: str, rep: Report, where: str) -> None:
    """パスの各要素が実体と大文字小文字まで一致するか。

    macOS は大小を区別しないので、最終要素だけ見ると親ディレクトリ側の
    違いが手元を通り、Linux の CI だけが落ちる。
    """
    cur = root
    for part in Path(rel).parts:
        names = listdir(cur, rep, where)
        if names is None:
            return
        if part not in names:
            rep.error(f"{where} の大文字小文字が実体と違う: {rel}")
            return
        cur = cur / part


def check_stale(doc: Doc, root: Path, rep: Report) -> None:
    if not doc.fm:
        return
    sha = (scalar(doc.fm, "distilled_from_sha") or "").strip('"')
    if not sha:
        return
    if git(root, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}").returncode != 0:
        rep.error(f"{doc.rel}: distilled_from_sha {sha} が履歴に無い"
                  "（rebase / shallow clone。比較できないことを『変更なし』と読まない）")
        return
    if git(root, "merge-base", "--is-ancestor", sha, "HEAD").returncode != 0:
        rep.error(f"{doc.rel}: distilled_from_sha {sha} が HEAD から到達できない")
        return
    for s in doc.sources:
        r = git(root, "log", "--format=%H", "-n", "1", f"{sha}..HEAD", "--", s)
        if r.returncode != 0:
            rep.error(f"{doc.rel}: stale 判定に失敗した（{s}）: {r.stderr.strip()}")
            continue
        if r.stdout.strip():
            rep.error(f"{doc.rel}: STALE — {s} が {sha} より後に変更されている。"
                      "本文を見直したうえで distilled_from_sha を進める")


def link_target(raw: str) -> str:
    """`path#frag "title"` からパス部分だけを取り出す。"""
    return LINK_TITLE_RE.sub("", raw.strip()).split("#", 1)[0].strip()


def check_links(rel: str, body: str, base: Path, rep: Report) -> None:
    for m in LINK_RE.finditer(for_detection(body)):
        target = link_target(m.group(1))
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        if probe((base / target).resolve(), rep, rel) == MISSING:
            rep.error(f"{rel}: リンク先が実在しない: {target}")


def check_registry(reg_text: str, docs: list[Doc], rep: Report) -> None:
    declared: dict[str, tuple[str, int]] = {}
    na: set[str] = set()

    block = extract_block(reg_text, "doc-classes")
    if block is None:
        rep.fatal("doc-classes.md: マーカー doc-classes が無い")
    else:
        for cells in table_rows(block, rep, "doc-classes.md クラス一覧"):
            if len(cells) != 4:
                rep.fatal(f"doc-classes.md: クラス一覧は 4 列固定: {cells}")
                continue
            cid, _name, state, cur = cells
            if not re.fullmatch(r"D\d{2}", cid):
                rep.fatal(f"doc-classes.md: クラス ID の形式: {cid}")
                continue
            if state not in ("active", "n/a"):
                rep.error(f"doc-classes.md: {cid} の状態は active / n/a のみ: {state}")
            if not cur.isdigit():
                rep.fatal(f"doc-classes.md: {cid} の現行が数値でない: {cur}")
                continue
            declared[cid] = (state, int(cur))

    na_block = extract_block(reg_text, "doc-classes-na")
    if na_block is None:
        rep.fatal("doc-classes.md: マーカー doc-classes-na が無い")
    else:
        for cells in table_rows(na_block, rep, "doc-classes.md N/A 宣言表"):
            if len(cells) != 3:
                rep.fatal(f"doc-classes.md: N/A 宣言表は 3 列固定: {cells}")
                continue
            cid, reason, resume = cells
            if not reason or not resume:
                rep.error(f"doc-classes.md: {cid} の N/A の理由 / 再開条件が空")
            na.add(cid)

    actual: dict[str, int] = {}
    for d in docs:
        for c in (d.doc_class or []):
            actual[c] = actual.get(c, 0) + 1

    for cid, (state, cur) in declared.items():
        if actual.get(cid, 0) != cur:
            rep.error(f"{cid}: 一覧の現行={cur} だが実態={actual.get(cid, 0)}")
        if state == "n/a" and cid not in na:
            rep.error(f"{cid}: n/a だが N/A 宣言表に行が無い")
        if state == "active" and cid in na:
            rep.error(f"{cid}: active だが N/A 宣言表に行がある")
        if state == "active" and cur == 0:
            rep.error(f"{cid}: active かつ 0 本（運用しないなら n/a で閉じる）")
    for cid in na - set(declared):
        rep.error(f"{cid}: N/A 宣言表にあるが一覧に無い")
    for cid in set(actual) - set(declared):
        rep.error(f"{cid}: 文書が宣言しているがクラス一覧に無い")
    for cid in actual:
        if declared.get(cid, ("", 0))[0] == "n/a":
            rep.error(f"{cid}: n/a のクラスを doc_class に指定した文書がある")

    idx_block = extract_block(reg_text, "doc-classes-index")
    if idx_block is None:
        rep.fatal("doc-classes.md: マーカー doc-classes-index が無い")
    else:
        idx: dict[str, list[str]] = {}
        order: list[str] = []
        for cells in table_rows(idx_block, rep, "doc-classes.md 割当索引"):
            if len(cells) != 2:
                rep.fatal(f"doc-classes.md: 割当索引は 2 列固定: {cells}")
                continue
            doc_path, classes = cells
            if not (classes.startswith("[") and classes.endswith("]")):
                rep.fatal(f"doc-classes.md: 割当索引の doc_class 表記: {classes}")
                continue
            idx[doc_path] = [x.strip() for x in classes[1:-1].split(",") if x.strip()]
            order.append(doc_path)
        if order != sorted(order):
            rep.error("doc-classes.md: 割当索引の行がパス昇順でない")
        expected = {d.rel: d.doc_class for d in docs if d.doc_class is not None}
        for rel, dc in expected.items():
            if rel not in idx:
                rep.error(f"割当索引に欠落: {rel}")
            elif idx[rel] != dc:
                rep.error(f"割当索引の不一致 {rel}: {idx[rel]} != {dc}")
        for rel in set(idx) - set(expected):
            rep.error(f"割当索引に余剰の行: {rel}")


def check_req_tables(docs: list[Doc], root: Path, rep: Report
                     ) -> tuple[set[tuple[str, str]], dict[str, int]]:
    """REQ 表を検査し、実在する (クラス, 文書) の組と status の件数を返す。"""
    seen: dict[str, str] = {}   # ID -> 文書。クラス内グローバルなので横断で集める
    found: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    for doc in docs:
        spans: list[tuple[int, int]] = []
        for m in REQ_BLOCK_RE.finditer(doc.detect):
            cls, block = m.group(1), m.group(2)
            spans.append(m.span())
            found.add((cls, doc.rel))
            if doc.doc_class is None or cls not in doc.doc_class:
                rep.error(f"{doc.rel}: REQ ブロック {cls} がこの文書の doc_class に無い")
            where = f"{doc.rel} の REQ 表 {cls}"
            # セルの中身は生テキストで見る。インラインコードを剥がすと
            # `tests/...::test_x` も `TBD` もどちらも空になる。
            raw_block = _matching_raw_block(doc.body, cls)
            if raw_block is None:
                rep.fatal(f"{where}: 生テキストのブロックを取れない")
                continue
            lines = [l.strip() for l in raw_block.splitlines()
                     if l.strip().startswith("|")]
            if not lines or lines[0] != REQ_HEADER:
                rep.fatal(f"{doc.rel}: REQ 表の見出し行が規約と違う")
                continue
            # 他の表と同じく table_rows に通す。ここだけ自前で [2:] を取ると
            # 区切り行の実在を確かめないまま、先頭のデータ行が黙って
            # 検査対象から外れる。
            rows = table_rows(raw_block, rep, where)
            if not rows:
                rep.fatal(f"{where}: データ行が 0 件（検査が成立していない）")
                continue
            for cells in rows:
                if len(cells) != 5:
                    rep.fatal(f"{doc.rel}: REQ 表は 5 列固定: {cells}")
                    continue
                rid, req, how, src, st = cells
                if not re.fullmatch(rf"REQ-{cls}-\d{{3}}", rid):
                    rep.error(f"{doc.rel}: REQ-ID の形式かクラス部が違う: {rid}")
                elif rid in seen:
                    rep.error(f"REQ-ID の重複: {rid}（{seen[rid]} と {doc.rel}）")
                else:
                    seen[rid] = doc.rel
                if not req:
                    rep.error(f"{rid}: 要件が空")
                if not src:
                    rep.error(f"{rid}: 出典が空")
                if st not in REQ_STATUS:
                    rep.error(f"{rid}: status の値域外 {st!r}")
                else:
                    counts[st] = counts.get(st, 0) + 1
                if st == "Confirmed" and how.strip().strip("`").lower() in EMPTY_MEANS:
                    rep.error(f"{rid}: Confirmed なのに検証手段が空扱い（{how!r}）")
                _check_req_source_in_sources(doc, rid, src, root, rep)

        # マーカー内を「連結した文字列の replace」で消すと、ブロックが 2 つ
        # 以上ある文書では連続部分文字列にならず空振りし、正常な表が
        # 「マーカー外」で fatal になる。位置で、後ろから削る。
        outside = doc.detect
        for a, b in reversed(spans):
            outside = outside[:a] + outside[b:]
        if any(l.strip() == REQ_HEADER for l in outside.splitlines()):
            rep.fatal(f"{doc.rel}: マーカーの外に REQ 表がある")
    return found, counts


def check_req_counts(readme_text: str, counts: dict[str, int], rep: Report) -> None:
    """ルート README の REQ 集計を実数と突合する。

    手書きの集計は必ず腐る。REQ 索引で同じことが起きたのと同型なので、
    同じやり方（マーカーで囲って機械で突合）で塞ぐ。
    """
    where = "README.md の REQ 集計"
    block = extract_block(readme_text, "req-counts")
    if block is None:
        rep.fatal("README.md: マーカー req-counts が無い")
        return
    m = REQ_COUNTS_RE.search(block)
    if m is None:
        rep.fatal(f"{where}: 「Confirmed N 件 / Tentative N 件」の形で書く: {block.strip()[:60]}")
        return
    for label, got in (("Confirmed", int(m.group(1))), ("Tentative", int(m.group(2)))):
        want = counts.get(label, 0)
        if got != want:
            rep.error(f"{where}: {label} が {got} 件と書かれているが実数は {want} 件")


def _matching_raw_block(body: str, cls: str) -> str | None:
    m = re.search(rf"<!-- REQ:begin {cls} -->(.*?)<!-- REQ:end {cls} -->", body, re.S)
    return m.group(1) if m else None


def _check_req_source_in_sources(doc: Doc, rid: str, src: str,
                                 root: Path, rep: Report) -> None:
    """出典が一次資料を名指ししたら sources にも載っていること。

    sources から行を消せば stale も消えるという抜け道の、最小限の封じ。
    一次資料は original-docs だけでなく qa も含む——片方だけを見ると、
    質問票を出典にした REQ で同じ抜け道が開いたままになる。
    """
    for m in LINK_RE.finditer(src):
        target = link_target(m.group(1))
        if target.startswith(("http://", "https://")):
            continue
        resolved = (doc.path.parent / target).resolve()
        try:
            rel = resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if not str(rel).startswith(PRIMARY_PREFIXES):
            continue
        if str(rel) not in doc.sources:
            rep.error(f"{rid}: 出典 {rel} が {doc.rel} の sources に無い")


def check_decision_logs(docs: list[Doc], rep: Report) -> None:
    for doc in docs:
        begins = doc.detect.count("<!-- decision-log:begin -->")
        ends = doc.detect.count("<!-- decision-log:end -->")
        if not DECISION_HEADING_RE.search(doc.detect):
            if begins == 0 and ends == 0:
                continue
            # 見出しの側からしか入らないと、見出しを 1 行消すだけで
            # マーカー内の検査（書式・ID 重複・status）が全部消える。
            rep.fatal(f"{doc.rel}: decision-log マーカーがあるのに "
                      "`## 決定ログ` 見出しが無い")
            continue
        if begins == 0 and ends == 0:
            # マーカーを両方消しても検査が黙って消えないよう、見出しの側で捕まえる。
            rep.fatal(f"{doc.rel}: マーカーの外に決定ログ見出しがある"
                      "（decision-log マーカーで囲む）")
            continue
        if begins != 1 or ends != 1:
            rep.fatal(f"{doc.rel}: decision-log マーカーが対で 1 組になっていない")
            continue
        before, rest = doc.detect.split("<!-- decision-log:begin -->", 1)
        seg, after = rest.split("<!-- decision-log:end -->", 1)
        if DECISION_HEADING_RE.search(before) or DECISION_HEADING_RE.search(after):
            rep.fatal(f"{doc.rel}: マーカーの外に決定ログ見出しがある")
        entries = DECISION_ENTRY_RE.findall(seg)
        if not entries:
            rep.error(f"{doc.rel}: 決定ログ節にエントリが無い")
        ids = [e[0] for e in entries]
        if len(ids) != len(set(ids)):
            rep.error(f"{doc.rel}: 決定ログの見出し ID が重複: {ids}")
        for _id, status in entries:
            if status not in DECISION_STATUS and not status.startswith("Superseded"):
                rep.error(f"{doc.rel}: 決定ログの status の値域外 {status!r}")
        for heading in ANY_H3_RE.findall(seg):
            if not DECISION_HEADING_FORMAT_RE.match(heading):
                rep.error(f"{doc.rel}: 決定ログ見出しの書式: ### {heading[:50]}")


def check_req_index(conv_text: str, found: set[tuple[str, str]], rep: Report) -> None:
    """README の「REQ 表のある文書（索引）」を、実在する REQ マーカーと突合する。

    索引が手書きのままだと、REQ 表を足しても索引が更新されない。番号空間は
    クラス内グローバルなので、索引の欠落はそのまま採番の重複を招く。
    """
    where = "knowledge/README.md REQ 索引"
    block = extract_block(conv_text, "req-index")
    if block is None:
        rep.fatal("knowledge/README.md: マーカー req-index が無い")
        return
    listed: set[tuple[str, str]] = set()
    for cells in table_rows(block, rep, where):
        if len(cells) != 3:
            rep.fatal(f"{where}: 3 列固定: {cells}")
            continue
        cid, doc_cell, scope = cells
        if not re.fullmatch(r"D\d{2}", cid):
            rep.fatal(f"{where}: クラス ID の形式: {cid}")
            continue
        m = LINK_RE.search(doc_cell)
        if m is None:
            rep.fatal(f"{where}: 文書欄はリンクで書く: {doc_cell}")
            continue
        if not scope:
            rep.error(f"{where}: {cid} の範囲が空")
        listed.add((cid, f"knowledge/{link_target(m.group(1))}"))
    for cid, rel in sorted(found - listed):
        rep.error(f"REQ 索引に欠落: {rel} の {cid}")
    for cid, rel in sorted(listed - found):
        rep.error(f"REQ 索引に余剰の行: {rel} の {cid}")


def check_marker_pairs(rel: str, text: str, rep: Report) -> None:
    """1 組しか置けないマーカーが、本当に 1 組かを見る。

    `extract_block` は最初の対しか拾わないので、二重に置くと 2 組目が
    黙って無検査域になる。
    """
    for name in SINGLE_PAIR_MARKERS:
        b = text.count(f"<!-- {name}:begin -->")
        e = text.count(f"<!-- {name}:end -->")
        if b > 1 or e > 1 or b != e:
            rep.fatal(f"{rel}: マーカー {name} が対で 1 組になっていない"
                      f"（begin {b} / end {e}）")


def check_marker_placement(docs: list[Doc], rep: Report) -> None:
    """正本以外の文書に単数マーカーが置かれていないこと。

    検査は正本 1 本しか読まないので、他の文書に置かれた同じマーカーは
    黙って無検査域になる——正本と食い違う第 2 の一覧がそこに残りうる。
    """
    for doc in docs:
        for name, home in MARKER_HOME.items():
            if (f"<!-- {name}:begin -->" not in doc.detect
                    and f"<!-- {name}:end -->" not in doc.detect):
                continue
            if doc.rel != home:
                where = home or "リポジトリルートの README.md"
                rep.fatal(f"{doc.rel}: マーカー {name} は {where} にしか置けない")


def check_layout(root: Path, rep: Report) -> None:
    """knowledge のサブディレクトリに .md が無いこと。

    `rglob` は走査中の PermissionError を握り潰すので使わない。読めない
    ディレクトリがあると「サブディレクトリに .md は無い」と報告してしまう。
    """
    kdir = root / KNOWLEDGE_DIR
    stack = [kdir]
    while stack:
        cur = stack.pop()
        names = listdir(cur, rep, str(KNOWLEDGE_DIR))
        if names is None:
            continue
        for name in sorted(names):
            child = cur / name
            state = probe_dir(child, rep, str(KNOWLEDGE_DIR))
            if state == UNKNOWN:
                continue
            if state == FOUND:
                stack.append(child)
            elif cur != kdir and name.endswith(".md"):
                rep.error(f"{child.relative_to(root)}: knowledge のサブディレクトリに "
                          ".md を置かない（1 階層下げるだけで無検査域になる）")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="リポジトリルート（既定: .）")
    ap.add_argument("--warn-only", action="store_true",
                    help="違反を警告扱いにして 0 で終わる（検査不成立は抑止しない）")
    ap.add_argument("--no-stale", action="store_true",
                    help="stale 検査を省く（git の無い環境向け）")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    rep = Report()

    kdir = root / KNOWLEDGE_DIR
    if probe_dir(kdir, rep, str(KNOWLEDGE_DIR)) != FOUND:
        rep.fatal(f"{KNOWLEDGE_DIR} が無い")
        return _report(rep, args.warn_only)

    check_layout(root, rep)
    docs = [Doc(p, root) for p in sorted(kdir.glob("*.md"))]
    if not docs:
        rep.fatal("検査対象の文書が 0 件（違反が無いのではなく、検査が成立していない）")
        return _report(rep, args.warn_only)

    for doc in docs:
        check_frontmatter(doc, rep)
        check_sources_exist(doc, root, rep)
        check_links(doc.rel, doc.body, doc.path.parent, rep)
        if not args.no_stale:
            check_stale(doc, root, rep)

    reg = root / REGISTRY
    reg_state = probe(reg, rep, str(REGISTRY))
    if reg_state == MISSING:
        rep.fatal(f"{REGISTRY} が無い（クラス定義の正本）")
    elif reg_state == FOUND:
        reg_text = strip_fences(reg.read_text(encoding="utf-8"))
        check_marker_pairs(str(REGISTRY), reg_text, rep)
        check_registry(reg_text, docs, rep)

    check_marker_placement(docs, rep)
    req_found, req_counts = check_req_tables(docs, root, rep)
    check_decision_logs(docs, rep)

    conv = root / CONVENTION
    conv_state = probe(conv, rep, str(CONVENTION))
    if conv_state == MISSING:
        rep.fatal(f"{CONVENTION} が無い（規約の正本）")
    elif conv_state == FOUND:
        conv_text = strip_fences(conv.read_text(encoding="utf-8"))
        check_marker_pairs(str(CONVENTION), conv_text, rep)
        check_req_index(conv_text, req_found, rep)

    for extra in EXTRA_LINK_TARGETS:
        p = root / extra
        state = probe(p, rep, str(extra))
        if state == MISSING:
            # 無いことを「検査するものが無い」と読むと、入口の改名で
            # リンク検査が黙って 0 件になる。
            rep.fatal(f"{extra} が無い（入口リンクの検査が成立しない）")
        elif state == FOUND:
            text = strip_fences(p.read_text(encoding="utf-8"))
            check_links(str(extra), text, root, rep)
            if extra.name == "README.md":
                check_marker_pairs(str(extra), text, rep)
                check_req_counts(text, req_counts, rep)

    return _report(rep, args.warn_only)


def _report(rep: Report, warn_only: bool) -> int:
    for m in rep.errors:
        print(f"{'warning' if warn_only else 'error'}: {m}")
    for m in rep.fatals:
        # 検査が成立していない。--warn-only でも抑止しない。
        print(f"error: {m}")

    if rep.fatals:
        print(f"\n検査が成立していない: {len(rep.fatals)} 件")
        return 1
    if rep.errors and not warn_only:
        print(f"\n違反: {len(rep.errors)} 件")
        return 1
    if rep.errors:
        print(f"\n違反 {len(rep.errors)} 件（--warn-only のため 0 で終了）")
        return 0
    print("OK: 違反なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
