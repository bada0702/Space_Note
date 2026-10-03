"""ChatGPT 공유 링크(https://chatgpt.com/share/...)의 대화를 노트용 Markdown으로 가져온다.

공유 페이지 HTML에는 대화 데이터가 React Router turbo-stream 형식
(평탄화된 JSON 배열 + 인덱스 참조)으로 `streamController.enqueue("...")` 안에 들어 있다.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

import httpx

from services.vault import clean_grounding_markers

_ALLOWED_HOSTS = {"chatgpt.com", "chat.openai.com"}
_SHARE_PATH = re.compile(r"^/share/(?:e/)?[A-Za-z0-9-]+/?$")
_ENQUEUE = re.compile(r'streamController\.enqueue\(("(?:[^"\\]|\\.)*")\)')
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36"
)
_SHARE_ROUTE = "routes/share.$shareId.($action)"


class ShareImportError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 가져오기 실패 사유."""


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    text: str


@dataclass
class SharedConversation:
    title: str
    create_time: float | None
    messages: list[ChatMessage]


def normalize_share_url(url: str) -> str:
    """ChatGPT 공유 링크만 허용(임의 주소로 서버가 요청하지 않도록) → 쿼리 제거한 정규 URL."""
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.hostname not in _ALLOWED_HOSTS or not _SHARE_PATH.match(parts.path):
        raise ShareImportError("ChatGPT 공유 링크(https://chatgpt.com/share/...)만 가져올 수 있습니다")
    return f"https://{parts.hostname}{parts.path.rstrip('/')}"


def fetch_share_html(url: str) -> str:
    try:
        resp = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=20, follow_redirects=True)
    except httpx.HTTPError as e:
        raise ShareImportError(f"ChatGPT에 연결하지 못했습니다: {e}") from e
    # 리다이렉트로 다른 호스트에 도착했으면 신뢰하지 않는다
    if resp.url.host not in _ALLOWED_HOSTS:
        raise ShareImportError("ChatGPT 공유 페이지가 아닌 곳으로 이동했습니다")
    if resp.status_code == 404:
        raise ShareImportError("공유 링크를 찾을 수 없습니다 (삭제되었거나 비공개로 바뀌었을 수 있습니다)")
    if resp.status_code in (403, 429, 503):
        raise ShareImportError(f"ChatGPT가 요청을 거부했습니다 (HTTP {resp.status_code}) — 잠시 후 다시 시도하세요")
    if resp.status_code != 200:
        raise ShareImportError(f"공유 페이지를 가져오지 못했습니다 (HTTP {resp.status_code})")
    return resp.text


def _turbo_decode(data: list):
    """turbo-stream 평탄 배열 → 파이썬 객체. 객체 키는 {"_<키 인덱스>": 값 인덱스}, 음수는 특수값."""
    memo: dict[int, object] = {}

    def dec(i):
        if not isinstance(i, int) or i < 0:
            return None  # undefined / null / NaN 등 특수값
        if i in memo:
            return memo[i]
        v = data[i]
        if isinstance(v, dict):
            obj: dict = {}
            memo[i] = obj
            for k, vi in v.items():
                obj[data[int(k[1:])]] = dec(vi)
            return obj
        if isinstance(v, list):
            if v and isinstance(v[0], str):  # ["D", ts] 같은 타입 태그 값
                return None
            arr: list = []
            memo[i] = arr
            arr.extend(dec(x) for x in v)
            return arr
        return v

    return dec(0)


def _message_text(content: dict) -> str:
    out = []
    for part in content.get("parts") or []:
        if isinstance(part, str):
            if part.strip():
                out.append(part)
        elif isinstance(part, dict) and "image" in str(part.get("content_type", "")):
            out.append("[이미지]")
    return clean_grounding_markers("\n\n".join(out)).strip()


def parse_share_html(html: str) -> SharedConversation:
    for raw in _ENQUEUE.findall(html):
        try:
            root = _turbo_decode(json.loads(json.loads(raw)))
            data = root["loaderData"][_SHARE_ROUTE]["serverResponse"]["data"]
        except (ValueError, KeyError, TypeError, IndexError):
            continue
        messages = []
        for node in data.get("linear_conversation") or []:
            m = (node or {}).get("message") or {}
            role = (m.get("author") or {}).get("role")
            content = m.get("content") or {}
            if role not in ("user", "assistant") or m.get("recipient", "all") != "all":
                continue
            if (m.get("metadata") or {}).get("is_visually_hidden_from_conversation"):
                continue
            if content.get("content_type") not in ("text", "multimodal_text"):
                continue  # 추론 요약, 코드 실행, 메모리 컨텍스트 등
            text = _message_text(content)
            if text:
                messages.append(ChatMessage(role, text))
        if messages:
            return SharedConversation(
                title=(data.get("title") or "ChatGPT 대화").strip(),
                create_time=data.get("create_time"),
                messages=messages,
            )
    raise ShareImportError("공유 페이지에서 대화 내용을 찾지 못했습니다 (ChatGPT 페이지 구조가 바뀌었을 수 있습니다)")


def to_markdown(conv: SharedConversation, source_url: str) -> str:
    """볼트의 기존 대화 노트 형식(### 👤 User / ### 🤖 Assistant)으로 변환."""
    created = datetime.fromtimestamp(conv.create_time) if conv.create_time else datetime.now()
    lines = [
        f"# {conv.title}",
        "",
        f"- **생성 일시**: {created.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **원본**: {source_url}",
    ]
    for m in conv.messages:
        header = "### 👤 User" if m.role == "user" else "### 🤖 Assistant"
        lines += ["", "---", "", header, "", m.text]
    return "\n".join(lines) + "\n"
