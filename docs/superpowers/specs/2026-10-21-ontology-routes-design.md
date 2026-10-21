# 온톨로지 기반 항로 설계

- 날짜: 2026-10-21
- 상태: 승인됨 (설계 1~3부 대화로 승인)
- 선행 문서: `2026-10-03-knowledge-graph-rag-design.md` (지식 그래프 RAG)

## 목표

성도의 노트 사이 항로를 "같은 키워드 공유"가 아니라 Class / Instance / Literal 노드와 의미 있는 관계 엣지로 만든다. [AI 항로분석]을 누르면 노트마다 온톨로지를 추출하고, 항로에는 `FAISS —인스턴스이다→ 벡터DB` 같은 관계와 방향이 붙는다. 추출 모델로 로컬 Ollama도 고를 수 있게 한다.

범위 밖: 별도 온톨로지 그래프 화면, 표준 RDF/OWL 직렬화, [자동항로분석(Python)]의 동작 변경(키워드 공유 그대로).

## 1. 데이터 모델 (기존 테이블 확장)

### 노드 — `concepts.kind`

| kind | 뜻 | 예 | 노트 간 공유 |
|---|---|---|---|
| `class` | 추상 분류 | `벡터DB`, `LLM` | 공유 (같은 norm은 하나) |
| `instance` | 구체 대상 | `FAISS`, `Ollama` | 공유 (동의어 병합 유지) |
| `literal` | 값 | `v0.3`, `768차원` | **노트별로 따로** — norm을 `lit:<note_id>:<값 norm>`으로 저장해 병합되지 않게 한다 |

- 기존 `type`(기술·도구·개념·문제·사람·조직·프로젝트)은 보조 라벨로 유지한다. literal은 `type = '값'`.
- literal은 항로·RAG 확장·별자리에서 쓰지 않는다 (노트 안 정보로만 남음).

### 엣지 — `relations.pred`

| 분류 | 관계 | 허용 방향 |
|---|---|---|
| 구조 | `인스턴스이다` (instanceOf) | instance → class |
| 구조 | `하위클래스이다` (subClassOf) | class → class |
| 객체 속성 | `사용한다`, `일부이다`, `해결한다`, `관련있다` | class/instance ↔ class/instance |
| 데이터 속성 | 자유 이름 (20자 이내, 예: `버전`, `출시일`) | class/instance → literal |

- 방향 규칙을 어긴 엣지는 파싱 단계에서 버린다. 단, 구조 관계가 반대 방향(class → instance `인스턴스이다`)이면 s/o를 뒤집어 살린다.
- 객체 속성에 목록 밖 이름이 오면 `관련있다`로 바꾼다.

### 마이그레이션 (`PRAGMA user_version` 2, 1회)

1. `concepts`에 `kind TEXT NOT NULL DEFAULT 'instance'` 추가.
2. `type = '개념'` → `kind = 'class'`, 나머지 → `instance`.
3. `일종이다` → 주어가 instance면 `인스턴스이다`, class면 `하위클래스이다`. (instance → instance `일종이다`는 목적어를 class로 승격한 뒤 `인스턴스이다`.)
4. 모든 노트의 `graph_hash = NULL` — 다음 [AI 항로분석]에서 새 형식으로 다시 추출된다. `graph_status`는 그대로 두어 변환된 그래프가 그동안 계속 쓰인다.

## 2. 추출 (`services/graph_extraction.py`)

- 응답 형식:
  `{"nodes":[{"name","kind","type","aliases":[],"weight"}],"edges":[{"s","p","o"}]}`
- 상한: class+instance 15개, literal 10개, 엣지 25개. 일반어 필터·본문 40,000자 제한·형식 오류 1회 재요청은 기존대로.
- 추출 모델: 새 설정 `settings.graph_model` (기본 `gemini-3.1-flash-lite`).
  - `gemini-*` → 기존 Gemini 호출 (`responseMimeType: application/json`)
  - `ollama:<이름>` → Ollama `/api/chat`, `format: "json"`, `stream: false`
- 작업자(분당 10개, 수정 후 60초 대기)는 그대로.

## 3. 버튼과 API

| 버튼 | API | 동작 |
|---|---|---|
| AI 항로분석 (전체) | `POST /notes/analyze` | 내용 있는 보관 안 된 노트 중 `graph_hash`가 NULL이거나 본문 해시와 다른 노트를 `graph_status = 'pending'`으로. 응답 `{queued}` |
| AI 항로분석 (이 노트) | `POST /notes/{id}/analyze` | 해시와 관계없이 `graph_hash = NULL`, `pending` (강제 재추출) |
| 자동항로분석 (Python) | 기존 그대로 | 키워드(`entities`)만 재추출 |

- 재분석은 노트 단위 교체: 그 노트의 `note_concepts`/`relations`만 지우고 다시 넣는다. 공유 노드는 남고 고아만 정리. 확정 항로(`routes`)는 유지.
- 추출 모델 준비 확인: Gemini면 Google 키, Ollama면 서버 연결. 안 되면 400.
- 미개척 항로 패널의 진행 표시는 `GET /graph/status`의 대기 개수와 예상 시간으로 바꾼다 (분당 10개라 전체 재분석은 수십 분 — 패널을 닫아도 백그라운드로 계속됨을 안내).

## 4. 항로 계산 (`GET /discoveries/routes`)

노트 쌍 (A, B)의 온톨로지 점수:

1. **관계 연결**: 어느 노트에서 나온 트리플이든 `X —p→ Y`에서 X ∈ A, Y ∈ B (또는 반대). 가중치 1.0, `관련있다` 0.6.
2. **노드 공유**: 같은 instance 1.0, 같은 class 0.5.
- literal 제외. 노트 30개 초과로 쓰이는 노드(허브)는 1·2 모두에서 제외 — 별자리가 담당.
- 노트당 상한 5개(`_MAX_ROUTES_PER_NOTE`)는 유지: 온톨로지 항로를 점수순으로 먼저 채우고, 남는 자리에 키워드 항로.
- 응답 항목에 필드 추가 (기존 필드 유지):
  - `kind`: `"ontology"` | `"keyword"`
  - `relations`: 대표 근거 최대 3개, `[{"s","s_kind","p","o","o_kind"}]` (노드 공유는 `p = "공유"`, s = o)

## 5. 화면

- 성도: 온톨로지 항로와 키워드 항로를 색으로 구분 (온톨로지: 관계 색, 키워드: 기존 노트 색 혼합).
- 미개척 항로 패널: 온톨로지 항목은 공유 키워드 대신 관계 경로 `FAISS —인스턴스이다→ 벡터DB`를 표시.
- 설정 › AI 모델: Ollama 서버 주소 입력 + [연결 확인], 모델 이름 직접 추가(`settings.ollama_custom_models`, JSON 배열). 추가한 모델은 채팅 모델·추출 모델 목록에 모두 뜬다.
- 설정 › 지식 그래프: 추출 모델 선택 (Gemini / Ollama 모델).
- Ollama 클라이언트는 DB의 `ollama_base_url`을 쓰고, 비어 있으면 환경변수 `OLLAMA_BASE_URL`.

## 6. RAG 영향

- `graph_retrieval`은 literal 노드를 출발 개념·확장에서 제외한다.
- `PRED_WEIGHT`: `관련있다` 0.6, 데이터 속성은 사용 안 함, 나머지 1.0.

## 검증

- 단위 테스트: 마이그레이션 변환 규칙, 파싱(방향 규칙·뒤집기·literal 분리), 해시 기반 재분석 대상 선정, 항로 점수(관계 연결·노드 공유·허브 제외·literal 제외·상한), `/discoveries/routes` 응답 필드, Ollama 추출 호출 형식, 설정 API(`graph_model`, `ollama_base_url`, `ollama_custom_models`).
- 실제 확인: 마이그레이션 전 `spacenote.db` 백업 → 변환 후 항로 수·예시 출력, 노트 몇 개를 실제로 재추출해 관계 품질 확인.
