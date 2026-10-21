from tests.conftest import AUTH


def _make_note(client, title="노트", content="Claude와 우주에 대한 메모"):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def _ready(monkeypatch):
    """추출 모델 준비 완료 + 작업자 스레드는 띄우지 않음."""
    from routers import notes as notes_router
    monkeypatch.setattr(notes_router.graph_extraction, "model_ready", lambda: None)
    monkeypatch.setattr(notes_router.graph_worker, "start", lambda: None)


def _graph(nid):
    from db import get_conn
    with get_conn() as conn:
        r = conn.execute("SELECT graph_status, graph_hash FROM notes WHERE id = ?", (nid,)).fetchone()
    return r["graph_status"], r["graph_hash"]


def _set_graph(nid, status, digest):
    from db import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE notes SET graph_status = ?, graph_hash = ? WHERE id = ?", (status, digest, nid))


def test_analyze_all_queues_only_changed_notes(client, monkeypatch):
    from services.graph_extraction import content_hash
    _ready(monkeypatch)
    a = _make_note(client, "a", "본문 A")
    b = _make_note(client, "b", "본문 B")
    c = _make_note(client, "c", "본문 C")
    _make_note(client, "빈노트", "")                      # 내용 없음 → 대상 아님
    _set_graph(a["id"], "done", content_hash("본문 A"))   # 이미 새 형식으로 분석됨
    _set_graph(b["id"], "done", None)                      # 마이그레이션으로 해시가 지워짐
    _set_graph(c["id"], "done", "옛 해시")                 # 본문이 바뀜

    r = client.post("/notes/analyze", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["queued"] == 2
    assert _graph(a["id"]) == ("done", content_hash("본문 A"))
    assert _graph(b["id"])[0] == "pending"
    assert _graph(c["id"])[0] == "pending"


def test_analyze_one_forces_reextract(client, monkeypatch):
    from services.graph_extraction import content_hash
    _ready(monkeypatch)
    n = _make_note(client, "a", "본문")
    _set_graph(n["id"], "done", content_hash("본문"))
    r = client.post(f"/notes/{n['id']}/analyze", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["queued"] == 1
    assert _graph(n["id"]) == ("pending", None)


def test_analyze_without_ready_model_returns_400_and_queues_nothing(client, monkeypatch):
    from routers import notes as notes_router
    monkeypatch.setattr(notes_router.graph_extraction, "model_ready", lambda: "Google API 키가 없습니다")
    n = _make_note(client, "a", "본문")
    _set_graph(n["id"], "done", None)
    for url in ("/notes/analyze", f"/notes/{n['id']}/analyze"):
        r = client.post(url, headers=AUTH)
        assert r.status_code == 400
        assert r.json()["detail"] == "Google API 키가 없습니다"
    assert _graph(n["id"]) == ("done", None)


def test_analyze_one_missing_note_404(client, monkeypatch):
    _ready(monkeypatch)
    r = client.post("/notes/does-not-exist/analyze", headers=AUTH)
    assert r.status_code == 404


def test_extraction_failure_sets_failed_status_and_no_entities(client, monkeypatch):
    from routers import notes as notes_router

    def _raise(content):
        raise Exception("boom")
    monkeypatch.setattr(notes_router.extraction, "extract_entities", _raise)

    r = client.post("/notes", json={"title": "x", "content": "본문"}, headers=AUTH)
    nid = r.json()["id"]
    got = client.get(f"/notes/{nid}", headers=AUTH).json()
    assert got["analysis_status"] == "failed"
    ents = client.get(f"/entities/{nid}", headers=AUTH).json()
    assert ents == []
