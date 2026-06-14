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
