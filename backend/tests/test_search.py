from conftest import AUTH


def _make_note(client, title, content=""):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def test_search_matches_title_and_content(client):
    _make_note(client, "우주여행", "은하수를 건너")
    _make_note(client, "다른 글", "상관없음")

    r = client.get("/search?q=은하수", headers=AUTH)
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["title"] == "우주여행"
    assert results[0]["content_preview"].startswith("은하수를 건너")


def test_search_empty_query_returns_empty_list(client):
    assert client.get("/search", headers=AUTH).json() == []


def test_search_requires_auth(client):
    assert client.get("/search?q=x").status_code == 401


def test_entities_endpoint_returns_extracted_entities(client, monkeypatch):
    from routers import notes as notes_router

    monkeypatch.setattr(notes_router.extraction, "has_api_key", lambda: True)
    monkeypatch.setattr(
        notes_router.extraction, "extract_entities",
        lambda c: [{"name": "Claude", "type": "개념"}],
    )
    note = _make_note(client, "n", "본문")
    r = client.get(f"/entities/{note['id']}", headers=AUTH)
    assert r.status_code == 200
    assert [e["name"] for e in r.json()] == ["Claude"]


def test_entities_endpoint_empty_for_unknown_note(client):
    assert client.get("/entities/does-not-exist", headers=AUTH).json() == []


def test_routes_requires_auth(client):
    assert client.get("/discoveries/routes").status_code == 401


def test_routes_returns_pair_for_shared_entity(client):
    from db import get_conn
    import uuid

    n1 = _make_note(client, "노트1")
    n2 = _make_note(client, "노트2")
    n3 = _make_note(client, "노트3")  # 엔티티 없음 — 연결 안 됨

    with get_conn() as conn:
        for note_id, name in [(n1["id"], "Ollama"), (n2["id"], "ollama")]:
            conn.execute(
                "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                "VALUES (?, ?, ?, 'concept', ?, 'now')",
                (str(uuid.uuid4()), note_id, name, "ollama"),
            )

    r = client.get("/discoveries/routes", headers=AUTH)
    assert r.status_code == 200
    routes = r.json()
    assert len(routes) == 1
    a, b = sorted([n1["id"], n2["id"]])
    assert routes[0]["note_a"] == a
    assert routes[0]["note_b"] == b
    assert routes[0]["shared_entities"] == ["Ollama"]
    assert not any(n3["id"] in (r["note_a"], r["note_b"]) for r in routes)


def test_routes_merges_multiple_shared_entities_into_one_pair(client):
    from db import get_conn
    import uuid

    n1 = _make_note(client, "노트1")
    n2 = _make_note(client, "노트2")
    with get_conn() as conn:
        for name, norm in [("Ollama", "ollama"), ("Docker", "docker")]:
            for note_id in (n1["id"], n2["id"]):
                conn.execute(
                    "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                    "VALUES (?, ?, ?, 'concept', ?, 'now')",
                    (str(uuid.uuid4()), note_id, name, norm),
                )

    r = client.get("/discoveries/routes", headers=AUTH)
    routes = r.json()
    assert len(routes) == 1
    assert sorted(routes[0]["shared_entities"]) == ["Docker", "Ollama"]


def test_routes_caps_at_20_connections_per_note(client):
    from db import get_conn
    import uuid

    x = _make_note(client, "중심노트")
    weakest_note_id = None
    with get_conn() as conn:
        for i in range(21):
            nid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO notes (id, path, title, content, tags, word_count, "
                "analysis_status, created_at, modified_at) "
                "VALUES (?, ?, ?, '', '[]', 0, 'analyzed', 'now', 'now')",
                (nid, f"/tmp/{nid}.md", f"n{i}"),
            )
            if i == 0:
                weakest_note_id = nid
            # n_i는 x와 (i+1)개의 엔티티를 공유 — i=0이 가장 약한(1개) 연결
            for k in range(i + 1):
                norm = f"ent{k}"
                conn.execute(
                    "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                    "VALUES (?, ?, ?, 'concept', ?, 'now')",
                    (str(uuid.uuid4()), x["id"], norm, norm),
                )
                conn.execute(
                    "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                    "VALUES (?, ?, ?, 'concept', ?, 'now')",
                    (str(uuid.uuid4()), nid, norm, norm),
                )

    r = client.get("/discoveries/routes", headers=AUTH)
    routes = r.json()
    pairs_with_x = [row for row in routes if x["id"] in (row["note_a"], row["note_b"])]
    assert len(pairs_with_x) == 20
    assert not any(
        weakest_note_id in (row["note_a"], row["note_b"]) for row in pairs_with_x
    )
