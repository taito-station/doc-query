import json

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


def test_index_missing_root_exits_nonzero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["index", "--root", "typo"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out.strip())
    assert out["scanned"] == 0
    assert len(out["errors"]) == 1
