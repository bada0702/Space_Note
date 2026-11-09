from tests.conftest import AUTH
from tests.test_graph import _note, _store


def _cat(client, name):
    return client.post("/categories", json={"name": name}, headers=AUTH).json()["id"]


def test_constellations_require_auth(client):
    assert client.get("/constellations").status_code == 401


def test_constellations_list_concepts_shared_by_enough_notes(client):
    c1, c2 = _cat(client, "은하1"), _cat(client, "은하2")
    a = _note(client, "a", "x", c1)
    b = _note(client, "b", "x", c2)
    c = _note(client, "c", "x", c2)
    d = _note(client, "d", "x", c1)
    # _store는 노트의 개념을 통째로 교체하므로 노트별로 한 번에 저장
    _store(a["id"], [("Athena", "시스템", 3, []), ("RAG", "기술", 3, [])])
    _store(b["id"], [("Athena", "시스템", 3, [])])
    _store(c["id"], [("Athena", "시스템", 3, [])])
    _store(d["id"], [("RAG", "기술", 3, [])])  # RAG는 노트 2개 → 별자리 아님

    rows = client.get("/constellations", headers=AUTH).json()
    assert [r["name"] for r in rows] == ["Athena"]
    assert rows[0]["note_count"] == 3
    assert rows[0]["galaxy_count"] == 2


def test_constellations_exclude_archived_notes(client):
    notes = [_note(client, f"n{i}", "x") for i in range(3)]
    for n in notes:
        _store(n["id"], [("Kafka", "기술", 2, [])])
    client.patch(f"/notes/{notes[0]['id']}", json={"is_archived": True}, headers=AUTH)
    assert client.get("/constellations", headers=AUTH).json() == []


def test_constellation_notes(client):
    notes = [_note(client, f"n{i}", "x") for i in range(3)]
    for n in notes:
        _store(n["id"], [("Athena", "시스템", 3, [])])
    cid = client.get("/constellations", headers=AUTH).json()[0]["id"]
    rows = client.get(f"/constellations/{cid}/notes", headers=AUTH).json()
    assert sorted(r["id"] for r in rows) == sorted(n["id"] for n in notes)
    assert {"id", "title", "category_id", "modified_at"} <= set(rows[0])


def test_constellation_notes_unknown_id(client):
    assert client.get("/constellations/nope/notes", headers=AUTH).status_code == 404


def test_constellation_graph_has_neighbors_and_labelled_edges(client):
    from tests.test_graph import _store_onto
    notes = [_note(client, f"n{i}", "x") for i in range(3)]
    _store(notes[0]["id"], [("Docker", "도구", 3, []), ("Linux", "기술", 2, []), ("Podman", "도구", 1, [])],
           [("Docker", "사용한다", "Linux"), ("Podman", "관련있다", "Docker"), ("Linux", "관련있다", "Podman")])
    _store(notes[1]["id"], [("Docker", "도구", 3, []), ("Linux", "기술", 2, [])], [("Docker", "사용한다", "Linux")])
    _store_onto(notes[2]["id"], [("Docker", "instance"), ("Kafka", "instance"), ("v24", "literal")],
                [("Docker", "버전", "v24")])
    cid = client.get("/constellations", headers=AUTH).json()[0]["id"]
    g = client.get(f"/constellations/{cid}/graph", headers=AUTH).json()
    names = {n["id"]: n["name"] for n in g["nodes"]}
    assert g["center"]["name"] == "Docker"
    # 관계 없는 공동 개념(Kafka)과 literal 값(v24)은 빠진다
    assert set(names.values()) == {"Docker", "Linux", "Podman"}
    edges = {(names[e["source"]], e["pred"], names[e["target"]]): e for e in g["edges"]}
    assert set(edges) == {("Docker", "사용한다", "Linux"), ("Podman", "관련있다", "Docker"), ("Linux", "관련있다", "Podman")}
    assert len(edges[("Docker", "사용한다", "Linux")]["notes"]) == 2


def test_constellation_graph_unknown_id(client):
    assert client.get("/constellations/nope/graph", headers=AUTH).status_code == 404

