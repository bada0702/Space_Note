# 온톨로지 기반 항로 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 성도 항로를 Class/Instance/Literal 노드와 관계 엣지 기반으로 만들고, [AI 항로분석]이 온톨로지 추출을 돌리며, 추출 모델로 Ollama를 고를 수 있게 한다.

**Architecture:** 기존 `concepts`/`relations` 테이블에 `kind`를 더해 온톨로지로 확장한다. 항로 점수 계산은 새 모듈 `services/ontology_routes.py` 하나에 모으고 `/discoveries/routes`와 `/discoveries?note_id=`가 함께 쓴다. 추출 모델 선택은 `settings.graph_model`로, Gemini/Ollama 호출을 `graph_extraction.call_model`에서 분기한다.

**Tech Stack:** FastAPI, SQLite, httpx, pytest / React + TypeScript + zustand, Three.js

**Spec:** `docs/superpowers/specs/2026-10-21-ontology-routes-design.md`

## Global Constraints

- 노드 kind: `class`, `instance`, `literal`. 구조 관계: `인스턴스이다`(instance→class), `하위클래스이다`(class→class). 객체 속성: `사용한다`, `일부이다`, `해결한다`, `관련있다`. 데이터 속성: 자유 이름 20자 이내, 대상은 literal.
- literal의 norm은 `lit:<note_id>:<값 norm>`, type은 `값`, 동의어를 등록하지 않는다.
- 상한: class+instance 15, literal 10, 엣지 25. 본문 40,000자.
- 항로 가중치: 관계 연결 1.0 (`관련있다` 0.6), instance 공유 1.0, class 공유 0.5. 허브 = 노트 30개 초과. 노트당 항로 상한 5 (기존 `_MAX_ROUTES_PER_NOTE`).
- 기본 추출 모델 `gemini-3.1-flash-lite`. Ollama 모델 값은 `ollama:<이름>`.
- 마이그레이션은 `PRAGMA user_version` 2. 실제 DB에 적용하기 전에 `backend/spacenote.db`를 백업한다.
- 주석·커밋 메시지는 한국어, 커밋 형식 `<유형>: <요약>`.
- 백엔드 테스트: `cd backend && venv/bin/python -m pytest tests -q`. 프론트: `npx tsc --noEmit -p . && npx vite build`.

## Review Focus

- Ollama 서버가 꺼진 상태에서 [AI 항로분석] → 400과 안내 문구, 대기열은 건드리지 않아야 한다. (Task 4 테스트)
- 모델이 literal을 엣지 주어로 쓰거나 class→instance로 `인스턴스이다`를 보냄 → 버리거나 뒤집어 저장, 예외 없음. (Task 2 테스트)
- 같은 값 literal("768")이 두 노트에 있음 → 항로가 생기지 않아야 한다. (Task 5 테스트)
- 마이그레이션을 두 번 실행(재시작) → 변환이 다시 일어나지 않고 새로 추출된 해시가 지워지지 않아야 한다. (Task 1 테스트)
- 노트 하나에만 쓰인 class와 다른 노트의 instance 사이 `인스턴스이다` → 항로로 이어져야 한다 (공유 없이 관계만으로). (Task 5 테스트)

---

### Task 1: DB 마이그레이션 — kind 컬럼·관계 이름 변환·설정 컬럼

**Files:**
- Modify: `backend/db.py` (SCHEMA의 concepts, settings / `init_db`)
- Test: `backend/tests/test_db_migration.py`

**Interfaces:**
- Produces: `concepts.kind` (`'class'|'instance'|'literal'`, 기본 `'instance'`), `settings.graph_model` (기본 `'gemini-3.1-flash-lite'`), `settings.ollama_custom_models` (JSON 배열 문자열, 기본 `'[]'`). `settings.ollama_base_url`은 이미 있음 (기본 `'http://127.0.0.1:11434'`).

- [ ] **Step 1: 실패 테스트 작성** — `test_migration_v2_converts_concepts_to_ontology`: user_version 1인 DB에 `kind` 없는 concepts(`RAG` 기술, `검색기법` 개념, `FAISS` 도구, `벡터DB` 도구)와 relations(`RAG 일종이다 검색기법`, `검색기법 일종이다 검색기법2(개념)`, `FAISS 일종이다 벡터DB`, `RAG 사용한다 FAISS`), notes.graph_hash='h'를 만든 뒤 `init_db()`.
  ```python
  assert kinds == {"RAG": "instance", "검색기법": "class", "FAISS": "instance", "벡터DB": "class"}  # instance→instance 일종이다의 목적어는 class로 승격
  assert preds == {("RAG","인스턴스이다","검색기법"), ("검색기법","하위클래스이다","검색기법2"), ("FAISS","인스턴스이다","벡터DB"), ("RAG","사용한다","FAISS")}
  assert graph_hash is None and user_version == 2
  ```
  `test_migration_v2_runs_once`: 마이그레이션 후 graph_hash='new'로 바꾸고 `init_db()` 재호출 → `'new'` 유지.
  `test_settings_has_graph_model_columns`: 새 DB에서 `graph_model == 'gemini-3.1-flash-lite'`, `ollama_custom_models == '[]'`.
- [ ] **Step 2: 실패 확인** — `venv/bin/python -m pytest tests/test_db_migration.py -q` → FAIL
- [ ] **Step 3: 구현** — `init_db`에 컬럼 추가(ALTER, 기존 패턴)와 `user_version < 2` 블록. 변환 순서: (1) `type='개념'`→class, 나머지 instance (2) 주어가 instance이고 목적어가 instance인 `일종이다`의 목적어를 class로 (3) `일종이다` → 주어 kind로 `인스턴스이다`/`하위클래스이다` (UNIQUE 충돌은 `UPDATE OR IGNORE` 후 남은 `일종이다` DELETE) (4) `UPDATE notes SET graph_hash = NULL`. SCHEMA의 CREATE 문에도 새 컬럼 반영.
- [ ] **Step 4: 통과 확인** — 같은 명령 PASS, 전체 테스트도 PASS
- [ ] **Step 5: 커밋** — `설정: 개념에 온톨로지 종류(kind)를 추가하고 기존 관계를 변환`

### Task 2: 추출 응답 파싱·저장을 온톨로지 형식으로

**Files:**
- Modify: `backend/services/graph_extraction.py` (`PROMPT`, `PREDICATES`, `parse_graph`, `_resolve_concept`, `store_graph`)
- Test: `backend/tests/test_graph.py`

**Interfaces:**
- Consumes: Task 1의 `concepts.kind`
- Produces: `parse_graph(text: str) -> {"concepts": [{"name","norm","kind","type","weight","aliases"}], "relations": [{"s","p","o"}]}` — 입력은 새 형식 `{"nodes","edges"}`와 기존 `{"concepts","relations"}` 모두 받는다 (kind가 없으면 type `'개념'`→class, 아니면 instance). 상수 `STRUCT_PREDICATES = ("인스턴스이다", "하위클래스이다")`, `OBJECT_PREDICATES = ("사용한다", "일부이다", "해결한다", "관련있다")`, `MAX_LITERALS = 10`, `MAX_RELATIONS = 25`. `store_graph(conn, note_id, graph)` 시그니처 유지.

- [ ] **Step 1: 실패 테스트 작성**
  - `test_parse_graph_ontology_kinds_and_directions`: nodes `FAISS`(instance), `벡터DB`(class), `v1.8`(literal), `검색`(class); edges `FAISS 인스턴스이다 벡터DB`, `벡터DB 인스턴스이다 FAISS`(뒤집힘), `벡터DB 하위클래스이다 검색`, `FAISS 버전 v1.8`, `v1.8 사용한다 FAISS`(literal 주어), `FAISS 사용한다 v1.8`(객체 속성→literal), `FAISS 아주아주아주아주긴속성이름스물한자초과 v1.8`.
    ```python
    assert {(r["s"], r["p"], r["o"]) for r in g["relations"]} == {("faiss","인스턴스이다","벡터db"), ("벡터db","하위클래스이다","검색"), ("faiss","버전","v1.8")}
    ```
    (norm 표기는 `norm_name` 결과에 맞춘다. 뒤집힌 중복은 한 번만.)
  - `test_parse_graph_caps_literals`: literal 12개 → 10개.
  - `test_store_literal_is_note_scoped`: 노트 A, B에 같은 literal `768` 저장 → concepts에 kind literal 2행, norm이 `lit:<A>:768`, `lit:<B>:768`, concept_aliases에 literal 없음.
  - 기존 `test_parse_graph_cleans_invalid_items`는 그대로 통과해야 한다 (구형 입력 호환).
- [ ] **Step 2: 실패 확인** — `pytest tests/test_graph.py -q` → 새 테스트 FAIL
- [ ] **Step 3: 구현** — 방향 규칙: `인스턴스이다`는 instance→class만(반대면 뒤집기), `하위클래스이다`는 class→class, literal은 데이터 속성의 목적어로만, 목적어가 literal이 아니면 목록 밖 이름은 `관련있다`로. 목적어가 literal이면 데이터 속성 — 구조·객체 속성 이름(`사용한다` 등)이거나 20자를 넘으면 버림. literal의 노트 스코프 norm은 `store_graph`에서 붙인다 (`parse_graph`는 note_id를 모름). `_resolve_concept`는 literal이면 별칭 조회·등록을 건너뛰고 kind를 INSERT에 포함. PROMPT를 스펙 2장 형식으로 교체.
- [ ] **Step 4: 통과 확인** — `pytest tests/test_graph.py -q` PASS
- [ ] **Step 5: 커밋** — `기능: 지식 그래프 추출을 Class·Instance·Literal 온톨로지 형식으로 변경`

### Task 3: 추출 모델 선택 (Gemini / Ollama)과 Ollama 주소 설정

**Files:**
- Modify: `backend/services/graph_extraction.py` (`call_model`), `backend/services/ollama_client.py`, `backend/models.py` (`SettingsPatch`), `backend/routers/ai.py` (`_get_settings`, `patch_settings`)
- Test: `backend/tests/test_graph.py`, `backend/tests/test_ai.py`

**Interfaces:**
- Produces:
  - `ollama_client.base_url() -> str` — DB `settings.ollama_base_url`, 비면 `settings.OLLAMA_BASE_URL`. 기존 함수들이 이것을 쓴다.
  - `ollama_client.chat_json(model: str, prompt: str) -> str` — `/api/chat`, `{"model": model_name(model), "messages":[user], "stream": False, "format": "json"}`, timeout 600, 응답 `message.content`.
  - `graph_extraction.graph_model() -> str` — DB `settings.graph_model`.
  - `graph_extraction.model_ready() -> str | None` — 준비 안 됐으면 사용자용 오류 문구, 됐으면 None. Gemini: Google 키 유무. Ollama: `list_models()`가 비면 `"Ollama 서버에 연결할 수 없습니다 (설정의 Ollama 주소를 확인하세요)"`.
  - `GET /ai/settings` 응답에 `graph_model: str`, `ollama_base_url: str`, `ollama_custom_models: list[str]` (DB의 JSON을 파싱해 돌려줌).
  - `PATCH /ai/settings` 입력에 `graph_model: str`, `ollama_base_url: str`, `ollama_custom_models: list[str]` (JSON으로 저장).

- [ ] **Step 1: 실패 테스트 작성**
  - `test_call_model_uses_ollama_when_selected`: settings.graph_model=`ollama:qwen3:8b`, ollama_base_url=`http://ollama.test:11434`, `httpx.post`를 가로채 URL이 `http://ollama.test:11434/api/chat`, json의 `format == "json"`, `model == "qwen3:8b"`인지, 반환이 `message.content`인지.
  - `test_model_ready_reports_missing_ollama`: graph_model ollama, `ollama_client.list_models`→`[]` → 문구 반환. Gemini + 키 없음 → 문구, 키 있음 → None.
  - `test_settings_roundtrip_graph_and_ollama_fields` (test_ai.py): PATCH 후 GET에서 `ollama_custom_models == ["llama3.1:8b"]`, `graph_model`, `ollama_base_url` 반영.
- [ ] **Step 2: 실패 확인** — 해당 테스트 FAIL
- [ ] **Step 3: 구현** — `call_model`은 `graph_model()`이 `ollama:` 접두사(또는 `is_ollama_model`)면 `chat_json(model, PROMPT + content[:MAX_INPUT_CHARS])`, 아니면 기존 Gemini 경로에 모델 이름을 `GRAPH_MODEL` 대신 설정값으로. 상수 `GRAPH_MODEL`은 기본값으로만 남긴다.
- [ ] **Step 4: 통과 확인** — 전체 테스트 PASS
- [ ] **Step 5: 커밋** — `기능: 지식 그래프 추출 모델로 Ollama를 고르고 서버 주소를 설정에서 지정`

### Task 4: [AI 항로분석]을 온톨로지 추출 대기열로

**Files:**
- Modify: `backend/routers/notes.py` (`analyze_all`, `analyze_one`)
- Test: `backend/tests/test_notes_analyze.py` (기존 AI 분석 테스트를 새 동작으로 교체)

**Interfaces:**
- Consumes: Task 3 `model_ready()`, `graph_extraction.content_hash(content)`, `graph_worker.start()`
- Produces: `POST /notes/analyze` → `{"queued": int}`, `POST /notes/{id}/analyze` → `{"queued": 1}`, 준비 안 됨 → 400 `{"detail": <model_ready 문구>}`. 진행 상황은 기존 `GET /graph/status`.

- [ ] **Step 1: 실패 테스트 작성**
  - `test_analyze_all_queues_only_changed_notes`: 노트 3개 (a: graph_hash=본문 해시, b: graph_hash NULL, c: 다른 해시), Google 키 설정 → queued 2, b·c만 `graph_status='pending'`, a는 그대로.
  - `test_analyze_one_forces_reextract`: 해시가 같아도 graph_hash NULL, pending.
  - `test_analyze_without_ready_model_returns_400_and_queues_nothing`: 키 없음 → 400, 모든 노트 graph_status 변화 없음.
  - `test_analyze_one_missing_note_404` 유지.
  - 기존 `analysis_status` 기대 테스트(`test_analyze_all_queues_failed_and_pending_notes`, `test_analyze_one`)는 삭제.
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 엔티티 추출 대신 `graph_status='pending'`(전체는 해시 비교로 선별, 단일은 해시 NULL) 후 `graph_worker.start()`. `_require_api_key`는 이 두 엔드포인트에서 `model_ready()`로 대체 (다른 곳에서 안 쓰면 제거).
- [ ] **Step 4: 통과 확인** — 전체 테스트 PASS
- [ ] **Step 5: 커밋** — `기능: AI 항로분석 버튼이 온톨로지 추출을 대기열에 넣도록 변경`

### Task 5: 온톨로지 항로 계산

**Files:**
- Create: `backend/services/ontology_routes.py`
- Modify: `backend/routers/search.py` (`discovery_routes`, `discoveries`)
- Test: `backend/tests/test_ontology_routes.py`

**Interfaces:**
- Consumes: Task 2의 kind·관계 저장
- Produces:
  - `ontology_pairs(conn) -> dict[tuple[str, str], Pair]` — 키는 (note_a, note_b), a < b. `@dataclass Pair: score: float; relations: list[dict]` (relations는 점수 높은 순 최대 3개, 각 `{"s","s_kind","p","o","o_kind"}`; 노드 공유는 `p="공유"`, s=o).
  - 상수 `HUB_NOTES = 30`, `SHARE_WEIGHT = {"instance": 1.0, "class": 0.5}`, `PRED_WEIGHT = {"관련있다": 0.6}`.
  - `/discoveries/routes` 항목: 기존 필드 + `kind: "ontology"|"keyword"`, `relations: list[dict]` (keyword면 `[]`).
  - `/discoveries?note_id=` 항목: 기존 필드 + `kind`, `relations`. 온톨로지로만 이어진 노트도 포함 (`shared_count`는 키워드 공유 수, 0일 수 있음). 정렬: 온톨로지 점수 → shared_count → modified_at.

- [ ] **Step 1: 실패 테스트 작성** (`_store` 헬퍼는 test_graph.py와 같은 방식, 새 형식 nodes/edges 사용)
  - `test_relation_links_notes_without_shared_node`: A에 `FAISS`(instance), B에 `벡터DB`(class), A의 엣지 `FAISS 인스턴스이다 벡터DB` → pair (A,B) score 1.0, relations[0] == `{"s":"FAISS","s_kind":"instance","p":"인스턴스이다","o":"벡터DB","o_kind":"class"}`.
  - `test_shared_instance_and_class_weights`: A·B가 instance 공유 → 1.0, C·D가 class 공유 → 0.5.
  - `test_literal_never_links`: A·B에 같은 literal `768` → pair 없음.
  - `test_hub_node_excluded`: class `LLM`이 노트 31개에 있으면 그것만으로는 pair 없음.
  - `test_routes_endpoint_prefers_ontology_and_marks_kind`: 노트 하나가 온톨로지 pair 1개와 키워드 pair 5개 → 결과 5개 중 ontology 항목 포함, `kind`·`relations` 필드 존재. 기존 `tests/test_search.py`의 항로 테스트도 그대로 PASS.
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 노트별 노드: `note_concepts JOIN concepts WHERE kind != 'literal'` (보관 노트 제외). 허브: 노트 수 > 30. 공유: 노드마다 노트 조합에 SHARE_WEIGHT. 관계: `relations`를 (s,p,o)로 DISTINCT, literal·허브 제외, s의 노트 × o의 노트 (같은 노트 제외)에 가중치 합산. `discovery_routes`는 노트별로 온톨로지 pair(점수순)를 먼저, 키워드 pair(공유 수순)를 뒤에 놓고 상위 `_MAX_ROUTES_PER_NOTE`개를 keep.
- [ ] **Step 4: 통과 확인** — 전체 테스트 PASS
- [ ] **Step 5: 커밋** — `기능: 성도 항로를 온톨로지 관계와 노드 공유로 계산`

### Task 6: RAG에서 literal 제외

**Files:**
- Modify: `backend/services/graph_retrieval.py` (`match_seeds`는 별칭이 없어 자동 제외 — `expand`의 관계 쿼리, `score_notes`)
- Test: `backend/tests/test_graph.py`

- [ ] **Step 1: 실패 테스트** — `test_retrieval_ignores_literals`: A에 `FAISS --버전--> v1.8`, B에도 literal `v1.8`; "FAISS" 질문 → B가 결과에 없음, A는 있음.
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — `expand` 쿼리에 `cs.kind != 'literal' AND co.kind != 'literal'`, `score_notes`의 개념 목록에서 literal 제외.
- [ ] **Step 4: 통과 확인** — 전체 테스트 PASS
- [ ] **Step 5: 커밋** — `수정: 지식 그래프 검색에서 Literal 값 노드를 제외`

### Task 7: 프론트엔드 — 항로 표시·분석 진행·설정

**Files:**
- Modify: `src/types/index.ts` (`DiscoveryRoute`, `Discovery`, `AISettings`), `src/components/StarMap/StarMapCanvas.tsx` (항로 색·hover 문구), `src/components/Navigation/DiscoveriesPanel.tsx` (AI 진행 표시·관계 경로), `src/components/Setup/ApiSettings.tsx` (Ollama 주소·모델 추가), `src/components/Setup/GraphSettings.tsx` (추출 모델 선택)

**Interfaces:**
- Consumes: Task 3 설정 필드, Task 4 엔드포인트, Task 5 응답 필드, 기존 `aiApi.getGraphStatus()`
- Produces: `formatRelation(r: RouteRelation): string` (`src/utils/ontology.ts`) — `"FAISS —인스턴스이다→ 벡터DB"`, 공유면 `"공유: FAISS"`.

- [ ] **Step 1: 타입** — `RouteRelation {s; s_kind; p; o; o_kind}`, `DiscoveryRoute`·`Discovery`에 `kind: 'ontology' | 'keyword'`, `relations: RouteRelation[]`, `AISettings`에 `graph_model`, `ollama_base_url`, `ollama_custom_models: string[]`.
- [ ] **Step 2: 성도** — 온톨로지 항로 색 `#7dd3fc`에 밝기 ×4 (재질 opacity 0.05와 가산 혼합이라 약 0.2로 보임), 키워드 항로는 기존 색. hover 문구(`RouteVisual.shared`)는 온톨로지면 `relations.map(formatRelation)`.
- [ ] **Step 3: 미개척 항로 패널** — [AI 항로분석]은 `getGraphStatus()`를 5초마다 폴링해 `대기 N개 · 약 M분 남음 — 패널을 닫아도 계속 분석합니다` 표시, pending 0이면 완료 문구와 목록 새로고침. 항목에 온톨로지 관계가 있으면 `formatRelation` 칩, 없으면 기존 공유 키워드 칩. 400 응답은 서버 `detail` 문구 그대로 표시.
- [ ] **Step 4: 설정** — AI 모델 탭: Ollama 주소 입력(`ollama_base_url`), [연결 확인]은 저장 후 `getOllamaModels()` 재호출해 개수/실패 표시, 모델 이름 입력 + [추가]로 `ollama_custom_models`에 넣고 칩으로 표시·삭제. 채팅 모델 select의 Ollama 그룹은 설치 목록 ∪ 직접 추가 목록. 지식 그래프 탭: 추출 모델 select (Gemini Flash-Lite 계열 `MODEL_OPTIONS`의 Google 그룹 + Ollama 목록), 바꾸면 즉시 PATCH. 재분석 확인 문구의 "Gemini API를 사용합니다"는 선택 모델 이름으로.
- [ ] **Step 5: 검증** — `npx tsc --noEmit -p . && npx vite build` 통과
- [ ] **Step 6: 커밋** — `기능: 온톨로지 항로 표시와 추출 모델·Ollama 설정 화면`

### Task 8: 실제 데이터 적용 확인

- [ ] **Step 1: 백업** — `cp backend/spacenote.db backend/spacenote.db.bak-20261021` (확인: 파일 크기 동일)
- [ ] **Step 2: 백엔드 재시작** (:8001, 기존 명령 `backend/venv/bin/uvicorn main:app --port 8001 --app-dir backend`) → 마이그레이션 적용. 확인: `concepts.kind` 분포, `일종이다` 0개, `/discoveries/routes`의 ontology 항목 수와 예시 3개 출력.
- [ ] **Step 3: 노트 2~3개 실제 재추출** — `POST /notes/{id}/analyze` 후 1분 뒤 해당 노트의 nodes/edges를 출력해 Class/Instance/Literal 품질 확인.
- [ ] **Step 4: 보고** — 변환 전후 수치, 예시 항로, 남은 전체 재분석 안내(약 1시간, 사용자가 버튼으로 시작).
