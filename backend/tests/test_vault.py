import importlib


def _vault(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    from config import settings
    settings.reload()
    vault = importlib.import_module("services.vault")
    return vault


def test_safe_filename_strips_traversal(monkeypatch, tmp_path):
    vault = _vault(monkeypatch, tmp_path)
    assert vault.safe_filename("../../etc/passwd") == "etcpasswd"
    assert vault.safe_filename("normal title") == "normal title"
    assert vault.safe_filename("a/b\\c") == "abc"
    assert vault.safe_filename("") == "untitled"


def test_write_md_creates_file_inside_vault(monkeypatch, tmp_path):
    vault = _vault(monkeypatch, tmp_path)
    path = vault.write_md("My Note", "hello world", tags=["x"])
    assert path.endswith("My Note.md")
    from config import settings
    assert str(settings.VAULT_DIR) in path
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "hello world" in text
    assert "tags:" in text  # frontmatter 존재
