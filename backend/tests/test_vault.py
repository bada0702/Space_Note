import importlib
from pathlib import Path


def _vault(monkeypatch, tmp_path):
    # DB_PATH도 격리하지 않으면 reload()가 실제 spacenote.db의 저장된 vault_dir로
    # 덮어써서 테스트가 진짜 vault 디렉토리에 파일을 쓰게 된다.
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
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


def test_write_md_with_existing_path_stays_in_same_subfolder(monkeypatch, tmp_path):
    """기존 노트(하위 폴더에 위치)를 수정하면 같은 폴더에 그대로 저장되어야 한다."""
    vault = _vault(monkeypatch, tmp_path)
    from config import settings
    sub = settings.VAULT_DIR / "카테고리"
    sub.mkdir(parents=True)
    original = sub / "노트.md"
    original.write_text("---\ntags: []\n---\n\n old", encoding="utf-8")

    path = vault.write_md("노트", "updated", tags=[], existing_path=str(original))
    assert path == str(original)
    assert "updated" in original.read_text(encoding="utf-8")


def test_write_md_with_existing_path_keeps_original_filename_even_if_unsafe_chars(monkeypatch, tmp_path):
    """safe_filename()이 원본 파일명(점 등)과 다른 결과를 내더라도, 파일이 아직 있으면
    새 이름으로 다시 만들지 않고 기존 파일 그대로 덮어써야 한다 (아니면 파일이 중복 생성됨)."""
    vault = _vault(monkeypatch, tmp_path)
    from config import settings
    sub = settings.VAULT_DIR / "카테고리"
    sub.mkdir(parents=True)
    # 제목에 safe_filename이 제거하는 문자(.)가 있는, 외부(Obsidian 등)에서 가져온 파일 상황
    original = sub / "v1.2.3 노트.md"
    original.write_text("old", encoding="utf-8")

    path = vault.write_md("v1.2.3 노트", "updated", tags=[], existing_path=str(original))

    assert path == str(original)
    assert "updated" in original.read_text(encoding="utf-8")
    assert list(sub.glob("*.md")) == [original]  # 새 파일이 옆에 더 생기면 안 됨


def test_write_md_after_rename_deletes_old_and_creates_new_name_in_same_folder(monkeypatch, tmp_path):
    """제목 변경(rename)은 호출자가 기존 파일을 먼저 지운 뒤 write_md를 호출한다 —
    이 경우 같은 폴더에 새 제목 기준 파일명으로 새로 생성되어야 한다."""
    vault = _vault(monkeypatch, tmp_path)
    from config import settings
    sub = settings.VAULT_DIR / "카테고리"
    sub.mkdir(parents=True)
    original = sub / "옛 제목.md"
    original.write_text("old", encoding="utf-8")

    vault.delete_md(str(original))  # notes.py의 rename 흐름과 동일
    path = vault.write_md("새 제목", "content", tags=[], existing_path=str(original))

    assert Path(path).parent == sub
    assert Path(path).name == "새 제목.md"
    assert not original.exists()


def test_write_md_without_existing_path_defaults_to_vault_root(monkeypatch, tmp_path):
    vault = _vault(monkeypatch, tmp_path)
    from config import settings
    sub = settings.VAULT_DIR / "카테고리"
    sub.mkdir(parents=True)
    (sub / "노트.md").write_text("old", encoding="utf-8")

    path = vault.write_md("노트", "new note content", tags=[])
    assert Path(path).parent == settings.VAULT_DIR


def test_delete_md_removes_file_at_given_path(monkeypatch, tmp_path):
    vault = _vault(monkeypatch, tmp_path)
    from config import settings
    sub = settings.VAULT_DIR / "카테고리"
    sub.mkdir(parents=True)
    target = sub / "노트.md"
    target.write_text("content", encoding="utf-8")

    vault.delete_md(str(target))
    assert not target.exists()


def test_sync_db_with_vault_scans_subfolders_recursively(monkeypatch, tmp_path):
    vault = _vault(monkeypatch, tmp_path)
    from config import settings
    from db import init_db
    init_db()

    sub = settings.VAULT_DIR / "개발_코딩"
    sub.mkdir(parents=True)
    (sub / "재귀 테스트.md").write_text("---\ntags: []\n---\n\n하위 폴더 노트", encoding="utf-8")

    vault.sync_db_with_vault()

    from db import get_conn
    with get_conn() as conn:
        rows = conn.execute("SELECT title, content, path, category_id FROM notes").fetchall()
        categories = conn.execute("SELECT id, name FROM categories").fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "재귀 테스트"
    assert "하위 폴더 노트" in rows[0]["content"]
    assert "개발_코딩" in rows[0]["path"]
    assert len(categories) == 1
    assert categories[0]["name"] == "개발_코딩"
    assert rows[0]["category_id"] == categories[0]["id"]


def test_sync_db_with_vault_top_level_file_has_no_category(monkeypatch, tmp_path):
    """vault 최상위에 바로 있는 파일(하위 폴더 없음)은 카테고리를 지정하지 않는다."""
    vault = _vault(monkeypatch, tmp_path)
    from config import settings
    from db import init_db
    init_db()

    settings.VAULT_DIR.mkdir(parents=True, exist_ok=True)
    (settings.VAULT_DIR / "루트 노트.md").write_text("---\ntags: []\n---\n\n루트", encoding="utf-8")

    vault.sync_db_with_vault()

    from db import get_conn
    with get_conn() as conn:
        row = conn.execute("SELECT category_id FROM notes WHERE title = ?", ("루트 노트",)).fetchone()
        categories = conn.execute("SELECT * FROM categories").fetchall()
    assert row["category_id"] is None
    assert len(categories) == 0


def test_sync_db_with_vault_does_not_overwrite_manually_set_category(monkeypatch, tmp_path):
    """이미 카테고리가 지정된 노트는 폴더가 달라도 재동기화 때 덮어쓰지 않는다(수동 지정 보존)."""
    vault = _vault(monkeypatch, tmp_path)
    from config import settings
    from db import init_db
    import uuid
    init_db()

    sub = settings.VAULT_DIR / "개발_코딩"
    sub.mkdir(parents=True)
    (sub / "노트.md").write_text("---\ntags: []\n---\n\n내용", encoding="utf-8")
    vault.sync_db_with_vault()

    from db import get_conn
    with get_conn() as conn:
        other_cid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO categories (id, name, color, sort_order, created_at) VALUES (?, '수동카테고리', NULL, 0, '2024-01-01')",
            (other_cid,),
        )
        conn.execute("UPDATE notes SET category_id = ? WHERE title = '노트'", (other_cid,))

    vault.sync_db_with_vault()  # 파일 내용은 그대로라 재동기화해도 category_id가 안 바뀌어야 함

    with get_conn() as conn:
        row = conn.execute("SELECT category_id FROM notes WHERE title = '노트'").fetchone()
    assert row["category_id"] == other_cid
