from tests.conftest import AUTH

DATED = "**생성 일시**: 2024-03-05 09:30:15\n\n대화 본문"


def _add(client, title, content):
    return client.post("/notes", json={"title": title, "content": content}, headers=AUTH).json()["id"]


def _titles(client, q):
    r = client.get("/search", params={"q": q, "all_words": "true"}, headers=AUTH)
    assert r.status_code == 200
    return {n["title"] for n in r.json()}


def test_list_omits_content_but_detail_keeps_it(client):
    nid = _add(client, "노트", "본문 내용")

    listed = client.get("/notes", headers=AUTH).json()

    assert "content" not in listed[0]
    assert listed[0]["title"] == "노트"
    assert client.get(f"/notes/{nid}", headers=AUTH).json()["content"] == "본문 내용"


def test_list_exposes_origin_at_from_note_head(client):
    _add(client, "가져온 대화", DATED)
    _add(client, "일반 노트", "날짜 없음")

    by_title = {n["title"]: n for n in client.get("/notes", headers=AUTH).json()}

    assert by_title["가져온 대화"]["origin_at"] == "2024-03-05T09:30:15"
    assert by_title["일반 노트"]["origin_at"] is None


def test_origin_at_only_reads_first_1000_chars(client):
    _add(client, "뒤쪽 날짜", "가" * 1000 + DATED)

    assert client.get("/notes", headers=AUTH).json()[0]["origin_at"] is None


def test_saved_note_keeps_origin_at(client):
    # 저장 응답이 목록의 항목을 대체하므로 여기에도 있어야 성도 시간이 흔들리지 않는다
    nid = _add(client, "가져온 대화", DATED)

    r = client.patch(f"/notes/{nid}", json={"is_favorite": True}, headers=AUTH)

    assert r.json()["origin_at"] == "2024-03-05T09:30:15"


def test_search_all_words_matches_any_order_and_separator(client):
    _add(client, "순서 다름", "배포 절차와 도커 설정")
    _add(client, "한 단어만", "도커 설정")

    assert _titles(client, "도커 배포") == {"순서 다름"}
    assert _titles(client, "도커_배포") == {"순서 다름"}


def test_search_all_words_needs_all_in_title_or_all_in_body(client):
    _add(client, "도커 입문", "배포")
    _add(client, "제목 일치 도커 배포", "무관한 본문")

    assert _titles(client, "도커 배포") == {"제목 일치 도커 배포"}


def test_search_all_words_treats_percent_literally(client):
    _add(client, "할인", "50% 할인")
    _add(client, "숫자", "500개")

    assert _titles(client, "50%") == {"할인"}


def test_search_without_all_words_stays_contiguous(client):
    _add(client, "순서 다름", "배포 절차와 도커 설정")

    assert client.get("/search", params={"q": "도커 배포"}, headers=AUTH).json() == []
