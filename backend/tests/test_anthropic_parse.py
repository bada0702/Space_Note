from services import anthropic_client as ac


def test_parse_entities_valid_json():
    text = '[{"name": "서울", "type": "place"}, {"name": "칸트", "type": "person"}]'
    out = ac.parse_entities(text)
    assert out == [
        {"name": "서울", "type": "place"},
        {"name": "칸트", "type": "person"},
    ]


def test_parse_entities_with_codefence():
    text = '```json\n[{"name": "A", "type": "concept"}]\n```'
    out = ac.parse_entities(text)
    assert out == [{"name": "A", "type": "concept"}]


def test_parse_entities_garbage_returns_empty():
    assert ac.parse_entities("not json at all") == []


def test_extract_entities_raises_without_key(client):
    # client 픽스처가 ANTHROPIC_API_KEY=""로 설정하고 DB를 초기화한다
    import pytest as _pytest

    assert ac.has_api_key() is False
    with _pytest.raises(ValueError):
        ac.extract_entities("내용 있는 노트")
