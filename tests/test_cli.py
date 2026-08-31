import json
import os
import sqlite3
import sys

import pytest

from docq import cli


def test_index_then_search_with_relative_root(tmp_path, sample_pdf, monkeypatch, capsys):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["index", "--root", "docs"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["indexed"] == 1
    assert out["chunks"] > 0

    rc = cli.main(["search", "--q", "大阪", "--top-k", "3", "--max-tokens", "800"])
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines
    hit = json.loads(lines[0])
    assert hit["pages"] == [2, 2]


def test_index_default_root_is_cwd(tmp_path, sample_pdf, monkeypatch, capsys):
    (tmp_path / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["index"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["indexed"] == 1


def test_index_with_absolute_root_outside_cwd(tmp_path, sample_pdf, monkeypatch,
                                               capsys):
    """`--root /abs/path` from an unrelated cwd must index, not traceback."""
    outside = tmp_path / "outside"
    workdir = tmp_path / "workdir"
    outside.mkdir()
    workdir.mkdir()
    (outside / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(workdir)

    rc = cli.main(["index", "--root", str(outside)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["indexed"] == 1
    assert out["errors"] == []

    rc = cli.main(["search", "--q", "大阪", "--top-k", "3"])
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines
    assert json.loads(lines[0])["path"] == "../outside/sample.pdf"


def test_index_no_prune_keeps_removed_entries(tmp_path, sample_pdf, monkeypatch,
                                               capsys):
    docs = tmp_path / "docs"
    docs.mkdir()
    pdf = docs / "sample.pdf"
    pdf.write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    assert cli.main(["index", "--root", "docs"]) == 0
    capsys.readouterr()

    pdf.unlink()
    assert cli.main(["index", "--root", "docs", "--no-prune"]) == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["pruned"] == 0

    assert cli.main(["stats"]) == 0
    assert json.loads(capsys.readouterr().out.strip())["files"] == 1


def test_index_from_another_directory_is_refused_but_search_is_not(
        tmp_path, sample_pdf, monkeypatch, capsys):
    """The write/read asymmetry, at the CLI layer.

    Writing from a second directory would reinterpret every key, so it is
    refused with a JSON error and rc=1. Reading only echoes keys back, so it
    must keep working — otherwise an index is usable only from the directory
    that built it.
    """
    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / "docs").mkdir(parents=True)
    (b / "docs").mkdir(parents=True)
    (a / "docs" / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    db = str(tmp_path / "shared.sqlite")

    monkeypatch.chdir(a)
    assert cli.main(["--db", db, "index", "--root", "docs"]) == 0
    capsys.readouterr()

    monkeypatch.chdir(b)
    assert cli.main(["--db", db, "index", "--root", "docs"]) == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert "error" in out

    # the entries written from `a` are untouched, and readable from `b`
    assert cli.main(["--db", db, "stats"]) == 0
    assert json.loads(capsys.readouterr().out.strip())["files"] == 1

    assert cli.main(["--db", db, "search", "--q", "大阪", "--top-k", "1"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines
    assert json.loads(lines[0])["path"] == "docs/sample.pdf"


@pytest.mark.skipif(
    sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="needs POSIX permissions and a non-root user",
)
def test_warnings_are_reported_without_failing_the_run(tmp_path, sample_pdf,
                                                        monkeypatch, capsys):
    """The exit-code contract, at the CLI layer.

    An unreadable directory does not resolve on its own, so folding it into
    `errors` would make every later run fail and train the caller to stop
    reading the exit code.
    """
    docs = tmp_path / "docs"
    locked = docs / "locked"
    locked.mkdir(parents=True)
    (locked / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    assert cli.main(["index", "--root", "docs"]) == 0
    capsys.readouterr()

    locked.chmod(0o000)
    try:
        rc = cli.main(["index", "--root", "docs"])
    finally:
        locked.chmod(0o755)

    out = json.loads(capsys.readouterr().out.strip())
    assert rc == 0
    assert out["errors"] == []
    assert out["warnings"]
    assert out["pruned"] == 0


def test_index_reports_no_text(tmp_path, blank_pdf, monkeypatch, capsys):
    """CLI の index 出力に no_text が含まれる。"""
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["index"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["no_text"] == 1
    assert out["skipped"] == 0
    assert any("blank" in f for f in out["no_text_files"])
    assert out["warnings"]


def test_index_missing_root_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["index", "--root", "typo"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["scanned"] == 0
    assert len(out["errors"]) == 1


def test_get_returns_chunk_by_id(tmp_path, sample_pdf, monkeypatch, capsys):
    (tmp_path / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    cli.main(["index"])
    capsys.readouterr()

    cli.main(["search", "--q", "大阪", "--top-k", "1"])
    hit = json.loads(capsys.readouterr().out.strip().splitlines()[0])
    chunk_id = hit["chunk_id"]

    rc = cli.main(["get", "--chunk-id", chunk_id])
    assert rc == 0
    chunk = json.loads(capsys.readouterr().out.strip())
    assert chunk["chunk_id"] == chunk_id
    assert "大阪" in chunk["text"]


def test_get_missing_chunk_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    cli.main(["index"])
    capsys.readouterr()

    rc = cli.main(["get", "--chunk-id", "nonexistent"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert "error" in out


def test_list_returns_all_chunks(tmp_path, sample_pdf, monkeypatch, capsys):
    (tmp_path / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    cli.main(["index"])
    capsys.readouterr()

    rc = cli.main(["list"])
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) >= 1
    for line in lines:
        row = json.loads(line)
        assert "chunk_id" in row


def test_list_respects_limit(tmp_path, sample_pdf, monkeypatch, capsys):
    (tmp_path / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    cli.main(["index"])
    capsys.readouterr()

    rc = cli.main(["list", "--limit", "1"])
    assert rc == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1


def test_stats_reports_counts(tmp_path, sample_pdf, monkeypatch, capsys):
    (tmp_path / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    cli.main(["index"])
    capsys.readouterr()

    rc = cli.main(["stats"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["files"] == 1
    assert out["chunks"] > 0


def test_stats_includes_last_indexed_at(tmp_path, sample_pdf, monkeypatch, capsys):
    (tmp_path / "sample.pdf").write_bytes(sample_pdf.read_bytes())
    monkeypatch.chdir(tmp_path)

    cli.main(["index"])
    capsys.readouterr()

    rc = cli.main(["stats"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert "last_indexed_at" in out
    assert out["last_indexed_at"].endswith("+00:00")


def test_schema_mismatch_exits_nonzero(tmp_path, monkeypatch, capsys):
    db = tmp_path / ".docq" / "index.sqlite"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    conn.close()
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["stats"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert "error" in out
    assert "schema version 999" in out["error"]
