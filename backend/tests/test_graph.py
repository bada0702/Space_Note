import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import AUTH


def _note(client, title, content, category_id=None):
    body = {"title": title, "content": content}
    if category_id:
        body["category_id"] = category_id
    return client.post("/notes", json=body, headers=AUTH).json()


def _store(note_id, concepts, relations=()):
    """모델 호출 없이 그래프를 직접 저장 (concepts: (name, type, weight, aliases))."""
    from db import get_conn
    from services import graph_extraction as ge
    raw = {
        "concepts": [
            {"name": n, "type": t, "weight": w, "aliases": list(a)} for n, t, w, a in concepts
        ],
        "relations": [{"s": s, "p": p, "o": o} for s, p, o in relations],
    }
    graph = ge.parse_graph(json.dumps(raw, ensure_ascii=False))
    with get_conn() as conn:
        ge.store_graph(conn, note_id, graph)


def _count(sql, *params):
    from db import get_conn
    with get_conn() as conn:
        return conn.execute(sql, params).fetchone()[0]


# ── 응답 검증 ────────────────────────────────────────────────

def test_parse_graph_cleans_invalid_items():
    from services.graph_extraction import parse_graph
    text = """```json
    {"concepts": [
        {"name": "RAG", "type": "기술", "weight": 5, "aliases": ["검색 증강 생성", "RAG"]},
        {"name": "임베딩", "type": "이상한타입", "weight": 2},
        {"name": "방법", "type": "개념"},
        {"name": "rag", "type": "기술"}
     ],
     "relations": [
        {"s": "검색 증강 생성", "p": "사용한다", "o": "임베딩"},
        {"s": "RAG", "p": "모르는관계", "o": "임베딩"},
        {"s": "RAG", "p": "사용한다", "o": "없는개념"}
     ]}
    ```"""
    g = parse_graph(text)
    names = [c["name"] for c in g["concepts"]]
    assert names == ["RAG", "임베딩"]                      # 일반어·중복 제거
    assert g["concepts"][0]["weight"] == 3                 # 범위 보정
    assert g["concepts"][0]["aliases"] == ["검색 증강 생성"]  # 자기 자신 제거
    assert g["concepts"][1]["type"] == "개념"              # 모르는 type → 기본값
    assert {(r["p"]) for r in g["relations"]} == {"사용한다", "관련있다"}  # 동의어로 지목, 모르는 관계 → 기본값
    assert len(g["relations"]) == 2


def test_parse_graph_rejects_broken_json():
    from services.graph_extraction import GraphParseError, parse_graph
    with pytest.raises(GraphParseError):
        parse_graph("개념은 RAG입니다")
    with pytest.raises(GraphParseError):
        parse_graph('{"relations": []}')


# ── DB 반영 ─────────────────────────────────────────────────

def test_store_merges_concepts_by_alias_and_replaces_per_note(client):
    a = _note(client, "A", "a")
    b = _note(client, "B", "b")
    _store(a["id"], [("Embedding", "기술", 3, ["임베딩"])])
    _store(b["id"], [("임베딩", "기술", 2, [])])           # 동의어로 같은 개념에 합쳐짐
    assert _count("SELECT COUNT(*) FROM concepts") == 1
    assert _count("SELECT COUNT(*) FROM note_concepts") == 2

    _store(a["id"], [("Docker", "도구", 3, [])])            # A 재분석: A 몫만 교체
    assert _count("SELECT COUNT(*) FROM note_concepts WHERE note_id = ?", a["id"]) == 1
    assert _count("SELECT COUNT(*) FROM concepts") == 2

    client.delete(f"/notes/{b['id']}", headers=AUTH)       # 삭제 → 고아 개념 정리
    assert _count("SELECT COUNT(*) FROM concepts") == 1
    assert _count("SELECT COUNT(*) FROM concept_aliases WHERE norm = '임베딩'") == 0


def test_process_note_calls_model_and_skips_unchanged(client, monkeypatch):
    from services import graph_extraction as ge
    n = _note(client, "RAG 정리", "RAG는 임베딩을 사용한다")
    calls = []

    def fake_call(content):
        calls.append(content)
        return json.dumps({
            "concepts": [{"name": "RAG", "type": "기술", "weight": 3},
                         {"name": "임베딩", "type": "기술", "weight": 2}],
            "relations": [{"s": "RAG", "p": "사용한다", "o": "임베딩"}],
        })

    monkeypatch.setattr(ge, "call_model", fake_call)
    assert ge.process_note(n["id"]) == "done"
    assert ge.process_note(n["id"]) == "done"              # 본문 그대로 → 호출 안 함
    assert len(calls) == 1
    assert _count("SELECT COUNT(*) FROM relations") == 1


def test_process_note_retries_bad_json_then_fails(client, monkeypatch):
    from services import graph_extraction as ge
    n = _note(client, "X", "내용")
    calls = []
    monkeypatch.setattr(ge, "call_model", lambda c: calls.append(c) or "not json")
    assert ge.process_note(n["id"]) == "failed"
    assert len(calls) == 2
    assert _count("SELECT COUNT(*) FROM notes WHERE graph_status = 'failed'") == 1


def test_call_model_retries_on_overload(client, monkeypatch):
    import httpx
    from services import graph_extraction as ge
    monkeypatch.setattr(ge.gemini_client, "_api_key", lambda: "k")
    monkeypatch.setattr(ge.time, "sleep", lambda s: None)
    responses = [503, 429, 200]

    def fake_post(url, **kw):
        code = responses.pop(0)
        body = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]} if code == 200 else {}
        return httpx.Response(code, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(ge.httpx, "post", fake_post)
    assert ge.call_model("본문") == "{}"
    assert responses == []


# ── 상태 / 작업자 ────────────────────────────────────────────

def test_note_edits_queue_graph_and_api_controls(client):
    n = _note(client, "새 노트", "본문")
    assert _count("SELECT COUNT(*) FROM notes WHERE graph_status = 'pending'") == 1

    from db import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE notes SET graph_status = 'failed'")
    r = client.post("/graph/retry-failed", headers=AUTH)
    assert r.json()["pending"] == 1

    with get_conn() as conn:
        conn.execute("UPDATE notes SET graph_status = 'idle'")
    client.patch(f"/notes/{n['id']}", json={"is_favorite": True}, headers=AUTH)
    assert _count("SELECT COUNT(*) FROM notes WHERE graph_status = 'idle'") == 1  # 플래그만 변경 → 그대로
    client.patch(f"/notes/{n['id']}", json={"content": "바뀐 본문"}, headers=AUTH)
    assert _count("SELECT COUNT(*) FROM notes WHERE graph_status = 'pending'") == 1

    with get_conn() as conn:
        conn.execute("UPDATE notes SET graph_status = 'done', graph_hash = 'x'")
    s = client.post("/graph/rebuild", headers=AUTH).json()
    assert s["pending"] == 1
    status = client.get("/graph/status", headers=AUTH).json()
    assert status["pending"] == 1 and status["total"] == 1 and status["eta_minutes"] == 1
    assert client.get("/graph/status").status_code == 401


def test_worker_waits_for_quiet_period(client):
    from services import graph_worker
    n = _note(client, "편집 중", "본문")
    assert graph_worker.next_ready_note() is None          # 방금 수정됨 → 대기
    later = datetime.now(timezone.utc) + timedelta(seconds=graph_worker.QUIET_SECONDS + 1)
    assert graph_worker.next_ready_note(later) == n["id"]


# ── 검색 ─────────────────────────────────────────────────────

def _graph_fixture(client):
    rag = _note(client, "RAG 파이프라인 메모", "검색 증강 생성 구조 정리")
    emb = _note(client, "임베딩 모델 비교", "문장을 벡터로 바꾸는 모델들")
    faiss = _note(client, "FAISS 인덱스 구축", "IVF 인덱스 만들기")
    other = _note(client, "점심 메뉴", "김치찌개")
    _store(rag["id"], [("RAG", "기술", 3, ["검색 증강 생성"]), ("Embedding", "기술", 1, ["임베딩"])],
           [("RAG", "사용한다", "Embedding")])
    _store(emb["id"], [("Embedding", "기술", 3, []), ("FAISS", "도구", 2, [])],
           [("FAISS", "사용한다", "Embedding")])
    _store(faiss["id"], [("FAISS", "도구", 3, [])])
    return rag, emb, faiss, other


def test_graph_retrieval_follows_relations(client):
    from db import get_conn
    from routers.ai import _retrieve_notes
    rag, emb, faiss, other = _graph_fixture(client)
    with get_conn() as conn:
        # "FAISS"라는 단어는 질문에 없지만 RAG → 임베딩 ← FAISS 로 2단계 연결
        notes = _retrieve_notes(conn, "검색 증강 생성은 어떻게 동작해?", None, None, fallback_recent=False)
    ids = [n["id"] for n in notes]
    assert ids[0] == rag["id"]
    assert faiss["id"] in ids and other["id"] not in ids
    reason = next(n["reason"] for n in notes if n["id"] == faiss["id"])
    assert reason == "'RAG' —사용한다→ 'Embedding' ←사용한다— 'FAISS'"


def test_ascii_alias_respects_word_boundary(client):
    from db import get_conn
    from services.graph_retrieval import match_seeds
    n = _note(client, "AI 노트", "x")
    _store(n["id"], [("AI", "기술", 3, [])])
    with get_conn() as conn:
        assert match_seeds(conn, "send mail") == {}
        assert len(match_seeds(conn, "AI가 뭐야")) == 1


def test_hub_concepts_are_not_expanded(client, monkeypatch):
    from db import get_conn
    from services import graph_retrieval
    rag, emb, faiss, other = _graph_fixture(client)
    monkeypatch.setattr(graph_retrieval, "HUB_DEGREE", 1)  # Embedding(이웃 2개)을 허브로 취급
    with get_conn() as conn:
        hits = graph_retrieval.expand(conn, graph_retrieval.match_seeds(conn, "RAG"))
    names = {h.name for h in hits.values()}
    assert "Embedding" in names and "FAISS" not in names


def test_retrieve_falls_back_to_keywords_without_graph(client):
    n = _note(client, "XRDP 세션 정리", "XRDP 세션이 끊기는 문제")
    r = client.get("/ai/retrieve", params={"q": "XRDP 세션"}, headers=AUTH).json()
    assert r[0]["id"] == n["id"]
    assert r[0]["reason"].startswith("키워드 '")
    assert set(r[0]) == {"id", "title", "excerpt", "reason"}


def test_chat_stream_sends_sources_first(client, monkeypatch):
    from routers import ai as ai_router
    rag, *_ = _graph_fixture(client)
    monkeypatch.setattr(ai_router.anthropic_client, "stream_chat", lambda m, s, msgs: iter(["답"]))
    r = client.post("/ai/chat", json={
        "model": "claude-sonnet-4-6", "use_rag": True,
        "messages": [{"role": "user", "content": "RAG 설명해줘"}],
    }, headers=AUTH)
    lines = [l[6:] for l in r.text.splitlines() if l.startswith("data: ")]
    first = json.loads(lines[0])
    assert first["sources"][0]["id"] == rag["id"]
    assert first["sources"][0]["path"] == "개념 'RAG'"
    assert json.loads(lines[1]) == {"text": "답"}
