from typing import Annotated, Optional
from pydantic import BaseModel, StringConstraints


class CategoryCreate(BaseModel):
    name: str
    color: Optional[str] = None


class CategoryPatch(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


class NoteCreate(BaseModel):
    title: str
    vault_path: Optional[str] = None  # 보안상 무시됨 (서버 VAULT_DIR 사용)
    category_id: Optional[str] = None
    content: Optional[str] = None


class ChatGPTImport(BaseModel):
    url: str
    category_id: Optional[str] = None


class MdFile(BaseModel):
    path: str  # 고른 폴더 기준 상대 경로 (예: 은하/노트.md)
    content: str


class MdFilesImport(BaseModel):
    files: list[MdFile]


class NotePatch(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[list[str]] = None
    is_favorite: Optional[bool] = None
    is_archived: Optional[bool] = None


class SettingsPatch(BaseModel):
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    default_model: Optional[str] = None
    vault_dir: Optional[str] = None
    graph_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_custom_models: Optional[list[str]] = None
    # 왼쪽 위 앱 이름·로고. 빈 문자열이면 화면이 기본값을 쓴다
    app_title: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]] = None
    # 로고는 이미지 data URL만 (외부 주소를 받으면 앱을 열 때마다 그 서버로 요청이 나간다).
    # 원본 200KB의 base64 길이(약 273,000자)에 여유를 둔다
    app_logo: Optional[Annotated[str, StringConstraints(
        max_length=280_000, pattern=r"^(data:image/(png|jpeg|svg\+xml);base64,[A-Za-z0-9+/=]+)?$",
    )]] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatSource(BaseModel):
    id: str
    title: str
    path: str = ""


class SavedChatMessage(BaseModel):
    role: str
    content: str
    sources: list[ChatSource] = []
    error: Optional[str] = None


class ConversationSave(BaseModel):
    title: Optional[str] = None
    model: str = ""
    messages: list[SavedChatMessage]


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    context_note_id: Optional[str] = None
    context_category_id: Optional[str] = None
    use_rag: bool = False
    use_wiki: bool = False


class RouteCreate(BaseModel):
    note_a: str
    note_b: str
