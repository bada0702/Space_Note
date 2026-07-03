from tests.conftest import AUTH


def _make_note(client, title="노트", content="Claude와 우주에 대한 메모"):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def test_analyze_all_without_key_returns_400(client):
    r = client.post("/notes/analyze", headers=AUTH)
    assert r.status_code == 400
    assert "API 키" in r.json()["detail"]


def test_analyze_all_queues_failed_and_pending_notes(client, monkeypatch):
    from routers import notes as notes_router
    monkeypatch.setattr(notes_router.anthropic_client, "has_api_key", lambda: True)
    monkeypatch.setattr(
        notes_router.anthropic_client, "extract_entities",
        lambda content: [{"name": "Claude", "type": "개념"}],
    )
    n1 = _make_note(client, "a")          # 생성 시 추출 성공 → analyzed
    _make_note(client, "빈노트", "")       # 내용 없음 → 큐잉 대상 아님

    # n1을 failed로 되돌려 재분석 대상으로 만든다
    from db import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE notes SET analysis_status='failed' WHERE id=?", (n1["id"],))
        conn.execute("DELETE FROM entities WHERE note_id=?", (n1["id"],))

    r = client.post("/notes/analyze", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["queued"] == 1

    # TestClient는 응답 후 BackgroundTasks를 동기 실행 → 상태/엔티티 확인
    got = client.get(f"/notes/{n1['id']}", headers=AUTH).json()
    assert got["analysis_status"] == "analyzed"
    ents = client.get(f"/entities/{n1['id']}", headers=AUTH).json()
    assert [e["name"] for e in ents] == ["Claude"]


def test_analyze_one(client, monkeypatch):
    from routers import notes as notes_router
    monkeypatch.setattr(notes_router.anthropic_client, "has_api_key", lambda: True)
    monkeypatch.setattr(
        notes_router.anthropic_client, "extract_entities",
        lambda content: [{"name": "우주", "type": "개념"}],
    )
    n = _make_note(client)
    r = client.post(f"/notes/{n['id']}/analyze", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["queued"] == 1
    got = client.get(f"/notes/{n['id']}", headers=AUTH).json()
    assert got["analysis_status"] == "analyzed"


def test_analyze_one_missing_note_404(client, monkeypatch):
    from routers import notes as notes_router
    monkeypatch.setattr(notes_router.anthropic_client, "has_api_key", lambda: True)
    r = client.post("/notes/does-not-exist/analyze", headers=AUTH)
    assert r.status_code == 404
