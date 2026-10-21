import json
import uuid

from tests.conftest import AUTH


def _note(client, title):
    return client.post("/notes", json={"title": title, "content": title}, headers=AUTH).json()["id"]


def _store(note_id, nodes, edges=()):
    """nodes: (name, kind), edges: (s, p, o)."""
    from db import get_conn
    from services import graph_extraction as ge
    raw = {
        "nodes": [{"name": n, "kind": k, "weight": 2} for n, k in nodes],
        "edges": [{"s": s, "p": p, "o": o} for s, p, o in edges],
    }
    with get_conn() as conn:
        ge.store_graph(conn, note_id, ge.parse_graph(json.dumps(raw, ensure_ascii=False)))


def _pairs():
    from db import get_conn
    from services.ontology_routes import ontology_pairs
    with get_conn() as conn:
        return ontology_pairs(conn)


def _key(a, b):
    return (a, b) if a < b else (b, a)


def test_relation_links_notes_without_shared_node(client):
    a, b = _note(client, "A"), _note(client, "B")
    _store(a, [("FAISS", "instance"), ("벡터DB", "class")], [("FAISS", "인스턴스이다", "벡터DB")])
    _store(b, [("벡터DB", "class")])
    # 공유 점수가 섞이지 않게 A의 노드 목록에서 벡터DB를 뺀다 (관계는 남김)
    from db import get_conn
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM note_concepts WHERE note_id = ? AND concept_id = "
            "(SELECT id FROM concepts WHERE name = '벡터DB')", (a,))
    pair = _pairs()[_key(a, b)]
    assert pair.score == 1.0
    assert pair.relations[0] == {"s": "FAISS", "s_kind": "instance", "p": "인스턴스이다",
                                 "o": "벡터DB", "o_kind": "class"}


def test_shared_instance_and_class_weights(client):
    a, b, c, d = (_note(client, t) for t in "ABCD")
    _store(a, [("Ollama", "instance")])
    _store(b, [("Ollama", "instance")])
    _store(c, [("LLM", "class")])
    _store(d, [("LLM", "class")])
    pairs = _pairs()
    assert pairs[_key(a, b)].score == 1.0
    assert pairs[_key(a, b)].relations[0]["p"] == "공유"
    assert pairs[_key(c, d)].score == 0.5


def test_literal_never_links(client):
    a, b = _note(client, "A"), _note(client, "B")
    _store(a, [("FAISS", "instance"), ("768", "literal")], [("FAISS", "차원", "768")])
    _store(b, [("Milvus", "instance"), ("768", "literal")], [("Milvus", "차원", "768")])
    assert _key(a, b) not in _pairs()


def test_hub_node_excluded(client):
    ids = [_note(client, f"N{i}") for i in range(31)]
    for nid in ids:
        _store(nid, [("LLM", "class")])
    assert _pairs() == {}


def _entity(note_id, name):
    from db import get_conn
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO entities (id, note_id, name, type, norm, created_at) VALUES (?, ?, ?, 'concept', ?, 'now')",
            (str(uuid.uuid4()), note_id, name, name.lower()))


def test_routes_endpoint_prefers_ontology_and_marks_kind(client):
    x, y = _note(client, "X"), _note(client, "Y")
    others = [_note(client, f"O{i}") for i in range(5)]
    _store(x, [("Ollama", "instance")])
    _store(y, [("Ollama", "instance")])
    for i, o in enumerate(others):          # X와 키워드만 공유하는 노트 5개
        _entity(x, f"kw{i}")
        _entity(o, f"kw{i}")
    routes = client.get("/discoveries/routes", headers=AUTH).json()
    mine = [r for r in routes if x in (r["note_a"], r["note_b"])]
    onto = [r for r in mine if r["kind"] == "ontology"]
    assert len(onto) == 1 and y in (onto[0]["note_a"], onto[0]["note_b"])
    assert onto[0]["relations"][0]["p"] == "공유"
    assert all(r["kind"] == "keyword" and r["relations"] == [] for r in mine if r is not onto[0])


def test_discoveries_for_note_include_ontology_links(client):
    x, y = _note(client, "X"), _note(client, "Y")
    _store(x, [("FAISS", "instance"), ("벡터DB", "class")], [("FAISS", "인스턴스이다", "벡터DB")])
    _store(y, [("벡터DB", "class")])
    items = client.get(f"/discoveries?note_id={x}", headers=AUTH).json()
    hit = next(i for i in items if i["note_id"] == y)
    assert hit["kind"] == "ontology"
    assert hit["relations"]
    assert hit["shared_count"] == 0
