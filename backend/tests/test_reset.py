from config import settings
from conftest import AUTH
from db import get_conn


def _seed(client):
    cat = client.post("/categories", json={"name": "은하1"}, headers=AUTH).json()
    client.post("/notes", json={"title": "노트1", "category_id": cat["id"], "content": "#태그 본문"}, headers=AUTH)
    client.post("/notes", json={"title": "노트2", "content": "본문"}, headers=AUTH)
    client.put("/conversations/c1", json={"model": "m", "messages": [{"role": "user", "content": "안녕"}]}, headers=AUTH)
    vault = settings.VAULT_DIR
    (vault / "은하1").mkdir(exist_ok=True)
    (vault / "은하1" / "옛노트.md").write_text("x", encoding="utf-8")
    (vault / "attachments").mkdir(exist_ok=True)
    (vault / "attachments" / "a.png").write_bytes(b"png")
    (vault / "keep.txt").write_text("남겨야 함", encoding="utf-8")
    with get_conn() as conn:
        conn.execute("UPDATE settings SET google_api_key = 'k' WHERE id = 1")


def test_reset_requires_auth(client):
    assert client.post("/reset", json={"confirm": "초기화"}).status_code == 401


def test_reset_preview_counts(client):
    _seed(client)
    r = client.get("/reset/preview", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == 2
    assert body["categories"] == 1
    assert body["conversations"] == 1
    assert body["files"] >= 4  # 노트 .md 2개 + 옛노트.md + 첨부 1개


def test_reset_wrong_confirm_does_nothing(client):
    _seed(client)
    r = client.post("/reset", json={"confirm": "아니"}, headers=AUTH)
    assert r.status_code == 400
    assert client.get("/reset/preview", headers=AUTH).json()["notes"] == 2


def test_reset_deletes_everything_but_settings(client):
    _seed(client)
    r = client.post("/reset", json={"confirm": "초기화"}, headers=AUTH)
    assert r.status_code == 200

    with get_conn() as conn:
        for table in ("notes", "categories", "entities", "tags", "routes", "concepts",
                      "concept_aliases", "note_concepts", "relations",
                      "conversations", "conversation_messages"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
        assert conn.execute("SELECT google_api_key FROM settings").fetchone()[0] == "k"

    vault = settings.VAULT_DIR
    assert vault.exists()
    assert list(vault.rglob("*.md")) == []
    assert not (vault / "attachments").exists()
    assert not (vault / "은하1").exists()  # 비게 된 은하 폴더는 정리
    assert (vault / "keep.txt").read_text(encoding="utf-8") == "남겨야 함"  # 노트와 무관한 파일은 유지
