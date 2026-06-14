# SpaceNote 구현 계획

> 상세 플랜: `docs/superpowers/plans/`
> 설계 스펙: `docs/superpowers/specs/2026-05-28-spacenote-design.md`

---

## 제품 개요

**SpaceNote** — Obsidian/Notion 수준의 노트 앱. AI가 노트 간 관계를 자동 발견하고 우주 공간(성도)으로 시각화한다.

- **노트 작성이 메인**, 우주 시각화는 보조
- 카테고리(은하) 생성 → 성도에 은하 자동 생성
- 모든 데이터는 로컬 .md 파일 (Obsidian vault 호환)

---

## 아키텍처

```
Tauri v2 .exe (~5MB)
  └── React 18 + TypeScript (프론트엔드)
        ├── Monaco Editor      노트 편집
        ├── Pixi.js v8         성도 렌더러 (WebGL + Canvas 폴백)
        └── D3-force Worker    그래프 레이아웃

  └── FastAPI :8001 (SpaceNote 백엔드)
        ├── SQLite             노트 / 카테고리 / 그래프
        ├── ChromaDB           벡터 검색
        └── httpx → Autology :8000 (AI 파이프라인)

  └── Autology FastAPI :8000 (기존 AI 백엔드 재사용)
```

---

## 메뉴 구조

```
[사이드바]
항해일지 ← 카테고리 + 노트 목록 (메인)
  ▶ 연구 (은하)
  ▶ 프로젝트 (은하)
은하 지도 ← 트리 탐색기
───────────
성도 ← 우주 그래프 뷰
미개척 항로 ← AI 발견 연결
───────────
항법 ← 전체 검색
⚙ 설정
───────────
성운 ← 미분류 노트

[노트 상단 탭]
편집 | 미리보기 | 성도
```

---

## 개발 로드맵

### Phase 1 — 핵심 노트 앱 (2주)
**플랜:** `docs/superpowers/plans/2026-05-28-phase1-core-note-app.md`

| Task | 내용 |
|------|------|
| 1 | Tauri v2 + React 18 + TypeScript 프로젝트 설정 |
| 2 | FastAPI + SQLite 백엔드 초기 설정 |
| 3 | 카테고리 CRUD API + 테스트 |
| 4 | 노트 CRUD API + .md 파일 동기화 |
| 5 | TypeScript 타입 + Zustand 스토어 |
| 6 | 다크/라이트 테마 + 앱 레이아웃 |
| 7 | 항해일지 사이드바 (카테고리 + 노트 목록) |
| 8 | Monaco 에디터 + Markdown 미리보기 + 탭 전환 |
| 9 | Vault 경로 설정 + 앱 초기화 |
| 10 | start.bat + 통합 테스트 |

**완료 기준:** 카테고리 생성 → 노트 작성 → .md 저장 → 미리보기 → 테마 전환

---

### Phase 2 — AI 통합 (2주)

| Task | 내용 |
|------|------|
| 1 | Autology httpx 클라이언트 + 분석 큐 |
| 2 | 노트 저장 시 백그라운드 AI 분석 트리거 |
| 3 | 엔티티 / 관계 결과 SQLite 저장 |
| 4 | ChromaDB 임베딩 파이프라인 (sentence-transformers) |
| 5 | 항법 — 전문 검색 (SQLite FTS5) |
| 6 | 항법 — 의미 검색 (ChromaDB) |
| 7 | 미개척 항로 패널 (추천 연결 표시) |
| 8 | 분석 상태 UI (pending / analyzing / done) |

**완료 기준:** 노트 저장 → Autology 분석 → 연결 추천 표시

---

### Phase 3 — 성도 (우주 그래프) (2주)

| Task | 내용 |
|------|------|
| 1 | Pixi.js v8 + D3-force WebWorker 설정 |
| 2 | 노드 렌더링 (항성/행성/성운) |
| 3 | 은하별 색상 구분 (카테고리 color 반영) |
| 4 | 항로 (관계선) 렌더링 |
| 5 | 배경 별 파티클 |
| 6 | 드래그 / 줌 / 패닝 |
| 7 | 노드 클릭 → 노트 열기 연동 |
| 8 | 미니맵 (우하단) |
| 9 | 편집 탭 ↔ 성도 탭 전환 연동 |

**완료 기준:** 500 노드 @ 60 FPS, 카테고리별 은하 색상, 클릭 연동

---

### Phase 4 — AI 채팅 + RAG (예정)

| Task | 내용 |
|------|------|
| 1 | 백엔드: `/api/ai/chat` 엔드포인트 (스트리밍) |
| 2 | 멀티 모델 지원: Claude (Anthropic API), Gemini (Google API), ChatGPT (OpenAI API) |
| 3 | 앱 설정 화면에서 API 키 관리 (로컬 저장, 암호화) |
| 4 | RAG 파이프라인: 노트 내용 → ChromaDB 임베딩 → 쿼리 시 관련 노트 자동 첨부 |
| 5 | 사이드바 "AI 채팅" 메뉴 — 채팅 UI (스트리밍 응답) |
| 6 | 채팅 컨텍스트: 현재 열린 노트 / 현재 카테고리 / 전체 노트 선택 가능 |
| 7 | Wikipedia 검색 도구 (AI가 필요 시 자동 호출, 결과를 답변에 인용) |
| 8 | 지식 그래프 연동: AI 답변에서 언급된 노트에 자동 링크 생성 |

**완료 기준:** AI와 대화 → 현재 노트 기반으로 답변 → Wikipedia 리서치 자동 수행

---

### Phase 5 — 완성도 + 배포 (1주)

| Task | 내용 |
|------|------|
| 1 | [[위키링크]] 자동완성 (Monaco 커스텀 컴플리션) |
| 2 | 성운 패널 (미분류 노트) |
| 3 | 제어판 (Vault 경로, Ollama 설정) |
| 4 | PyInstaller로 Python 백엔드 번들 |
| 5 | Tauri .exe 빌드 + 리소스 패킹 |
| 6 | 온보딩 플로우 |
| 7 | 에러 처리 (Autology 없을 때 graceful degradation) |

**완료 기준:** SpaceNote.exe 단일 파일 실행, < 50MB

---

## 데이터 모델 (핵심)

```sql
-- 카테고리 = 성도 은하
CREATE TABLE categories (
  id TEXT PRIMARY KEY, name TEXT UNIQUE, color TEXT, sort_order INTEGER, created_at TEXT
);

-- 노트 = .md 파일 + 메타데이터 캐시
CREATE TABLE notes (
  id TEXT PRIMARY KEY, path TEXT UNIQUE, title TEXT, content TEXT,
  category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
  tags TEXT DEFAULT '[]', word_count INTEGER, analysis_status TEXT,
  created_at TEXT, modified_at TEXT
);
```

---

## 성능 목표

| 항목 | 목표 |
|------|------|
| 노트 저장 | < 100ms |
| 앱 시작 | < 3초 |
| 검색 응답 | < 500ms |
| AI 분석 | < 30초/노트 |
| 성도 FPS (WebGL) | 60 FPS / 3,000 노드 |
| .exe 크기 | < 50MB |

---

## 빠른 시작

```powershell
# 1. Autology 백엔드 먼저 실행
cd D:\autology && start.bat

# 2. SpaceNote 실행
cd D:\Space_Note_v100 && start.bat
```
