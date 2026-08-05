"""엔티티 추출 제공자 디스패처: 기본 모델 설정에 따라 적절한 클라이언트 선택."""
import re
import logging
from db import get_conn
from services import anthropic_client, gemini_client, ollama_client

logger = logging.getLogger(__name__)

# Kiwi 형태소 분석기 임포트 시도
try:
    from kiwipiepy import Kiwi
    kiwi = Kiwi()
    try:
        # 기본 사전에 없어 의미 없는 조각으로 잘못 쪼개지는 기술/개발 복합어를
        # 단일 명사로 등록 (예: "프론트엔드"→"프론트"+"엔드", "빌드업"→"빌"+"드"+"업" 오분리 방지)
        for _custom_word in (
            "프론트엔드", "백엔드", "마이크로서비스", "오픈소스",
            "다크모드", "라이트모드", "핫픽스", "빌드업", "엔드포인트",
            "메타데이터", "북마크",
        ):
            kiwi.add_user_word(_custom_word, "NNG", 0)
    except Exception:
        logger.warning("Kiwi custom dictionary registration failed; default segmentation will be used.")
except ImportError:
    kiwi = None
    logger.warning("kiwipiepy is not installed. Morphological analysis fallback will be used.")


def _get_default_model() -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT default_model FROM settings WHERE id = 1").fetchone()
        return row["default_model"] if row else "claude-sonnet-4-6"


def has_api_key() -> bool:
    model = _get_default_model()
    if not model.startswith(("claude", "gemini")):
        return True  # Ollama는 로컬이므로 키가 필요 없음
    return anthropic_client.has_api_key() or gemini_client.has_api_key()


# 한국어 및 영어 불용어(Stopwords)
STOP_WORDS = {
    # 영어 대화/마크다운용 노이즈 및 코드/개발 키워드
    "user", "assistant", "id", "text", "type", "data", "value", "key", 
    "name", "null", "true", "false", "string", "file", "path", "info",
    "yes", "no", "ok", "error", "test", "code", "run", "http", "port",
    "get", "post", "put", "delete", "patch", "api", "app", "main", "dev",
    "to", "in", "on", "at", "for", "with", "by", "of", "and", "or",
    "it", "is", "the", "that", "this", "you", "me", "my", "he", "she",
    "they", "we", "our", "your", "him", "her", "us", "them", "so", "but",
    "how", "why", "what", "who", "where", "when", "if", "an", "as", "be",
    "add", "check", "return", "use", "generate", "update", "print", "import",
    "export", "const", "let", "var", "function", "class", "def", "else",
    "while", "try", "except", "catch", "throw", "undefined", "void", "public",
    "private", "protected", "static", "new", "super", "break", "continue",
    "number", "boolean", "any", "object", "array", "interface", "from", "async", "await",
    
    # 한국어 공통 지시사/접속사/대화형 어휘 및 불용어
    "그럼", "근데", "그리고", "그래서", "그러나", "이러한", "그렇기", "때문에", 
    "또한", "대하여", "통하여", "관련된", "위하여", "대해서", "위해서", 
    "통해서", "경우에는", "경우가", "있습니다", "합니다", "입니다", 
    "노트", "항해", "일지", "시간", "정보", "분석", "확인", "의하여",
    "자세한", "대해서는", "대해", "위해", "통해", "경우", "다른", "모든", 
    "어떤", "무엇", "이것", "그것", "저것", "매우", "가장", "어떻게", "의한",
    "일반", "기본", "이후", "이전", "최근", "최초", "생성", "일시", "대화",
    "가능", "기반", "또는", "같은", "지금", "실제", "있음", "실행", "방법",
    "바로", "아니라", "자동", "추천", "사용", "있는", "이건", "문제", "상태",
    "이렇게", "현재", "요약", "직접", "이런", "예시", "다음", "기능", "필요",
    "없음", "관련", "내용", "부분", "추가", "설정", "처리", "결과", "대한",
    "다시", "하나", "생각", "작성", "정리", "상세", "기존", "로그", "완료",
    "수정", "삭제", "등록", "조회", "이용", "출력", "입력", "작업", "진행",
    "수행", "제공", "구현", "참고", "문서", "기록", "요청", "응답",
    "개발", "프로젝트", "프로그램", "서비스", "애플리케이션", "도구",
    "으로", "에서", "하여", "하고", "했다", "한다", "된다", "이다", "였다",
    "하는", "있는", "되는", "하며", "되고", "이고", "하고", "있어", "보면",
    "원하면", "진짜", "특히", "거의", "이미", "이게", "좋은", "중요한", "단순",
    "그냥", "없이", "같아", "내가", "네가", "이거", "저거", "그거", "하면",
    "여러", "아래", "위의", "해도", "해서", "함께", "ai가", "어떤", "저런",
    "그런", "하면", "되고", "하고", "많이", "크게", "매우", "대부분", "예를",
    "나는", "너는", "너무", "단순히", "나를", "너를", "그는", "그를", "그가",
    "그녀가", "그녀를", "그녀는", "우리는", "우리를", "나의", "너의", "그의",
    "그녀의", "우리", "그들", "저희", "당신", "너희", "조금", "적게", "같이",
    "단순", "다양한", "다양하게", "어떻게", "여전히", "아직도", "조금씩", "결국",
    "새로운", "새로", "정도", "때문", "있다", "하다", "되다", "이다", "이번", 
    "여기", "저기", "없는", "것", "들", "적", "등", "및", "선택",
    "오늘", "어제", "내일", "모레", "방금", "아까", "이제", "요즘"
}


def clean_word_casing(w: str) -> str:
    """주요 기술 스택 및 영문 약어의 대소문자를 고정 및 표준화합니다."""
    w_clean = w.strip()
    w_lower = w_clean.lower()
    
    # 영문 약어 (항상 대문자 유지)
    uppers = {
        "llm", "rag", "db", "ai", "vr", "os", "ip", "ui", "ux", 
        "api", "cli", "nim", "nfs", "gpt", "ntp", "wsl", "hba", 
        "wwn", "mcp", "cpu", "gpu", "yaml", "xml", "json", "rest", "sql"
    }
    # 특정 고유 명칭 (공식 대소문자 고정)
    specials = {
        "fastapi": "FastAPI",
        "athena": "Athena",
        "ollama": "Ollama",
        "konlpy": "KoNLPy",
        "kiwi": "Kiwi",
        "tauri": "Tauri",
        "vite": "Vite",
        "react": "React",
        "three": "Three",
        "python": "Python",
        "sqlite": "SQLite",
        "mysql": "MySQL",
        "oracle": "Oracle",
        "virtuoso": "Virtuoso",
        "langchain": "LangChain",
        "langgraph": "LangGraph",
        "chromadb": "ChromaDB"
    }
    
    if w_lower in uppers:
        return w_clean.upper()
    if w_lower in specials:
        return specials[w_lower]
        
    return w_clean


def is_korean_stopword_or_ending(word: str) -> bool:
    w_lower = word.lower()
    if w_lower in STOP_WORDS:
        return True
        
    if word.endswith("니다") or word.endswith("습니다"):
        return True
        
    grammatical_endings = (
        "에서는", "에게는", "으로써", "으로", "에서", "에게", "이며", 
        "하여", "하고", "했다", "한다", "된다", "이다", "였다", "하는", 
        "있는", "되는", "하며", "되고", "이고", "하고"
    )
    for ending in grammatical_endings:
        if len(word) >= len(ending) and word.endswith(ending):
            return True
            
    return False


def is_invalid_entity(name: str) -> bool:
    name = name.strip()
    if not name:
        return True
        
    # 1. 숫자만 있는 경우 필터링 (예: "2025", "053521")
    if name.isdigit():
        return True
        
    # 2. 해시/UUID 세그먼트 필터링 (예: "6840ae08", "e544")
    if re.match(r"^[0-9a-fA-F]{6,}$", name) or (re.search(r"\d", name) and re.search(r"[a-zA-Z]", name) and len(name) >= 6):
        return True
        
    # 3. 조사, 어미 및 불용어 필터링
    if is_korean_stopword_or_ending(name):
        return True
        
    # 4. 연도/날짜 관련 단순 패턴 필터링 (예: "2025년", "6월")
    if re.match(r"^\d+[년월일원명개번층세%배]$", name):
        return True

    return False


def strip_korean_particles(word: str) -> str:
    """한국어 명사 뒤에 붙는 조사 및 형용사형 어미(한, 된)를 탈락시켜 형태소 단어로 정규화."""
    particles_long = (
        "에서는", "에게는", "에 대한", "에대한", "으로부터",
        "으로", "에서", "에게", "한테", "부터", "까지", "이며", "이고", "라고"
    )
    particles_short = (
        "은", "는", "이", "가", "을", "를", "의", "에", "과", "와", "도", "만", "고", "한", "된"
    )
    
    changed = True
    while changed:
        changed = False
        # 1. 2글자 이상의 조사 탈락 시도
        for p in particles_long:
            if word.endswith(p) and len(word) > len(p):
                word = word[:-len(p)]
                changed = True
                break
        if changed:
            continue
            
        # 2. 1글자 조사 탈락 시도 (단어 최소 길이가 3글자 이상일 때만 수행하여 '국가', '화가' 등이 손상되는 것을 방지)
        for p in particles_short:
            if word.endswith(p) and len(word) >= 3:
                word = word[:-len(p)]
                changed = True
                break
    return word


def clean_entities(entities: list[dict]) -> list[dict]:
    """추출된 엔티티 목록에서 유효하지 않은 항목 필터링 및 중복 제거."""
    cleaned = []
    seen = set()
    for e in entities:
        name = e.get("name", "").strip()
        # 한국어 조사 제거 및 단어 정규화 수행
        normalized_name = strip_korean_particles(name)
        normalized_name = clean_word_casing(normalized_name)
        
        if is_invalid_entity(normalized_name):
            continue
        norm = normalized_name.lower()
        if norm not in seen:
            seen.add(norm)
            e_copy = dict(e)
            e_copy["name"] = normalized_name
            cleaned.append(e_copy)
    return cleaned


def extract_entities(content: str) -> list[dict]:
    model = _get_default_model()
    
    if not model.startswith(("claude", "gemini")):
        raw = ollama_client.extract_entities(content, model)
    elif anthropic_client.has_api_key():
        try:
            raw = anthropic_client.extract_entities(content)
        except Exception:
            if not gemini_client.has_api_key():
                raise
            raw = gemini_client.extract_entities(content)
    elif gemini_client.has_api_key():
        raw = gemini_client.extract_entities(content)
    else:
        raise ValueError("AI API 키가 설정되지 않았습니다")
        
    return clean_entities(raw)


def extract_entities_python(content: str) -> list[dict]:
    """파이썬 기반 규칙 및 Kiwi 형태소 분석기를 혼합하여 노트를 대표하는 핵심 키워드들을 추출합니다."""
    raw_entities = []

    # 1. Wiki-links [[link]] 추출
    for link in re.findall(r"\[\[(.*?)\]\]", content):
        parts = link.split("|")
        clean_name = re.sub(r"\d{4}-\d{2}-\d{2}_\d{6}_", "", parts[0])
        clean_name = re.sub(r"_[0-9a-fA-F]{8}$", "", clean_name)
        raw_entities.append({"name": clean_name, "type": "term"})

    # 2. Hashtags #tag 추출
    for tag in re.findall(r"#([\w\-가-힣]+)", content):
        raw_entities.append({"name": tag, "type": "tag"})

    # 3. Quotes 『...』, 「...」 추출
    for term in re.findall(r"[『「](.*?)[』」]", content):
        raw_entities.append({"name": term, "type": "term"})

    # 4. Kiwi 형태소 분석을 통한 명사 및 영어 단어 추출 (사용 가능한 경우)
    if kiwi:
        try:
            tokens = kiwi.tokenize(content or "")
            current_compound = []

            def flush_compound():
                if not current_compound:
                    return
                if len(current_compound) > 1:
                    raw_entities.append({"name": " ".join(current_compound), "type": "term"})
                    for part in current_compound:
                        raw_entities.append({"name": part, "type": "term"})
                else:
                    raw_entities.append({"name": current_compound[0], "type": "term"})
                current_compound.clear()

            for t in tokens:
                # NNG(일반 명사), NNP(고유 명사), SL(영어/외국어) 수집
                if t.tag in ("NNG", "NNP") or (t.tag == "SL" and len(t.form) >= 2):
                    form = clean_word_casing(t.form)
                    # 1글자 단어 예외 처리
                    if len(form) < 2 and form.upper() not in ("AI", "DB", "VR", "OS", "IP", "UI", "UX"):
                        continue
                    # 불용어 명사는 결합하지 않고 복합 명사 경계로만 취급
                    # (그러지 않으면 "정도"+"디버깅"처럼 뜻 없는 단어가 옆 단어에 묻어 필터를 통과한다)
                    if is_korean_stopword_or_ending(form):
                        flush_compound()
                        continue
                    current_compound.append(form)
                else:
                    # 명사가 끊어지면 쌓아둔 복합 명사를 키워드로 결합
                    flush_compound()

            # 마지막 잔여 복합 명사 처리
            flush_compound()
        except Exception:
            logger.warning("Kiwi processing failed. Falling back to regex frequency parsing.")

    # 5. 폴백 (Kiwi가 작동하지 않거나 단어가 너무 적게 추출된 경우)
    if not kiwi or len(raw_entities) < 5:
        # 기존의 한글/영문 단어 패턴 수집 (빈도 기반)
        words = re.findall(r"[a-zA-Z가-힣]{2,15}", content)
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
            
        for w, count in freq.items():
            if count >= 2:
                raw_entities.append({"name": w, "type": "term"})

    # 6. 전처리 및 조사 필터링 수행
    cleaned = clean_entities(raw_entities)
    
    # 7. 단어들의 가중치/빈도 계산을 통해 최적의 상위 30개 키워드를 선별
    cleaned_by_lower = {c["name"].lower(): c["name"] for c in cleaned}
    cleaned_type_by_name = {c["name"]: c["type"] for c in cleaned}
    
    weights = {}
    for item in raw_entities:
        name = item["name"]
        norm = name.lower()
        matched_name = cleaned_by_lower.get(norm)
        if not matched_name:
            continue
            
        weight_delta = 1
        if item["type"] == "tag":
            weight_delta = 3  # 명시적인 해시태그 우대
        elif item["type"] == "term" and ("[" in name or "『" in name or "「" in name):
            weight_delta = 2  # 인용구 및 위키링크 단어 가중치 우대
            
        weights[matched_name] = weights.get(matched_name, 0) + weight_delta

    # 가중치가 높은 상위 30개 키워드로 한정
    sorted_kws = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    top_kws = [k for k, w in sorted_kws[:30]]
    
    # 최종 결과물 조립
    final_entities = []
    seen_final = set()
    for kw in top_kws:
        orig_type = cleaned_type_by_name.get(kw, "term")
        if kw.lower() not in seen_final:
            seen_final.add(kw.lower())
            final_entities.append({"name": kw, "type": orig_type})
            
    return final_entities
