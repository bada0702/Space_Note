"""Gemini 공유 링크(https://share.gemini.google/... , https://gemini.google.com/share/...)의 대화를
노트용 Markdown으로 가져온다.

공유 페이지 HTML에는 대화가 없고, 페이지가 뜬 뒤 Gemini 웹이 내부 RPC(batchexecute, rpcid `ujx1Bf`)로
받아온다. 로그인 없이 공유 ID만으로 호출되므로 그 RPC를 직접 부른다. 공개 API가 아니라서
구글이 구조를 바꾸면 parse_batchexecute()가 ShareImportError를 낸다.
"""
import json
import re
from urllib.parse import urlsplit

import httpx

from services.chatgpt_share import ChatMessage, SharedConversation, ShareImportError, _USER_AGENT
from services.vault import clean_grounding_markers

_SHORT_HOST = "share.gemini.google"
_SHARE_HOST = "gemini.google.com"
_SHORT_PATH = re.compile(r"^/([A-Za-z0-9_-]+)/?$")
_SHARE_PATH = re.compile(r"^/share/([A-Za-z0-9_-]+)/?$")
_RPC_ID = "ujx1Bf"
_RPC_URL = f"https://{_SHARE_HOST}/_/BardChatUi/data/batchexecute?rpcids={_RPC_ID}&rt=c"
# 답변 본문에 붙는 출처 표시: "[cite: 2]", "[cite: 1, 3]", "[cite_start]"
_CITE = re.compile(r"\[cite(?:_start|:\s*[\d,\s]+)\]")


def is_gemini_url(url: str) -> bool:
    return urlsplit(url.strip()).hostname in (_SHORT_HOST, _SHARE_HOST)


def normalize_share_url(url: str) -> str:
    """Gemini 공유 링크만 허용 → 쿼리 제거한 정규 URL."""
    parts = urlsplit(url.strip())
    path_re = _SHORT_PATH if parts.hostname == _SHORT_HOST else _SHARE_PATH
    if parts.scheme != "https" or not is_gemini_url(url) or not path_re.match(parts.path):
        raise ShareImportError(
            "Gemini 공유 링크(https://share.gemini.google/... 또는 https://gemini.google.com/share/...)만 가져올 수 있습니다"
        )
    return f"https://{parts.hostname}{parts.path.rstrip('/')}"


def _resolve_share_id(url: str) -> str:
    """짧은 링크(share.gemini.google)는 301로 gemini.google.com/share/<id>를 가리킨다 → 공유 ID."""
    parts = urlsplit(url)
    if parts.hostname == _SHARE_HOST:
        return _SHARE_PATH.match(parts.path).group(1)
    try:
        resp = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=20, follow_redirects=False)
    except httpx.HTTPError as e:
        raise ShareImportError(f"Gemini에 연결하지 못했습니다: {e}") from e
    target = urlsplit(resp.headers.get("location", ""))
    m = _SHARE_PATH.match(target.path)
    # 리다이렉트가 Gemini 공유 페이지가 아니면 신뢰하지 않는다
    if resp.status_code not in (301, 302) or target.hostname != _SHARE_HOST or not m:
        raise ShareImportError("공유 링크를 찾을 수 없습니다 (삭제되었거나 비공개로 바뀌었을 수 있습니다)")
    return m.group(1)


def fetch_share_data(url: str) -> str:
    """공유 대화 RPC 원문 응답."""
    share_id = _resolve_share_id(url)
    f_req = json.dumps([[[_RPC_ID, json.dumps([None, share_id, [4]]), None, "generic"]]])
    try:
        resp = httpx.post(_RPC_URL, data={"f.req": f_req}, headers={"User-Agent": _USER_AGENT}, timeout=20)
    except httpx.HTTPError as e:
        raise ShareImportError(f"Gemini에 연결하지 못했습니다: {e}") from e
    if resp.status_code in (403, 429, 503):
        raise ShareImportError(f"Gemini가 요청을 거부했습니다 (HTTP {resp.status_code}) — 잠시 후 다시 시도하세요")
    if resp.status_code != 200:
        raise ShareImportError(f"공유 대화를 가져오지 못했습니다 (HTTP {resp.status_code})")
    return resp.text


def _rpc_payload(raw: str):
    """batchexecute 응답(")]}'" 접두 + 길이 줄/JSON 줄 반복)에서 ujx1Bf 결과 JSON을 꺼낸다."""
    for line in raw.splitlines():
        if not line.startswith("[["):
            continue
        try:
            items = json.loads(line)
        except ValueError:
            continue
        for item in items:
            if isinstance(item, list) and item[:2] == ["wrb.fr", _RPC_ID]:
                if not isinstance(item[2], str):  # 없는 공유 ID → null + 오류 코드
                    raise ShareImportError("공유 링크를 찾을 수 없습니다 (삭제되었거나 비공개로 바뀌었을 수 있습니다)")
                return json.loads(item[2])
    raise ShareImportError("Gemini 응답에서 대화 내용을 찾지 못했습니다 (Gemini 구조가 바뀌었을 수 있습니다)")


def _clean(text: str) -> str:
    return clean_grounding_markers(_CITE.sub("", text or "")).strip()


def parse_batchexecute(raw: str) -> SharedConversation:
    data = _rpc_payload(raw)
    try:
        conv = data[0]
        turns = sorted(conv[1], key=lambda t: (t[4] or [0])[0])
        title = conv[2][1]
        messages = []
        for turn in turns:
            query = turn[2][0]
            user_text = "\n\n".join(p for p in (_clean(query[0]), "[첨부]" if query[4] else "") if p)
            if user_text:
                messages.append(ChatMessage("user", user_text))
            response = turn[3]
            # 후보 답변이 여럿이면 [3]이 화면에 보인 답변 ID
            chosen = next((c for c in response[0] if c[0] == response[3]), response[0][0])
            answer = _clean(chosen[1][0])
            if answer:
                messages.append(ChatMessage("assistant", answer))
    except (IndexError, TypeError, KeyError) as e:
        raise ShareImportError("Gemini 응답 구조를 해석하지 못했습니다 (Gemini 구조가 바뀌었을 수 있습니다)") from e
    if not messages:
        raise ShareImportError("공유 대화에 가져올 메시지가 없습니다")
    return SharedConversation(
        title=(title or "Gemini 대화").strip(),
        create_time=(turns[0][4] or [None])[0],
        messages=messages,
    )
