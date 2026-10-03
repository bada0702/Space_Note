import json

import pytest

from tests.conftest import AUTH

SHARE_URL = "https://chatgpt.com/share/6ac0f382-c4d4-83e8-b9b3-6031ca30a1c0"


def _turbo_encode(value) -> list:
    """React Router turbo-stream 형식(평탄화된 배열 + 인덱스 참조)으로 인코딩 — 테스트 픽스처용."""
    out: list = []

    def enc(v) -> int:
        if v is None:
            return -5
        idx = len(out)
        out.append(None)
        if isinstance(v, dict):
            obj = {}
            for k, val in v.items():
                kidx = len(out)
                out.append(k)
                obj[f"_{kidx}"] = enc(val)
            out[idx] = obj
        elif isinstance(v, list):
            out[idx] = [enc(x) for x in v]
        else:
            out[idx] = v
        return idx

    enc(value)
    return out


def _msg(role, parts, content_type="text", recipient="all", hidden=None):
    return {"message": {
        "author": {"role": role},
        "content": {"content_type": content_type, "parts": parts},
        "recipient": recipient,
        "metadata": {"is_visually_hidden_from_conversation": hidden} if hidden else {},
    }}


def _share_html(title="몬테카를로 정리", messages=None) -> str:
    messages = messages if messages is not None else [
        {"message": None},
        _msg("system", [""], hidden=True),
        _msg("user", ["몬테카를로 설명해줘"]),
        {"message": {"author": {"role": "assistant"},
                     "content": {"content_type": "reasoning_recap", "content": "2초간 처리함"},
                     "recipient": "all", "metadata": {}}},
        _msg("assistant", ["**수많은 번** 가상으로 실행해 보는 방법이야.citeturn0search1"]),
        _msg("assistant", ["print(1)"], content_type="code", recipient="python"),
        _msg("user", ["이 그림 봐줘", {"content_type": "image_asset_pointer"}], content_type="multimodal_text"),
    ]
    root = {"loaderData": {"routes/share.$shareId.($action)": {"serverResponse": {"data": {
        "title": title,
        "create_time": 1781000000.0,
        "linear_conversation": messages,
    }}}}}
    payload = json.dumps(json.dumps(_turbo_encode(root), ensure_ascii=False), ensure_ascii=False)
    return (
        "<html><head><title>ChatGPT</title></head><body>"
        f"<script>window.__reactRouterContext.streamController.enqueue({payload});</script>"
        "</body></html>"
    )


# ── 파싱 ────────────────────────────────────────────────────

def test_parse_share_html_keeps_only_visible_chat_text():
    from services.chatgpt_share import parse_share_html
    conv = parse_share_html(_share_html())
    assert conv.title == "몬테카를로 정리"
    assert [m.role for m in conv.messages] == ["user", "assistant", "user"]
    # 인용 마커 제거, 이미지는 자리표시
    assert conv.messages[1].text == "**수많은 번** 가상으로 실행해 보는 방법이야."
    assert conv.messages[2].text == "이 그림 봐줘\n\n[이미지]"


def test_parse_share_html_rejects_page_without_conversation():
    from services.chatgpt_share import ShareImportError, parse_share_html
    with pytest.raises(ShareImportError):
        parse_share_html("<html><body>Just a moment...</body></html>")


def test_to_markdown_matches_vault_chat_format():
    from services.chatgpt_share import parse_share_html, to_markdown
    md = to_markdown(parse_share_html(_share_html()), SHARE_URL)
    assert md.startswith("# 몬테카를로 정리\n\n- **생성 일시**: ")
    assert f"- **원본**: {SHARE_URL}" in md
    assert "### 👤 User\n\n몬테카를로 설명해줘" in md
    assert "### 🤖 Assistant\n\n**수많은 번**" in md
    assert "2초간 처리함" not in md and "print(1)" not in md


@pytest.mark.parametrize("url", [
    SHARE_URL,
    "https://chat.openai.com/share/abc-123",
    SHARE_URL + "?utm=x",
])
def test_normalize_share_url_accepts_chatgpt_share_links(url):
    from services.chatgpt_share import normalize_share_url
    assert normalize_share_url(url).split("/share/")[1].split("?")[0]


@pytest.mark.parametrize("url", [
    "https://evil.com/share/abc",
    "http://chatgpt.com/share/abc",
    "https://chatgpt.com.evil.com/share/abc",
    "https://chatgpt.com/c/abc",
    "file:///etc/passwd",
])
def test_normalize_share_url_rejects_other_urls(url):
    from services.chatgpt_share import ShareImportError, normalize_share_url
    with pytest.raises(ShareImportError):
        normalize_share_url(url)


# ── API ─────────────────────────────────────────────────────

def test_import_endpoint_creates_note(client, monkeypatch):
    from services import chatgpt_share
    monkeypatch.setattr(chatgpt_share, "fetch_share_html", lambda url: _share_html())
    r = client.post("/notes/import/chatgpt", json={"url": SHARE_URL}, headers=AUTH)
    assert r.status_code == 200, r.text
    note = r.json()
    assert note["title"] == "몬테카를로_정리"
    assert "### 👤 User" in note["content"]
    assert note["category_id"] is None


def test_import_endpoint_does_not_overwrite_same_title(client, monkeypatch):
    from services import chatgpt_share
    monkeypatch.setattr(chatgpt_share, "fetch_share_html", lambda url: _share_html())
    a = client.post("/notes/import/chatgpt", json={"url": SHARE_URL}, headers=AUTH).json()
    b = client.post("/notes/import/chatgpt", json={"url": SHARE_URL}, headers=AUTH).json()
    assert a["path"] != b["path"]
    assert b["title"] == "몬테카를로_정리_2"


def test_import_endpoint_rejects_non_chatgpt_url(client):
    r = client.post("/notes/import/chatgpt", json={"url": "https://example.com/share/x"}, headers=AUTH)
    assert r.status_code == 400
