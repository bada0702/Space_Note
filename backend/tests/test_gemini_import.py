import json

import pytest

from tests.conftest import AUTH

SHORT_URL = "https://share.gemini.google/AbC12dEf34Gh"
SHARE_URL = "https://gemini.google.com/share/0a1b2c3d4e5f"


def _turn(user_text, answer, ts, attachments=None, candidates=None, chosen=None):
    """Gemini 공유 대화 RPC(ujx1Bf)의 한 턴 — 실제 응답에서 쓰는 위치만 채운 가상 데이터."""
    candidates = candidates or [["rc_1", [answer]]]
    return [
        ["c_x", f"r_{ts}"],
        None,
        [[user_text, None, None, None, attachments or []], 2, None, 1, "x", None],
        [candidates, None, None, chosen or candidates[0][0]],
        [ts, 0],
    ]


def _rpc_raw(title="장보기 목록 정리", turns=None) -> str:
    turns = turns if turns is not None else [
        _turn("주말 장보기 목록 정리해줘", "**채소**: 양파, 당근[cite: 1]\n[cite_start]과일: 사과[cite: 1, 2]", 1781000000),
        _turn("", "사진 속 영수증 합계는 12,000원입니다.", 1781000100, attachments=[[None, 1, "receipt.jpg"]]),
    ]
    payload = json.dumps([[None, turns, [True, title], "0a1b2c3d4e5f"], None, False], ensure_ascii=False)
    line = json.dumps([["wrb.fr", "ujx1Bf", payload, None, None, None, "generic"], ["di", 10]], ensure_ascii=False)
    return f")]}}'\n\n{len(line)}\n{line}\n25\n[[\"e\",4,null,null,100]]\n"


# ── 파싱 ────────────────────────────────────────────────────

def test_parse_batchexecute_extracts_turns_and_strips_citations():
    from services.gemini_share import parse_batchexecute
    conv = parse_batchexecute(_rpc_raw())
    assert conv.title == "장보기 목록 정리"
    assert conv.create_time == 1781000000
    assert [m.role for m in conv.messages] == ["user", "assistant", "user", "assistant"]
    assert conv.messages[1].text == "**채소**: 양파, 당근\n과일: 사과"
    # 텍스트 없이 첨부만 보낸 질문은 자리표시
    assert conv.messages[2].text == "[첨부]"


def test_parse_batchexecute_uses_displayed_candidate():
    from services.gemini_share import parse_batchexecute
    turn = _turn("질문", "", 1781000000,
                 candidates=[["rc_a", ["초안 A"]], ["rc_b", ["초안 B"]]], chosen="rc_b")
    conv = parse_batchexecute(_rpc_raw(turns=[turn]))
    assert conv.messages[1].text == "초안 B"


def test_parse_batchexecute_reports_missing_share():
    from services.gemini_share import ShareImportError, parse_batchexecute
    line = json.dumps([["wrb.fr", "ujx1Bf", None, None, None, [5], "generic"]])
    with pytest.raises(ShareImportError, match="찾을 수 없습니다"):
        parse_batchexecute(f")]}}'\n\n{len(line)}\n{line}\n")


def test_parse_batchexecute_rejects_unexpected_structure():
    from services.gemini_share import ShareImportError, parse_batchexecute
    with pytest.raises(ShareImportError):
        parse_batchexecute(_rpc_raw(turns=[["깨진 턴"]]))


@pytest.mark.parametrize("url", [SHORT_URL, SHARE_URL, SHARE_URL + "?hl=ko", SHORT_URL + "/"])
def test_normalize_share_url_accepts_gemini_share_links(url):
    from services.gemini_share import normalize_share_url
    assert "?" not in normalize_share_url(url)


@pytest.mark.parametrize("url", [
    "http://share.gemini.google/AbC12dEf34Gh",
    "https://gemini.google.com/app/0a1b2c3d4e5f",
    "https://share.gemini.google/a/b",
])
def test_normalize_share_url_rejects_other_gemini_urls(url):
    from services.gemini_share import ShareImportError, normalize_share_url
    with pytest.raises(ShareImportError):
        normalize_share_url(url)


# ── API ─────────────────────────────────────────────────────

def test_import_endpoint_creates_note_from_gemini(client, monkeypatch):
    from services import gemini_share
    monkeypatch.setattr(gemini_share, "fetch_share_data", lambda url: _rpc_raw())
    r = client.post("/notes/import/chatgpt", json={"url": SHORT_URL}, headers=AUTH)
    assert r.status_code == 200, r.text
    note = r.json()
    assert note["title"] == "장보기_목록_정리"
    assert f"- **원본**: {SHORT_URL}" in note["content"]
    assert "### 🤖 Assistant\n\n**채소**" in note["content"]
    assert "[cite" not in note["content"]


def test_import_endpoint_rejects_non_share_gemini_url(client):
    r = client.post("/notes/import/chatgpt", json={"url": "https://gemini.google.com/app/x"}, headers=AUTH)
    assert r.status_code == 400
    assert "Gemini 공유 링크" in r.json()["detail"]
