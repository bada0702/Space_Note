from conftest import AUTH


def test_create_list_update_delete_category(client):
    r = client.post("/categories", json={"name": "은하1", "color": "#abcdef"}, headers=AUTH)
    assert r.status_code == 200
    cat = r.json()
    assert cat["name"] == "은하1"
    assert cat["color"] == "#abcdef"
    assert cat["id"]
    assert cat["sort_order"] == 0
    assert cat["created_at"]

    cid = cat["id"]

    r = client.get("/categories", headers=AUTH)
    assert len(r.json()) == 1

    r = client.patch(f"/categories/{cid}", json={"name": "은하-수정", "sort_order": 3}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["name"] == "은하-수정"
    assert r.json()["sort_order"] == 3

    r = client.delete(f"/categories/{cid}", headers=AUTH)
    assert r.status_code == 204
    r = client.get("/categories", headers=AUTH)
    assert r.json() == []


def test_update_missing_category_404(client):
    r = client.patch("/categories/nope", json={"name": "x"}, headers=AUTH)
    assert r.status_code == 404
