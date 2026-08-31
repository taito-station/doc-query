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
