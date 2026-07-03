"""엔티티 추출 제공자 디스패처: 키가 저장된 제공자를 자동 선택 (Anthropic 우선)."""
from services import anthropic_client, gemini_client


def has_api_key() -> bool:
    return anthropic_client.has_api_key() or gemini_client.has_api_key()


def extract_entities(content: str) -> list[dict]:
    if anthropic_client.has_api_key():
        try:
            return anthropic_client.extract_entities(content)
        except Exception:
            # 잘못된 키(401 등)여도 Gemini 키가 있으면 이어서 시도
            if not gemini_client.has_api_key():
                raise
    if gemini_client.has_api_key():
        return gemini_client.extract_entities(content)
    raise ValueError("AI API 키가 설정되지 않았습니다")
