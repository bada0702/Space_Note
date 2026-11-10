# 지식 그래프 정확도 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 성도 연결선(A)과 AI 채팅 검색(B)의 품질을, 측정 가능한 기준선 대비로 올린다.

**Architecture:** 먼저 `backend/graph_eval`에 DB 진단·연결·검색 평가를 추가해 기준선을 잰다. 그다음 연결 계산(`routers/search.py`)을 AI 호출 없이 고친다. 이어서 추출(`services/graph_extraction.py`)을 고쳐 전체 재분석하고, 마지막으로 긴 노트 분할을 넣는다. 단계마다 평가 보고서로 채택 여부를 정한다.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, pytest, Gemini(`gemini-3.1-flash-lite`)

**Spec:** `docs/superpowers/specs/2026-11-10-graph-accuracy-design.md`

## Global Constraints

- 모든 명령은 `backend/`에서 실행한다. 테스트: `venv/bin/python -m pytest -q`. 시작 시점 기준선은 289 passed.
- 주석·커밋 메시지·보고서는 한국어로 쓴다. 커밋 형식은 `<유형>: <요약>`(유형: 기능, 수정, 리팩터, 문서, 테스트, 설정)이고, 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`를 붙인다. push하지 않는다.
- 평가 도구는 운영 DB를 읽기 전용(`file:...?mode=ro`)으로만 연다.
- 실제 노트에서 나온 정답·판정·표본은 `backend/graph_eval/local/`(git 제외)에만 둔다. 커밋하는 정답 세트는 가상 데이터만 쓴다. 실제 장비명·IP·위치는 넣지 않는다.
- 판정용 CSV는 `utf-8-sig`로 쓴다.
- 채택 규칙: 그 단계의 목표 지표가 오르고, 다른 층 지표가 3%p 넘게 떨어지지 않아야 한다. 미판정 쌍이 남아 있으면 채택 여부를 정하지 않는다.
- 파라미터(`_HUB_SHARE`, `_MIN_ROUTE_SCORE`, 후보 수 50, 분할 상한)는 모듈 상단 상수로 둔다.
- 노트 본문을 Gemini로 보내는 전체 재분석과, DB 스키마를 바꾸는 서버 재시작은 실행 직전에 사용자 확인을 받는다. 그 전에 `cp spacenote.db spacenote.db.bak-<YYYYMMDD-HHMM>`으로 백업한다 (`backend/*.db.bak-*`는 git 제외 패턴에 있음).

## Review Focus

1. 노트를 삭제·보관해서 투표가 줄면 공유 개념의 `kind`가 남은 노트의 다수결로 다시 정해져야 한다 → Task 8 `test_kind_recomputed_after_note_delete`.
2. 표본에 들어간 노트가 나중에 삭제·보관되면 연결 평가는 그 노트를 건너뛰고 건수를 보고해야 한다 (예외 없이) → Task 2 `test_score_skips_missing_sample_notes`.
3. 40,000자 넘게 이어지는 코드 블록처럼 안전한 경계가 없는 노트도 상한 이하 조각으로 나뉘어야 한다 → Task 11 `test_split_hard_cuts_when_no_boundary`.
4. 기존 개념 후보에서 짧은 영문 이름(`AI`)이 다른 단어 속(`mail`)에 걸리면 안 된다 → Task 9 `test_known_concepts_respect_word_boundary`.
5. 확정한 항로는 최소 점수 미만이어도 계속 그려져야 한다 → Task 7 `test_confirmed_route_kept_below_min_score`.

---

### Task 1: 항로 순위 함수 분리 + DB 진단 도구

**Files:**
- Modify: `backend/routers/search.py` (`discovery_routes`의 노트별 상위 5개 선택을 함수로 분리)
- Create: `backend/graph_eval/audit.py`
- Modify: `.gitignore` (`backend/graph_eval/local/` 추가)
- Test: `backend/tests/test_graph_eval_audit.py`

**Interfaces:**
- Produces:
  - `routers.search.ranked_routes(ev: _PairEvidence, rejected: set[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]`: 노트 id → 그 노트의 상위 쌍 키(정렬된 (a, b)) 목록. 점수 내림차순, 최대 `_MAX_ROUTES_PER_NOTE`개. `discovery_routes`는 이 결과 값들의 합집합 ∪ 확정 항로를 그린다 (동작 변화 없음).
  - `graph_eval.audit.open_ro(path: str | None = None) -> sqlite3.Connection`: 읽기 전용, `row_factory = sqlite3.Row`. 기본 경로는 `settings.DB_PATH`.
  - `graph_eval.audit.audit(conn) -> dict`: 키는 `notes_active`, `graph_status`(dict), `relations`, `evidence_rate`, `generic_rate`(객체 관계 중 `관련있다`), `concepts`, `singleton_rate`, `long_name_rate`(3단어 이상), `kind_violations`(dict: `인스턴스이다`, `하위클래스이다`), `long_notes`(40,000자 초과 수), `tail_concepts`(긴 노트에서 이름·동의어가 40,000자 뒤에만 나오는 개념 수), `pairs`, `lines`, `line_kinds`(dict), `max_degree`, `notes_without_lines`, `hubs`, `line_score_p25`(그려지는 선 점수의 25번째 백분위수).
  - CLI: `venv/bin/python -m graph_eval.audit [--db PATH]` → `graph_eval/reports/<ts>-audit.json`, `.md`.

- [ ] **Step 1: 실패하는 테스트 작성** — `client` 픽스처로 노트를 만들고 `tests.test_graph._store`, `_store_onto`로 그래프를 넣은 뒤 `audit(conn)`을 검사한다.
  - `test_audit_counts_kind_violations`: `_store_onto`로 정상 그래프를 저장한 다음, SQL로 concept 하나의 kind를 바꿔 `인스턴스이다` 위반을 만든다 → `kind_violations["인스턴스이다"] == 1`
  - `test_audit_tail_concepts`: 본문 `"a" * 40_001 + " Zeta"`인 노트에 개념 Zeta 저장 → `long_notes == 1`, `tail_concepts == 1`
  - `test_audit_lines_match_discovery_routes`: `_graph_fixture` → `audit(conn)["lines"] == len(client.get("/discoveries/routes").json())`
  - `test_open_ro_rejects_writes`: `open_ro(path).execute("DELETE FROM notes")` → `sqlite3.OperationalError`
- [ ] **Step 2: 실패 확인** — `venv/bin/python -m pytest tests/test_graph_eval_audit.py -q` → `ModuleNotFoundError: graph_eval.audit`
- [ ] **Step 3: `ranked_routes`를 분리하고 `discovery_routes`가 쓰게 한다. `audit.py`를 구현한다.** 집계 SQL은 스펙 "현재 상태" 표와 같은 정의를 쓴다. `lines`·`line_kinds`·`max_degree`·`notes_without_lines`는 `_PairEvidence`와 `ranked_routes`로 계산하고, 확정 항로는 제외한다.
- [ ] **Step 4: 통과 확인** — `venv/bin/python -m pytest -q` → 293 passed
- [ ] **Step 5: 커밋** — `기능: 지식 그래프 DB 진단 도구 추가`

### Task 2: 연결 평가 (정밀도@5)

**Files:**
- Create: `backend/graph_eval/links.py`
- Test: `backend/tests/test_graph_eval_links.py`

**Interfaces:**
- Consumes: `ranked_routes`, `_PairEvidence`, `open_ro` (Task 1)
- Produces:
  - `sample_notes(conn, n: int = 30, seed: int = 20261110) -> list[str]`: 활성 노트 중 무작위 n개 (`random.Random(seed)`, id 정렬 후 샘플). 앞 20개는 조정용, 뒤 10개는 확인용.
  - `top_routes(conn) -> dict[str, list[dict]]`: 노트 id → `[{"other": id, "score": float, "kind": str, "evidence": str}]`. `ranked_routes` 순서를 따르고, `evidence`는 공유 개념·관계·키워드를 `"; "`로 이은 문자열.
  - `export_unlabeled(conn, labels: Path, sample: list[str]) -> int`: 표본 노트의 상위 선 중 판정 파일에 없는 쌍을 추가하고, 추가한 행 수를 돌려준다. 열은 `note_a,note_b,title_a,title_b,kind,evidence,label,comment`이고 `note_a < note_b`로 정렬한다. `label`은 비워 둔다(`1` 관련, `0` 무관).
  - `score(conn, labels: Path, sample: list[str]) -> dict`: `{"tune": {...}, "holdout": {...}, "all": {...}, "missing_notes": int}`. 각 값은 `{"precision": float | None, "judged": int, "unlabeled": int, "notes_without_lines": int}`.
  - CLI: `python -m graph_eval.links export|score [--hub-share F] [--min-score F]`. 표본은 처음 실행 때 `local/links_sample.json`에 저장하고 이후 재사용한다. 판정은 `local/links_labels.csv`, 보고서는 `reports/<ts>-links.md|json`에 남긴다. `--hub-share`·`--min-score`는 `routers.search`의 `_HUB_SHARE`·`_MIN_ROUTE_SCORE` 값을 실행 중에만 바꾼다 (`_MIN_ROUTE_SCORE`는 Task 7에서 생긴다. 그 전에는 해당 옵션을 받지 않는다).

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_export_then_score`: `_graph_fixture` 후 표본을 `[rag, emb]`로 고정해 export → 행이 2개 이상. 모두 `label=1`로 채우면 `score(...)["all"]["precision"] == 1.0`, `unlabeled == 0`. 다시 export하면 0을 돌려준다.
  - `test_score_skips_missing_sample_notes`: 표본에 존재하지 않는 id 하나 포함 → `missing_notes == 1`, 예외 없음
  - `test_csv_is_utf8_sig`: export한 파일의 첫 3바이트가 `b"\xef\xbb\xbf"`
- [ ] **Step 2: 실패 확인** — `venv/bin/python -m pytest tests/test_graph_eval_links.py -q` → FAIL
- [ ] **Step 3: `links.py` 구현**
- [ ] **Step 4: 통과 확인** — 전체 테스트 통과
- [ ] **Step 5: 커밋** — `기능: 성도 연결선 정밀도 평가 도구 추가`

### Task 3: 검색 평가 (적중률@5, MRR)

**Files:**
- Create: `backend/graph_eval/retrieval.py`
- Test: `backend/tests/test_graph_eval_retrieval.py`

**Interfaces:**
- Consumes: `routers.ai._retrieve_notes(conn, query, None, None, fallback_recent=False)`, `open_ro`
- Produces:
  - `load_questions(path: Path) -> list[dict]`: `[{"q": str, "answers": [note_id, ...]}]`
  - `evaluate(conn, questions: list[dict]) -> dict`: `{"hit_at_5": float, "mrr": float, "missing_answers": int, "rows": [{"q", "ranks": [int|None], "top": [note_id]}]}`. MRR은 상위 5개 안의 첫 정답 순위의 역수이고, 없으면 0이다. 존재하지 않는 정답 id는 `missing_answers`로 세고 분모에서 뺀다.
  - CLI: `python -m graph_eval.retrieval` → `local/questions.json`을 읽어 `reports/<ts>-retrieval.md|json`을 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성** — `_graph_fixture` 사용
  - `test_evaluate_hit_and_mrr`: 질문 `"검색 증강 생성은 어떻게 동작해?"`의 정답 `[rag]` → `hit_at_5 == 1.0`, `mrr == 1.0`. 질문 `"점심 메뉴 추천"`의 정답 `[faiss]` → 그 행의 `ranks == [None]`, 두 질문 평균 `mrr == 0.5`
  - `test_missing_answer_ids_are_counted`
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: `retrieval.py` 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 커밋** — `기능: AI 채팅 검색 적중률 평가 도구 추가`

### Task 4: 추출 정답 세트 확대 (가상 노트)

**Files:**
- Create: `backend/graph_eval/cases/<ID>.md`, `<ID>.json` 12쌍 (ID 예: `RAG_PIPELINE`, `AIX_BACKUP`, `DOCKER_INSTALL`, `K8S_TROUBLESHOOT`, `OLLAMA_LOCAL`, `FAISS_INDEX`, `LINUX_CRON`, `FASTAPI_AUTH`, `THREEJS_SCENE`, `STREAMLIT_DASH`, `KOREAN_CHUNKING`, `GIT_WORKFLOW`)
- Modify: `backend/graph_eval/run.py` (`validate`가 선택 항목 `known_concepts: list[str]`를 허용·검사)
- Test: `backend/tests/test_graph_eval.py`

**Interfaces:**
- Produces: 정답 세트 형식에 선택 항목 `"known_concepts": [str]` 추가. Task 9가 프롬프트에 넣는다. 이 Task에서는 검사만 한다.

- [ ] **Step 1: 실패하는 테스트 작성** — `test_validate_rejects_bad_known_concepts`: `known_concepts: "Docker"`(문자열) → 문제 1건 보고
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: `validate`를 수정하고 가상 노트 12개를 작성한다.**
  - 노트는 각 800~3,000자의 가상 기술 메모로 쓰고, 실제 장비명·IP·사내 정보는 넣지 않는다.
  - 정답 세트 형식은 기존 `SAMPLE_DOCKER.json`과 같고, `status`는 `"draft — 사용자 검토 대기"`로 둔다.
  - 4개 이상 노트에 "Docker 설치 방법", "RAG 구축 과정" 같은 활동 명사구를 넣는다. 정답 개념은 대상(Docker, RAG)만 둔다.
  - 4개 이상 사례에 `known_concepts`를 넣는다. 본문 표기와 다른 표준 이름(예: 본문 "도커", known "Docker")을 포함한다.
- [ ] **Step 4: 통과 확인** — `test_bundled_gold_sets_fit_the_vocabulary`를 포함한 전체 테스트 통과
- [ ] **Step 5: 커밋** — `테스트: 지식 그래프 추출 정답 세트 12건 추가`

### Task 5: 기준선 측정 (체크포인트 — 코드 변경 없음)

- [ ] **Step 1: DB 진단** — `venv/bin/python -m graph_eval.audit` → 보고서의 수치가 스펙 "현재 상태" 표와 같은지 확인한다 (예: 그려지는 선 2,408).
- [ ] **Step 2: 연결 판정 초안** — `venv/bin/python -m graph_eval.links export` → Claude가 표본 노트와 상대 노트 본문을 읽고 `label`과 `comment`(판정 이유 한 줄)를 채운다.
- [ ] **Step 3: 검색 질문 초안** — Claude가 표본 노트에서 질문 25개와 정답 노트 id를 만들어 `local/questions.json`에 쓴다. 질문의 절반은 노트 제목·본문에 그대로 없는 표현으로 쓴다.
- [ ] **Step 4: 사용자 검토** — 판정 CSV(Excel)와 질문 파일, Task 4 정답 세트를 사용자가 검토하고 고친다. 정답 세트 `status`를 `"reviewed"`로 바꿔 커밋한다 (`테스트: 추출 정답 세트 검토 반영`).
- [ ] **Step 5: 기준선 실행** — `links score`, `retrieval`, `venv/bin/python -m graph_eval.run --runs 3`(가상 노트만 Gemini 전송). 이후 단계의 목표치와 "선 없는 노트" 허용 폭을 사용자와 정한다.

### Task 6: 관계 근거를 추출한 노트로 한정 + 희소성·중요도 반영

**Files:**
- Modify: `backend/routers/search.py` (`_PairEvidence.__init__`, `score`)
- Test: `backend/tests/test_ontology_features.py`

**Interfaces:**
- Consumes: `services.graph_retrieval.idf(total, df)`
- Produces: `_PairEvidence`의 공개 속성(`concepts`, `relations`, `keywords`, `evidence`, `graph_notes`, `hubs`)과 `/discoveries`·`/discoveries/routes` 응답 형식은 그대로 유지한다.

규칙 (스펙 ②):
- 공유 개념 c의 점수: `idf(total, df(c)) × min(w_a(c), w_b(c)) / 3`
- 노트 a에서 추출된 관계 (s, p, o)는 a와, s나 o를 가진 다른 노트 b를 잇는다. 점수는 `predicate_strength(p) × max over c ∈ {s, o} ∩ concepts(b) of idf(total, df(c)) × min(w_a(c), w_b(c)) / 3`이고, 같은 라벨이 여러 노트에서 나오면 쌍별로 최댓값을 쓴다.
- 쌍 점수 = 개념 점수 합 + `_RELATION_WEIGHT` × 관계 점수 합 + `_KEYWORD_WEIGHT` × 키워드 수
- `kind()`의 `relation` 판정은 지금처럼 `predicate_strength(p) >= 1.0`인 관계가 있는지로 한다. 점수가 아니라 관계 종류로 판정한다.

- [ ] **Step 1: 실패하는 테스트 작성·수정**
  - 새 테스트 `test_relation_from_third_note_does_not_link`: `_graph_fixture`에서 rag–faiss 항로가 없다 (FAISS→Embedding 관계는 emb 노트에서 나왔으므로).
  - 새 테스트 `test_mentioned_only_concept_links_weaker`: x는 Shared(w=3)를 가지고, y는 Shared(w=1), z는 Shared(w=3)를 가진다 → `/discoveries?note_id=x` 결과에서 z가 y보다 앞선다.
  - 새 테스트 `test_relation_to_rare_concept_links_stronger`: a가 `A —사용한다→ Rare`와 `A —사용한다→ Common`을 말하고, b는 Rare, c는 Common(그 외 Common을 가진 노트 3개)을 가진다 → a의 결과에서 b가 c보다 앞선다.
  - 기대값 수정 `test_routes_link_notes_by_shared_concept_and_relation`: rag–faiss 대신 emb–faiss 항로의 `relations == ["FAISS —사용한다→ Embedding"]`, `shared_concepts == ["FAISS"]`
  - 기대값 수정 `test_discoveries_use_concepts_and_relations`: rag의 결과가 `[emb]`이고, 전체 결과의 노트 집합은 그대로다.
- [ ] **Step 2: 실패 확인** — `venv/bin/python -m pytest tests/test_ontology_features.py -q` → 새 테스트와 수정한 테스트가 FAIL
- [ ] **Step 3: 구현** — `relation_rows`는 `GROUP BY` 없이 `r.note_id`를 포함해 읽는다. `concept_rows`는 `nc.weight`를 포함해 읽는다.
- [ ] **Step 4: 통과 확인** — 전체 테스트 통과 (`test_rare_shared_concept_ranks_above_common_one`, `test_hub_concept_is_not_route_evidence` 포함)
- [ ] **Step 5: 평가** — `audit`, `links export`(새로 나온 쌍 판정 → 사용자 확인), `links score`를 실행해 기준선과 비교한 결과를 보고한다.
- [ ] **Step 6: 커밋** — `수정: 항로 관계 근거를 그 관계를 추출한 노트로 한정`

### Task 7: 허브 비율·최소 점수 조정

**Files:**
- Modify: `backend/routers/search.py` (`_MIN_ROUTE_SCORE` 추가, `ranked_routes`와 `discoveries`에 적용)
- Modify: `backend/graph_eval/links.py` (`--min-score` 옵션)
- Test: `backend/tests/test_ontology_features.py`, `backend/tests/test_routes.py`

**Interfaces:**
- Produces: `routers.search._MIN_ROUTE_SCORE: float`(기본 0.0으로 동작 변화 없음). `ranked_routes`와 `/discoveries`는 `ev.score(k) < _MIN_ROUTE_SCORE`인 쌍을 뺀다. 확정 항로는 점수와 무관하게 유지한다.

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_weak_pairs_dropped_below_min_score` (monkeypatch로 `_MIN_ROUTE_SCORE = 100.0`) → `/discoveries/routes == []`, `/discoveries == []`
  - `test_confirmed_route_kept_below_min_score` (`test_routes.py`): 확정한 쌍은 `_MIN_ROUTE_SCORE = 100.0`에서도 응답에 `confirmed: True`로 남는다
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인**
- [ ] **Step 5: 조정** — 조합 6개(`--hub-share` 0.05/0.1/0.2 × `--min-score` 0과 Task 1 `audit`의 `line_score_p25`)로 `links export`(미판정 쌍 판정) → `links score`를 실행한다. 조정용 20개 정밀도로 고르고, 확인용 10개에서 3%p 넘게 떨어지지 않는지 본다. "선 없는 노트" 허용 폭을 지키는 조합 중 정밀도가 가장 높은 것을 상수에 반영한다. 결과표를 사용자에게 보고한다.
- [ ] **Step 6: 통과 확인 후 커밋** — `기능: 항로 허브 기준과 최소 점수 조정`

### Task 8: `kind` 다수결 + 마이그레이션

**Files:**
- Modify: `backend/db.py` (`note_concepts`에 `kind TEXT NOT NULL DEFAULT 'instance'` 추가: SCHEMA와 user_version 3 마이그레이션. 기존 행은 `concepts.kind`로 채움)
- Modify: `backend/services/graph_extraction.py` (`_resolve_concept`, `store_graph`, `clear_note_graph`; `recompute_kinds`, `VALID_STRUCT_SQL` 추가)
- Modify: `backend/routers/search.py` (관계 쿼리 2곳에 `JOIN concepts cs` + `VALID_STRUCT_SQL`), `backend/services/graph_retrieval.py` (`expand` 쿼리에 `VALID_STRUCT_SQL`)
- Test: `backend/tests/test_graph.py`, `backend/tests/test_db_migration.py`

**Interfaces:**
- Produces:
  - `graph_extraction.recompute_kinds(conn, concept_ids: Iterable[str]) -> None`: 각 개념의 `note_concepts.kind` 다수결을 `concepts.kind`에 쓴다. 동률이면 현재 값을 유지하고, 투표가 없으면 그대로 둔다.
  - `graph_extraction.VALID_STRUCT_SQL: str`: 별칭 `r`(relations), `cs`(주어 concept), `co`(목적어 concept)를 전제로 한 WHERE 조건. `인스턴스이다`는 `cs.kind='instance' AND co.kind='class'`, `하위클래스이다`는 `cs.kind='class' AND co.kind='class'`일 때만 참이고, 다른 관계는 항상 참이다.
- 동작:
  - `store_graph`는 노트 안의 kind(별칭으로 합쳐지면 class 우선, 기존 규칙)를 `note_concepts.kind`에 저장한 뒤 `recompute_kinds`를 호출한다. 관계는 다수결로 저장된 kind 기준으로 `_clean_relation`을 통과한 것만 저장한다.
  - `_resolve_concept`는 기존 개념의 kind를 덮어쓰지 않는다 (`UPDATE concepts SET kind` 제거).
  - `clear_note_graph`는 지우기 전에 그 노트의 개념 id를 모아 두고, 지운 뒤 `recompute_kinds`를 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성·수정**
  - 기대값 수정 `test_reextract_updates_kind_of_shared_concept` → 이름을 `test_shared_concept_kind_follows_majority`로 바꾼다. A: instance, B: class → instance 유지(동률). C: class를 추가하면 class.
  - `test_kind_recomputed_after_note_delete`: 노트 3개(class, class, instance) → class. class인 노트 2개를 삭제(`DELETE /notes/{id}`)하면 instance.
  - `test_invalid_struct_relation_skipped_in_routes_and_expand`: 다수결 결과와 맞지 않게 남은 `인스턴스이다` 관계를 SQL로 만든다 → `/discoveries/routes`의 `relations`에 없고, `graph_retrieval.expand` 결과의 경로에도 없다.
  - `test_migration_fills_note_concept_kind` (`test_db_migration.py`, 기존 파일 방식 따름): `note_concepts`에 kind 컬럼이 없는 user_version 2 DB → `init_db()` 후 컬럼이 `concepts.kind` 값으로 채워지고 user_version은 3
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — 전체 테스트 통과 (`test_alias_merge_in_one_note_keeps_relation_directions_valid` 포함)
- [ ] **Step 5: 운영 DB 적용** — 사용자 확인 → DB 백업 → 백엔드 재시작(마이그레이션 실행) → `audit`에서 `kind_violations` 확인. 지금 그래프는 노트별 투표가 한 종류뿐이라, 위반은 전체 재분석(Task 10) 뒤에 0이 되는 것이 정상이다. 다만 검색·연결에서는 바로 제외된다.
- [ ] **Step 6: 커밋** — `수정: 공유 개념 kind를 노트별 다수결로 결정`

### Task 9: 개념 이름 규칙 + 기존 개념 목록 제공

**Files:**
- Modify: `backend/services/graph_retrieval.py` (일치 규칙을 `mentions`로 분리해 `match_seeds`가 사용)
- Modify: `backend/services/graph_extraction.py` (`PROMPT` 규칙 추가, `known_concepts`, `build_prompt`, `call_model`/`_call_gemini` 시그니처, `process_note`)
- Modify: `backend/graph_eval/run.py` (`model_fn`의 호출이 `(content, known)`을 받고, `run`이 `case.get("known_concepts", [])`을 넘김)
- Test: `backend/tests/test_graph.py`, `backend/tests/test_graph_eval.py`

**Interfaces:**
- Produces:
  - `graph_retrieval.mentions(norm: str, qnorm: str, grams: set[str]) -> bool`: 영문·숫자로만 된 norm은 `norm in grams`, 그 외에는 `len(norm) >= 2 and norm in qnorm`. `match_seeds` 동작은 변화 없음.
  - `graph_extraction.KNOWN_LIMIT = 50`
  - `graph_extraction.known_concepts(conn, content: str, limit: int = KNOWN_LIMIT) -> list[str]`: 이름이나 동의어가 본문에 `mentions`되는 개념의 표준 이름. 조건은 kind ≠ literal, 2개 이상 활성 노트에서 쓰임, 이름이 3단어 미만이다. 노트 수 내림차순, 같으면 이름순으로 최대 limit개를 돌려준다.
  - `graph_extraction.build_prompt(content: str, known: Sequence[str] = ()) -> str`: `PROMPT`(끝의 `"노트:\n"`을 뗀 규칙 부분) + known이 있으면 아래 목록 블록 + `"노트:\n"` + `content[:MAX_INPUT_CHARS]`
  - `call_model(content: str, known: Sequence[str] = ()) -> str`; `_call_gemini(model: str, prompt: str) -> str` (프롬프트를 받는다)
  - `process_note`는 `known_concepts(conn, content)`를 계산해 `call_model`에 넘긴다.
- 프롬프트 "노드 규칙"에 추가할 문구 (원문 그대로):
  ```
  - name은 그 대상을 가리키는 가장 짧은 표준 이름으로 쓴다. "Docker 설치", "RAG 구축 방법" 같은 활동·작업 명사구는 노드로 만들지 말고, 대상(Docker, RAG)만 노드로 두고 내용은 관계로 나타낸다.
  - 세 단어 이상인 name은 제품명·책 제목 같은 고유명사일 때만 쓴다.
  ```
- 목록 블록 (원문 그대로, 항목마다 `- 이름` 한 줄):
  ```
  이미 쓰는 이름 (노트의 대상이 아래 이름과 같은 대상이면 그 이름을 그대로 name으로 쓴다. 같은 대상이 아니면 무시한다):
  ```

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_known_concepts_filters_and_orders`: Docker(노트 3개), Linux(노트 2개), Solo(노트 1개), `"Docker 설치 가이드 문서"`(노트 2개, 3단어 이상), literal 값 → 본문 `"도커 말고 Docker와 Linux, Solo, Docker 설치 가이드 문서"`에 대해 `["Docker", "Linux"]`
  - `test_known_concepts_respect_word_boundary`: 노트 2개에 있는 개념 `AI` → 본문 `"mail 서버 설정"`에서는 `[]`
  - `test_build_prompt_includes_rules_and_known`: `build_prompt("본문", ["Docker"])`에 `"가장 짧은 표준 이름"`, `"이미 쓰는 이름"`, `"- Docker"`가 들어 있고, 끝이 `"노트:\n본문"`. `build_prompt("본문")`에는 `"이미 쓰는 이름"`이 없다.
  - `test_process_note_passes_known_concepts`: `call_model`을 monkeypatch해 받은 `known`을 기록 → 기존 공유 개념 이름이 들어 있다.
  - `test_run_passes_known_concepts_to_model` (`test_graph_eval.py`): 가짜 호출이 `known`을 기록 → 사례의 `known_concepts`와 같다. 기존 `test_run_and_report_with_fake_model`의 가짜 호출은 `lambda text, known=(): answer`로 바꾼다.
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — `PROMPT`나 `_call_gemini(name, content)`를 쓰는 곳을 `grep -rn "PROMPT\|_call_gemini" backend`로 모두 찾아 바꾼다.
- [ ] **Step 4: 통과 확인** — 전체 테스트 통과
- [ ] **Step 5: 커밋** — `기능: 추출 프롬프트에 개념 이름 규칙과 기존 개념 목록 추가`

### Task 10: 추출 평가 → 전체 재분석 (체크포인트)

- [ ] **Step 1: 추출 평가** — `venv/bin/python -m graph_eval.run --runs 3`을 실행해 Task 5 기준선과 비교한다. 개념 재현율과 관계 정밀도·재현율의 3회 평균이 기준선 이상이 아니면 멈추고 보고한다. 같은 조건으로 `--model gemini-3.1-flash --runs 3`도 실행해 비교표에 넣는다 (스펙 ③-4: 비교만, 모델 교체는 별도 제안).
- [ ] **Step 2: 사용자 확인** — "노트 586개 본문이 Gemini로 다시 전송되고 약 1시간 걸림"을 알리고 승인을 받는다.
- [ ] **Step 3: 백업 후 재분석** — `cp spacenote.db spacenote.db.bak-<ts>` → `POST /graph/rebuild` → `GET /graph/status`에서 `pending`이 0이 될 때까지 기다린다. `failed`가 남으면 `POST /graph/retry-failed`를 실행한다.
- [ ] **Step 4: 재평가** — `audit`(`kind_violations` 0, 고립 비율·3단어 이상 비율 감소), `links export` → 판정 → `links score`, `retrieval`을 실행한다. Task 5와 Task 7 결과와 비교한 표를 사용자에게 보고한다. 채택 규칙을 어기면 백업으로 되돌릴지 사용자에게 묻는다.

### Task 11: 긴 노트 분할·병합 + 호출 단위 속도 제한

**Files:**
- Modify: `backend/services/graph_extraction.py` (`split_content`, `merge_graphs`, `process_note`)
- Modify: `backend/services/graph_worker.py` (`Throttle`, `_run`)
- Test: `backend/tests/test_graph.py`

**Interfaces:**
- Consumes: `known_concepts`, `call_model(content, known)`, `parse_graph` (Task 9)
- Produces:
  - `split_content(content: str, limit: int = MAX_INPUT_CHARS) -> list[str]`: `len(content) <= limit`이면 `[content]`. 아니면 앞에서부터 limit 안의 마지막 경계에서 자른다. 경계 우선순위는 코드 블록 밖의 줄 시작 `#` 제목 > 코드 블록 밖의 빈 줄 > limit 위치다. 모든 조각은 limit 이하이고, 이어 붙이면 원문과 같다.
  - `merge_graphs(graphs: list[dict]) -> dict`: `parse_graph` 결과 형식. 개념은 `norm`이 같거나 동의어 norm이 겹치면 합친다 (`weight`는 최댓값, 동의어는 합집합, 먼저 나온 이름 유지). 상한은 n = 조각 수일 때 개념 `min(15n, 30)`, literal `min(10n, 20)`, 관계 `min(25n, 50)`이다. 넘으면 weight 내림차순(같으면 먼저 나온 순)으로 남긴다. 빠진 개념을 가리키는 관계는 버리고, 중복 관계 `(s, p, o)`는 근거가 있는 쪽을 남긴다.
  - `process_note(note_id: str, before_call: Callable[[], None] | None = None) -> str`: 조각마다 `before_call()` → `known_concepts(conn, 조각)` → `call_model` → `parse_graph(응답, 조각)`. 근거 문장은 조각과 대조하는데, 조각이 원문의 부분 문자열이라 전체 대조와 같다. 형식 오류 시 1회 재시도하는 규칙은 조각 단위로 적용한다. 조각 하나라도 실패하면 기존 그래프를 그대로 두고 `failed`.
  - `graph_worker.Throttle(rate_per_minute: int = RATE_PER_MINUTE)`와 `.wait() -> None`: 마지막 호출로부터 `60/rate`초가 지날 때까지 `_stop.wait`로 기다린다. `_run`은 `process_note(note_id, before_call=throttle.wait)`로 호출하고, 노트 단위 대기 코드는 지운다.

- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_split_prefers_heading_and_keeps_code_blocks`: limit=100, 본문 = 60자 문단 + `"\n# 제목\n"` + 코드 블록(80자, 안에 빈 줄과 `# 주석` 줄 포함) + 문단 → 두 번째 조각이 `"# 제목"`으로 시작하고, 코드 블록이 한 조각 안에 온전히 있으며, `"".join(조각) == 본문`
  - `test_split_hard_cuts_when_no_boundary`: limit=100, 250자 코드 블록 → 조각 3개, 모두 100자 이하, 이어 붙이면 원문
  - `test_merge_graphs_unions_and_caps`: 두 그래프에 같은 개념(weight 1과 3)과 동의어로 겹치는 개념 → 하나로 합쳐지고 weight 3. 각 15개짜리 서로 다른 개념 그래프 3개를 합치면 30개.
  - `test_long_note_failure_keeps_existing_graph`: 기존 그래프를 저장한 노트 본문을 `split_content` 결과가 2조각이 되게 바꾸고, 두 번째 호출이 예외 → `failed`, `note_concepts`는 그대로
  - `test_process_note_calls_before_call_per_chunk`: 2조각 노트 → `before_call` 2회, `call_model` 2회
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 테스트에서는 `monkeypatch.setattr(ge, "MAX_INPUT_CHARS", 100)`로 조각을 만든다. `split_content`의 기본값은 호출 시점에 `MAX_INPUT_CHARS`를 읽도록 `limit: int | None = None`으로 둔다.
- [ ] **Step 4: 통과 확인** — 전체 테스트 통과 (`test_worker_waits_for_quiet_period` 포함)
- [ ] **Step 5: 커밋** — `기능: 긴 노트를 나눠 추출하고 호출 단위로 속도 제한`

### Task 12: 긴 노트 평가와 재추출 → 최종 보고 (체크포인트)

**Files:**
- Create: `backend/graph_eval/cases/LONG_NOTE.md`, `LONG_NOTE.json` (약 45,000자 가상 노트. 정답 개념 중 3개 이상은 40,000자 뒤에만 나온다)

- [ ] **Step 1: 정답 세트 추가 → 테스트 통과 → 커밋** — `테스트: 긴 노트 추출 정답 세트 추가`
- [ ] **Step 2: 평가** — `venv/bin/python -m graph_eval.run --runs 3 --cases LONG_NOTE` → 40,000자 뒤 정답 개념의 재현율을 보고한다.
- [ ] **Step 3: 운영 재추출** — 사용자 확인 → 백업 → 40,000자 초과 노트 25개만 `POST /graph/notes/{id}`로 재추출 → `audit`의 `tail_concepts`가 증가하는지 확인한다.
- [ ] **Step 4: 최종 재평가와 보고** — `audit`, `links score`, `retrieval`을 실행해 기준선(Task 5) → ②(Task 7) → ③(Task 10) → ④ 단계별 비교표를 사용자에게 보고한다.
