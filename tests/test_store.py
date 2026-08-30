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
