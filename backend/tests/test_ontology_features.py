"""naviswiki에서 이식한 온톨로지 기능 — 근거 문장, 추출 실패 사유, 잔여 행 정리,
항로 거부, 경로 탐색, 별자리 관계도, 노트 즉시 추출."""
import json

from tests.conftest import AUTH
from tests.test_graph import _count, _graph_fixture, _note, _store


def _entity(note_id, name):
    import uuid
    from db import get_conn
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
            "VALUES (?, ?, ?, 'concept', ?, 'now')",
            (str(uuid.uuid4()), note_id, name, name.lower()),
        )


# ── 근거 문장 ───────────────────────────────────────────────

def test_parse_graph_keeps_evidence_only_when_quoted_from_note():
    from services import graph_extraction as ge
    source = "FAISS는   벡터 검색에\nEmbedding을 사용한다. 끝."
    raw = {
        "nodes": [{"name": "FAISS", "kind": "instance"}, {"name": "Embedding", "kind": "instance"},
                  {"name": "벡터DB", "kind": "class"}],
        "edges": [
            {"s": "FAISS", "p": "사용한다", "o": "Embedding", "q": "FAISS는 벡터 검색에 Embedding을 사용한다."},
            {"s": "FAISS", "p": "인스턴스이다", "o": "벡터DB", "q": "본문에 없는 문장"},
        ],
    }
    g = ge.parse_graph(json.dumps(raw, ensure_ascii=False), source)
    ev = {(r["s"], r["p"]): r["evidence"] for r in g["relations"]}
    assert ev[("faiss", "사용한다")] == "FAISS는 벡터 검색에 Embedding을 사용한다."
    assert ev[("faiss", "인스턴스이다")] is None
    # 본문을 주지 않으면 근거를 확인할 수 없으므로 남기지 않는다
    assert all(r["evidence"] is None for r in ge.parse_graph(json.dumps(raw, ensure_ascii=False))["relations"])


def test_process_note_stores_evidence(client, monkeypatch):
    from services import graph_extraction as ge
    n = _note(client, "노트", "Docker는 Linux 커널 기능을 사용한다.")
    monkeypatch.setattr(ge, "call_model", lambda content: json.dumps({
        "nodes": [{"name": "Docker", "kind": "instance"}, {"name": "Linux", "kind": "instance"}],
        "edges": [{"s": "Docker", "p": "사용한다", "o": "Linux", "q": "Docker는 Linux 커널 기능을 사용한다."}],
    }))
    assert ge.process_note(n["id"]) == "done"
    assert _count("SELECT COUNT(*) FROM relations WHERE evidence = ?", "Docker는 Linux 커널 기능을 사용한다.") == 1


# ── 추출 실패 사유 ─────────────────────────────────────────

def test_failure_reason_is_stored_and_cleared(client, monkeypatch):
    import httpx
    from services import graph_extraction as ge
    n = _note(client, "노트", "본문")

    def _quota(content):
        req = httpx.Request("POST", "https://example.invalid")
        raise httpx.HTTPStatusError("quota", request=req, response=httpx.Response(429, request=req))
    monkeypatch.setattr(ge, "call_model", _quota)
    assert ge.process_note(n["id"]) == "failed"
    assert client.get(f"/notes/{n['id']}", headers=AUTH).json()["graph_error"] == "Google API 사용 한도를 초과했습니다"
    status = client.get("/graph/status", headers=AUTH).json()
    assert status["failures"] == [{"id": n["id"], "title": "노트", "error": "Google API 사용 한도를 초과했습니다"}]

    monkeypatch.setattr(ge, "call_model", lambda content: "깨진 응답")
    ge.process_note(n["id"])
    assert client.get(f"/notes/{n['id']}", headers=AUTH).json()["graph_error"] == "모델 응답 형식이 올바르지 않습니다"

    monkeypatch.setattr(ge, "call_model", lambda content: json.dumps(
        {"nodes": [{"name": "Redis", "kind": "instance", "type": "도구", "weight": 3}], "edges": []}))
    assert ge.process_note(n["id"]) == "done"
    assert client.get(f"/notes/{n['id']}", headers=AUTH).json()["graph_error"] is None


def test_failure_reason_for_ollama(client, monkeypatch):
    import httpx
    from services import graph_extraction as ge
    monkeypatch.setattr(ge, "graph_model", lambda: "ollama:gemma")
    req = httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
    err = httpx.HTTPStatusError("nf", request=req, response=httpx.Response(404, request=req))
    assert "Ollama" in ge.describe_failure(err)
    assert ge.describe_failure(httpx.ConnectError("refused")) == "추출 모델 서버에 연결할 수 없습니다"


# ── 삭제된 노트의 잔여 행 정리 ──────────────────────────────

def test_purge_dangling_rows_removes_deleted_notes_graph(client):
    from db import get_conn
    from services import graph_extraction as ge
    keep, gone = _note(client, "남음", "본문"), _note(client, "지워짐", "본문")
    _store(keep["id"], [("Kept", "도구", 2, [])])
    _store(gone["id"], [("Ghost", "도구", 2, []), ("Kept", "도구", 1, [])], [("Ghost", "관련있다", "Kept")])
    _entity(gone["id"], "유령")
    with get_conn() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (gone["id"],))  # 앱 밖에서 노트 행만 삭제
        removed = ge.purge_dangling_rows(conn)
    assert removed["note_concepts"] == 2 and removed["relations"] == 1 and removed["entities"] == 1
    assert removed["concepts"] == 1
    assert _count("SELECT COUNT(*) FROM concepts WHERE name = 'Kept'") == 1


def test_vault_sync_deleting_missing_file_clears_graph(client):
    from pathlib import Path
    from services.vault import sync_db_with_vault
    keep, gone = _note(client, "남는 파일", "본문"), _note(client, "사라질 파일", "본문")
    _store(gone["id"], [("Ghost", "도구", 2, [])])
    Path(gone["path"]).unlink()
    sync_db_with_vault()
    assert _count("SELECT COUNT(*) FROM notes WHERE id = ?", gone["id"]) == 0
    assert _count("SELECT COUNT(*) FROM note_concepts WHERE note_id = ?", gone["id"]) == 0


# ── 항로: 지식 그래프 근거 (naviswiki 방식) ────────────────

def _route(routes, x, y):
    a, b = sorted([x, y])
    return next((r for r in routes if r["note_a"] == a and r["note_b"] == b), None)


def test_routes_link_notes_by_shared_concept_and_relation(client):
    rag, emb, faiss, other = _graph_fixture(client)
    routes = client.get("/discoveries/routes", headers=AUTH).json()

    # 개념 공유: RAG 노트와 임베딩 노트는 둘 다 Embedding을 가진다
    r = _route(routes, rag["id"], emb["id"])
    assert r["shared_concepts"] == ["Embedding"]
    assert "RAG —사용한다→ Embedding" in r["relations"]

    # 임베딩 노트가 말한 관계(FAISS→Embedding)는 FAISS를 가진 FAISS 노트와 잇는다
    r = _route(routes, emb["id"], faiss["id"])
    assert r["shared_concepts"] == ["FAISS"]
    assert r["relations"] == ["FAISS —사용한다→ Embedding"]

    assert not any(other["id"] in (x["note_a"], x["note_b"]) for x in routes)


def test_relation_from_third_note_does_not_link(client):
    # FAISS→Embedding은 임베딩 노트에서 나온 관계다 — RAG 노트(Embedding)와
    # FAISS 노트(FAISS)는 그 관계를 말하지 않았으므로 이어지지 않는다
    rag, emb, faiss, other = _graph_fixture(client)
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert _route(routes, rag["id"], faiss["id"]) is None


def test_mentioned_only_concept_links_weaker(client):
    x, z, y = (_note(client, t, "본문") for t in ("X", "Z", "Y"))
    _store(x["id"], [("Shared", "개념", 3, [])])
    _store(z["id"], [("Shared", "개념", 3, [])])
    _store(y["id"], [("Shared", "개념", 1, [])])   # 언급만 — 나중에 만들어 최근 순으로는 앞선다
    d = client.get(f"/discoveries?note_id={x['id']}", headers=AUTH).json()
    assert [n["note_id"] for n in d] == [z["id"], y["id"]]


def test_relation_to_rare_concept_links_stronger(client):
    from db import get_conn
    from routers.search import _PairEvidence
    a, b, c = (_note(client, t, "본문") for t in ("A", "B", "C"))
    _store(a["id"], [("Alpha", "도구", 2, []), ("Rare", "기술", 2, []), ("Common", "기술", 2, [])],
           [("Alpha", "사용한다", "Rare"), ("Alpha", "사용한다", "Common")])
    _store(b["id"], [("Rare", "기술", 2, [])])
    _store(c["id"], [("Common", "기술", 2, [])])
    for i in range(3):
        _store(_note(client, f"W{i}", "본문")["id"], [("Common", "기술", 2, [])])
    with get_conn() as conn:
        ev = _PairEvidence(conn)
    ab = ev.relations[tuple(sorted((a["id"], b["id"])))]["Alpha —사용한다→ Rare"]
    ac = ev.relations[tuple(sorted((a["id"], c["id"])))]["Alpha —사용한다→ Common"]
    assert ab > ac


def test_discoveries_use_concepts_and_relations(client):
    rag, emb, faiss, other = _graph_fixture(client)
    d = client.get(f"/discoveries?note_id={rag['id']}", headers=AUTH).json()

    # RAG 노트는 Embedding을 공유하고 관계(RAG→Embedding)를 말한 임베딩 노트와만 이어진다
    assert [x["note_id"] for x in d] == [emb["id"]]
    assert d[0]["shared_concepts"] == ["Embedding"]
    assert "RAG —사용한다→ Embedding" in d[0]["relations"]

    all_ids = {x["note_id"] for x in client.get("/discoveries", headers=AUTH).json()}
    assert all_ids == {rag["id"], emb["id"], faiss["id"]}


def test_rare_shared_concept_ranks_above_common_one(client):
    x, y, z = (_note(client, t, "본문") for t in ("X", "Y", "Z"))
    _store(x["id"], [("Common", "개념", 2, []), ("Rare", "개념", 2, [])])
    _store(y["id"], [("Common", "개념", 2, [])])
    _store(z["id"], [("Rare", "개념", 2, [])])
    for i in range(3):
        _store(_note(client, f"W{i}", "본문")["id"], [("Common", "개념", 2, [])])

    d = client.get(f"/discoveries?note_id={x['id']}", headers=AUTH).json()
    # Y와 W들은 같은 흔한 개념만 공유해 동점 — 희귀 개념을 공유한 Z가 그들보다 앞선다
    assert d[0]["note_id"] == z["id"]
    assert y["id"] in [n["note_id"] for n in d[1:]]


def test_hub_concept_is_not_route_evidence(client):
    notes = [_note(client, f"N{i}", "본문") for i in range(12)]
    for n in notes:
        _store(n["id"], [("Hub", "개념", 2, [])])
    a, b = notes[0], notes[1]
    _store(a["id"], [("Hub", "개념", 2, []), ("Niche", "개념", 2, [])])
    _store(b["id"], [("Hub", "개념", 2, []), ("Niche", "개념", 2, [])])

    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert len(routes) == 1
    assert routes[0]["shared_concepts"] == ["Niche"]


def test_extracted_keywords_ignored_between_graph_notes_but_tags_kept(client):
    a = _note(client, "A", "#공통태그")
    b = _note(client, "B", "#공통태그")
    plain = _note(client, "그래프 없음", "본문")
    _store(a["id"], [("Alpha", "개념", 2, [])])
    _store(b["id"], [("Beta", "개념", 2, [])])
    for n in (a, b, plain):
        _entity(n["id"], "기술")

    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert _route(routes, a["id"], b["id"])["shared_entities"] == ["공통태그"]
    # 그래프가 없는 노트는 추출 키워드로 대신 이어진다
    assert _route(routes, a["id"], plain["id"])["shared_entities"] == ["기술"]


def test_routes_list_strong_relations_first_with_evidence(client):
    from db import get_conn
    a, b = _note(client, "A", "본문"), _note(client, "B", "본문")
    _store(a["id"], [("Docker", "도구", 2, []), ("Linux", "기술", 2, []), ("Zulu", "개념", 2, [])],
           [("Docker", "관련있다", "Zulu"), ("Docker", "사용한다", "Linux")])
    _store(b["id"], [("Zulu", "개념", 2, []), ("Linux", "기술", 2, [])])
    with get_conn() as conn:
        conn.execute("UPDATE relations SET evidence = 'Docker는 Linux 커널을 쓴다' WHERE pred = '사용한다'")

    r = _route(client.get("/discoveries/routes", headers=AUTH).json(), a["id"], b["id"])
    # 가나다/알파벳순이면 '관련있다'가 앞서지만, 강한 관계가 먼저 온다
    assert r["relations"] == ["Docker —사용한다→ Linux", "Docker —관련있다→ Zulu"]
    assert r["evidence"] == {"Docker —사용한다→ Linux": "Docker는 Linux 커널을 쓴다"}


def test_route_kind_reflects_strongest_evidence(client):
    rag, emb, faiss, other = _graph_fixture(client)
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert _route(routes, rag["id"], emb["id"])["kind"] == "relation"
    a, b = _note(client, "약한1", "본문"), _note(client, "약한2", "본문")
    _store(a["id"], [("Shared", "개념", 2, [])])
    _store(b["id"], [("Shared", "개념", 2, [])])
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    assert _route(routes, a["id"], b["id"])["kind"] == "concept"


def test_literal_never_links_notes(client):
    from tests.test_graph import _store_onto
    a, b = _note(client, "A", "본문"), _note(client, "B", "본문")
    _store_onto(a["id"], [("FAISS", "instance"), ("768", "literal")], [("FAISS", "차원", "768")])
    _store_onto(b["id"], [("Milvus", "instance"), ("768", "literal")], [("Milvus", "차원", "768")])
    assert _route(client.get("/discoveries/routes", headers=AUTH).json(), a["id"], b["id"]) is None


def test_archived_note_relations_do_not_link_notes(client):
    from db import get_conn
    from tests.test_graph import _store_onto
    a, b, arch = (_note(client, t, "본문") for t in ("A", "B", "보관"))
    _store_onto(a["id"], [("FAISS", "instance")])
    _store_onto(b["id"], [("벡터DB", "class")])
    _store_onto(arch["id"], [("FAISS", "instance"), ("벡터DB", "class")], [("FAISS", "인스턴스이다", "벡터DB")])
    with get_conn() as conn:
        conn.execute("UPDATE notes SET is_archived = 1 WHERE id = ?", (arch["id"],))
    assert _route(client.get("/discoveries/routes", headers=AUTH).json(), a["id"], b["id"]) is None


# ── 경로 탐색 ──────────────────────────────────────────────

def _path(client, a, b):
    return client.get(f"/routes/path?from={a}&to={b}", headers=AUTH)


def test_route_path_follows_relations_between_notes(client):
    rag, emb, faiss, other = _graph_fixture(client)
    p = _path(client, rag["id"], faiss["id"]).json()
    assert p["found"] is True
    # RAG 노트 —Embedding— 관계(FAISS 사용한다 Embedding) —FAISS— FAISS 노트: 3단계가 최단
    assert [n.get("title") or n.get("name") for n in p["nodes"]] == [
        "RAG 파이프라인 메모", "Embedding", "FAISS", "FAISS 인덱스 구축"]
    assert [e["kind"] for e in p["edges"]] == ["contains", "relation", "contains"]
    assert p["edges"][1]["pred"] == "사용한다"

    assert _path(client, rag["id"], other["id"]).json() == {"found": False, "nodes": [], "edges": []}
    assert _path(client, rag["id"], rag["id"]).status_code == 400
    assert _path(client, rag["id"], "nope").status_code == 404


def test_route_path_does_not_shortcut_through_hub(client):
    notes = [_note(client, f"N{i}", "본문") for i in range(12)]
    for n in notes:
        _store(n["id"], [("Hub", "개념", 2, [])])
    assert _path(client, notes[0]["id"], notes[1]["id"]).json()["found"] is False


def test_route_path_ignores_literals(client):
    from tests.test_graph import _store_onto
    a, b = _note(client, "A", "본문"), _note(client, "B", "본문")
    _store_onto(a["id"], [("Redis", "instance"), ("v7", "literal")], [("Redis", "버전", "v7")])
    _store_onto(b["id"], [("Kafka", "instance"), ("v7", "literal")], [("Kafka", "버전", "v7")])
    assert _path(client, a["id"], b["id"]).json()["found"] is False


# ── 노트 즉시 추출 (항로 분석 버튼) ─────────────────────────

def test_graph_analyze_note_endpoint(client, monkeypatch):
    from services import graph_extraction as ge
    n = _note(client, "노트", "본문")

    monkeypatch.setattr(ge, "model_ready", lambda: "Google API 키가 설정되지 않았습니다")
    r = client.post(f"/graph/notes/{n['id']}", headers=AUTH)
    assert r.status_code == 400 and "API 키" in r.json()["detail"]

    monkeypatch.setattr(ge, "model_ready", lambda: None)
    monkeypatch.setattr(ge, "call_model", lambda content: json.dumps(
        {"nodes": [{"name": "Redis", "kind": "instance", "type": "도구", "weight": 3}], "edges": []}))
    assert client.post("/graph/notes/nope", headers=AUTH).status_code == 404
    assert client.post(f"/graph/notes/{n['id']}", headers=AUTH).json() == {"queued": 1}
    assert client.get(f"/notes/{n['id']}", headers=AUTH).json()["graph_status"] == "done"
    assert _count("SELECT COUNT(*) FROM note_concepts WHERE note_id = ?", n["id"]) == 1


def test_graph_analyze_queues_only_missing(client, monkeypatch):
    from db import get_conn
    from services import graph_extraction as ge, graph_worker
    monkeypatch.setattr(graph_worker, "start", lambda: None)
    monkeypatch.setattr(ge, "model_ready", lambda: "Ollama 서버에 연결할 수 없습니다")
    assert client.post("/graph/analyze", headers=AUTH).status_code == 400

    monkeypatch.setattr(ge, "model_ready", lambda: None)
    a, b, c = (_note(client, t, "본문") for t in ("가", "나", "다"))
    with get_conn() as conn:
        conn.execute("UPDATE notes SET graph_status = 'done' WHERE id = ?", (a["id"],))
        conn.execute("UPDATE notes SET graph_status = 'failed' WHERE id = ?", (b["id"],))
        conn.execute("UPDATE notes SET graph_status = 'idle' WHERE id = ?", (c["id"],))
    assert client.post("/graph/analyze", headers=AUTH).json() == {"queued": 2}
    assert client.get(f"/notes/{a['id']}", headers=AUTH).json()["graph_status"] == "done"


def test_weak_pairs_dropped_below_min_score(client, monkeypatch):
    from routers import search
    _graph_fixture(client)
    monkeypatch.setattr(search, "_MIN_ROUTE_SCORE", 100.0)
    assert client.get("/discoveries/routes", headers=AUTH).json() == []
    assert client.get("/discoveries", headers=AUTH).json() == []
