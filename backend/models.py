from typing import Optional
from pydantic import BaseModel


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


class NotePatch(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[list[str]] = None


class SettingsPatch(BaseModel):
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    default_model: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    context_note_id: Optional[str] = None
    context_category_id: Optional[str] = None
    use_rag: bool = False
    use_wiki: bool = False
