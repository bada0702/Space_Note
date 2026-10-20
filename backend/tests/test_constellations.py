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
