import sqlite3

import pytest

from docq import store


def test_open_store_creates_gitignore(tmp_path):
    """open_store は .gitignore を自動生成する。"""
    db = tmp_path / ".docq" / "index.sqlite"
    conn = store.open_store(db)
    conn.close()
    gitignore = tmp_path / ".docq" / ".gitignore"
    assert gitignore.exists()
    assert "*" in gitignore.read_text(encoding="utf-8")


def test_open_store_does_not_overwrite_existing_gitignore(tmp_path):
    """既存の .gitignore は上書きしない。"""
    docq_dir = tmp_path / ".docq"
    docq_dir.mkdir()
    gitignore = docq_dir / ".gitignore"
    gitignore.write_text("custom\n", encoding="utf-8")
    conn = store.open_store(docq_dir / "index.sqlite")
    conn.close()
    assert gitignore.read_text(encoding="utf-8") == "custom\n"


def test_open_store_accepts_matching_schema_version(tmp_path):
    """user_version が SCHEMA_VERSION と一致すれば正常に開ける。"""
    db = tmp_path / "index.sqlite"
    conn = store.open_store(db)
    conn.close()
    conn2 = store.open_store(db)
    v = conn2.execute("PRAGMA user_version").fetchone()[0]
    conn2.close()
    assert v == store.SCHEMA_VERSION


def test_open_store_raises_on_schema_version_mismatch(tmp_path):
    """user_version が SCHEMA_VERSION と異なれば SchemaMismatch を送出する。"""
    db = tmp_path / "index.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    conn.close()
    with pytest.raises(store.SchemaMismatch, match="schema version 999"):
        store.open_store(db)


def test_get_chunks_by_ids_returns_matching_rows(tmp_path):
    conn = store.open_store(tmp_path / "index.sqlite")
    store.upsert_file(conn, "a.pdf", sha1="aaa", mtime=0.0, size_bytes=100)
    store.insert_chunks(conn, [
        ("c1", "a.pdf", "p.1", 1, 1, 10, "hello", 0, 1, "[]"),
        ("c2", "a.pdf", "p.2", 2, 2, 10, "world", 0, 1, "[]"),
    ])
    result = store.get_chunks_by_ids(conn, ["c1", "c2"])
    assert set(result.keys()) == {"c1", "c2"}
    assert result["c1"]["text"] == "hello"
    assert result["c2"]["text"] == "world"


def test_get_chunks_by_ids_missing_id_is_absent(tmp_path):
    conn = store.open_store(tmp_path / "index.sqlite")
    store.upsert_file(conn, "a.pdf", sha1="aaa", mtime=0.0, size_bytes=100)
    store.insert_chunks(conn, [
        ("c1", "a.pdf", "p.1", 1, 1, 10, "hello", 0, 1, "[]"),
    ])
    result = store.get_chunks_by_ids(conn, ["c1", "missing"])
    assert "c1" in result
    assert "missing" not in result


def test_get_chunks_by_ids_empty_list_returns_empty(tmp_path):
    conn = store.open_store(tmp_path / "index.sqlite")
    assert store.get_chunks_by_ids(conn, []) == {}
