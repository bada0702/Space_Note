from tests.conftest import AUTH


def test_norm_name_case_space_symbols():
    from services.textnorm import norm_name

    assert norm_name("OLLAMA") == norm_name("ollama") == norm_name("Ollama ")
    assert norm_name("Deep Learning") == norm_name("deep-learning")
    assert norm_name("GPT_4") == norm_name("gpt.4")
    # 한글은 그대로 보존 (공백/기호만 제거)
    assert norm_name("별 자리") == norm_name("별자리")
    assert norm_name("올라마") != norm_name("ollama")  # 한/영은 프롬프트에서 통일


def test_discoveries_links_case_insensitive_entities(client, monkeypatch):
    from routers import notes as notes_router

    monkeypatch.setattr(notes_router.extraction, "has_api_key", lambda: True)
    # 노트마다 다른 대소문자/공백 표기를 반환하도록 순차 응답
    responses = iter([
        [{"name": "OLLAMA", "type": "개념"}],
        [{"name": "ollama", "type": "개념"}],
    ])
    monkeypatch.setattr(
        notes_router.extraction, "extract_entities", lambda c: next(responses)
    )

    r1 = client.post("/notes", json={"title": "a", "content": "올라마 메모"}, headers=AUTH)
    r2 = client.post("/notes", json={"title": "b", "content": "ollama 메모"}, headers=AUTH)
    n1, n2 = r1.json(), r2.json()

    # n1 기준 발견: 표기가 달라도(OLLAMA vs ollama) n2가 연결되어야 한다
    d = client.get(f"/discoveries?note_id={n1['id']}", headers=AUTH).json()
    assert [x["note_id"] for x in d] == [n2["id"]]
    assert d[0]["shared_count"] == 1

    # 전체 발견에서도 노트당 한 번씩만 나온다
    all_d = client.get("/discoveries", headers=AUTH).json()
    ids = {x["note_id"] for x in all_d}
    assert {n1["id"], n2["id"]} <= ids
