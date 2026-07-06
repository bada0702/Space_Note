from conftest import AUTH
from services.tagparse import extract_tags


def _make_note(client, title, content=""):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


# ── 파싱 규칙 ────────────────────────────────────────────────────────────

def test_extract_tags_finds_inline_hashtags():
    assert extract_tags("오늘 #AIX 클러스터 작업, #HACMP 이슈") == ["AIX", "HACMP"]


def test_extract_tags_ignores_markdown_headings():
    assert extract_tags("# 제목\n## 소제목\n본문") == []


def test_extract_tags_ignores_hash_glued_to_preceding_word():
    assert extract_tags("설정#AIX 는 태그 아님") == []


def test_extract_tags_dedupes_by_normalized_form():
    assert extract_tags("#AIX #aix #AIX") == ["AIX"]


def test_extract_tags_ignores_double_hash():
    assert extract_tags("##더블해시") == []


def test_extract_tags_empty_content():
    assert extract_tags("") == []


# ── 노트 생성/수정/삭제 시 tags 테이블 동기화 ────────────────────────────

def test_create_note_with_hashtag_registers_tag(client):
    _make_note(client, "n", "#AIX 작업 중")
    r = client.get("/tags", headers=AUTH)
    assert r.json() == [{"tag": "AIX", "count": 1}]


def test_update_note_content_resyncs_tags(client):
    note = _make_note(client, "n", "#AIX 작업 중")
    client.patch(f"/notes/{note['id']}", json={"content": "#HACMP 로 변경"}, headers=AUTH)
    r = client.get("/tags", headers=AUTH)
    assert r.json() == [{"tag": "HACMP", "count": 1}]


def test_update_without_content_change_keeps_tags(client):
    note = _make_note(client, "n", "#AIX 작업 중")
    client.patch(f"/notes/{note['id']}", json={"title": "제목만 변경"}, headers=AUTH)
    r = client.get("/tags", headers=AUTH)
    assert r.json() == [{"tag": "AIX", "count": 1}]


def test_delete_note_removes_its_tags(client):
    note = _make_note(client, "n", "#AIX 작업 중")
    client.delete(f"/notes/{note['id']}", headers=AUTH)
    r = client.get("/tags", headers=AUTH)
    assert r.json() == []


# ── /tags, /tags/{tag}/notes ────────────────────────────────────────────

def test_tags_requires_auth(client):
    assert client.get("/tags").status_code == 401


def test_tags_notes_endpoint_lists_notes_with_tag(client):
    a = _make_note(client, "노트A", "#AIX 이야기")
    _make_note(client, "노트B", "관련 없음")
    r = client.get("/tags/AIX/notes", headers=AUTH)
    assert [n["id"] for n in r.json()] == [a["id"]]


def test_tags_notes_endpoint_matches_case_insensitively(client):
    a = _make_note(client, "노트A", "#aix 이야기")
    r = client.get("/tags/AIX/notes", headers=AUTH)
    assert [n["id"] for n in r.json()] == [a["id"]]


# ── 성도 항로(/discoveries/routes) 통합 ──────────────────────────────────

def test_routes_includes_pair_sharing_only_a_tag(client):
    n1 = _make_note(client, "노트1", "#AIX 이야기")
    n2 = _make_note(client, "노트2", "#AIX 다른 이야기")
    n3 = _make_note(client, "노트3", "무관")

    r = client.get("/discoveries/routes", headers=AUTH)
    routes = r.json()
    a, b = sorted([n1["id"], n2["id"]])
    assert any(
        row["note_a"] == a and row["note_b"] == b and row["shared_entities"] == ["AIX"]
        for row in routes
    )
    assert not any(n3["id"] in (row["note_a"], row["note_b"]) for row in routes)


def test_routes_does_not_merge_entity_and_tag_with_same_text(client):
    """엔티티 "AIX"를 가진 노트와 태그 #AIX를 가진 노트는 서로 다른 개념이므로
    이 둘만으로는 항로가 생기면 안 된다(네임스페이스 분리 검증)."""
    from db import get_conn
    import uuid

    entity_note = _make_note(client, "엔티티노트", "")
    tag_note = _make_note(client, "태그노트", "#AIX")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
            "VALUES (?, ?, 'AIX', 'concept', 'aix', 'now')",
            (str(uuid.uuid4()), entity_note["id"]),
        )

    r = client.get("/discoveries/routes", headers=AUTH)
    routes = r.json()
    pair = sorted([entity_note["id"], tag_note["id"]])
    assert not any(
        row["note_a"] == pair[0] and row["note_b"] == pair[1] for row in routes
    )


def test_discoveries_for_note_includes_tag_matches(client):
    n1 = _make_note(client, "노트1", "#AIX 이야기")
    n2 = _make_note(client, "노트2", "#AIX 다른 이야기")

    r = client.get(f"/discoveries?note_id={n1['id']}", headers=AUTH)
    results = r.json()
    assert len(results) == 1
    assert results[0]["note_id"] == n2["id"]
    assert results[0]["shared_entities"] == ["AIX"]
