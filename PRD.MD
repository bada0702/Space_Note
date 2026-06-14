PRD (Product Requirements Document)
SpaceNote
AI 기반 우주형 지식 노트 시스템
내 머리속의 우주 , 지식으로 담다.
Version 0.3 (Updated: 2026-05-28)

---

1. 제품 개요 (Product Overview)

제품명: SpaceNote

제품 설명

SpaceNote는 Obsidian/Notion 수준의 노트 작성 기능을 핵심으로 하되,
AI가 노트 간 관계를 자동 발견하고 이를 우주 공간으로 시각화하는 지식 관리 플랫폼이다.

노트 작성이 메인이다.
우주 시각화(성도)는 노트 그래프 뷰의 확장이다.

사용자는
  노트를 작성하고
  AI가 관계를 발견하며
  성도(星圖)에서 자신의 지식 우주를 탐험한다.

핵심 비전
  지식을 저장하는 것이 아니라 항해한다

기술 기반
  SpaceNote는 D:\autology (Autology 온톨로지 그래프 빌더)의
  AI 파이프라인을 API 서비스로 적극 활용한다.
  노트 내용을 Autology에 전달하면 엔티티 추출 → 관계 매핑 → 검증이 자동으로 완료된다.

---

2. 문제 정의 (Problem Statement)

기존 노트 앱의 문제
  Obsidian  → 수동 링크, AI 없음, 그래프 뷰가 복잡하고 못생김
  Notion    → 클라우드 의존, 프라이버시 문제, 느림
  Roam      → 가파른 학습 곡선, 고비용

공통 문제
  노트는 많은데 연결된 지식을 발견하기 어렵다
  수동으로 링크를 만들어야 해서 귀찮다
  그래프 뷰는 너무 복잡해서 실제로 잘 안 쓴다

SpaceNote의 해법
  AI가 자동으로 관계를 찾아준다
  우주 메타포로 그래프를 탐험하고 싶게 만든다
  로컬 우선, 데이터 소유권은 사용자에게

---

3. 제품 목표 (Goals)

G1. 노트 작성 최우선
    빠르고 방해받지 않는 Markdown 편집 경험을 제공한다.

G2. AI 기반 관계 자동 발견
    수동 링크 없이도 AI가 노트 간 숨겨진 연결을 찾아낸다.

G3. 우주형 그래프 탐험
    지식 그래프를 우주 공간에서 탐험하는 경험을 제공한다.

G4. 로컬 우선 / 개방 구조
    모든 데이터는 로컬 .md 파일로 저장된다. Obsidian vault 호환.

G5. 저사양 실행
    고사양 GPU 없이, 일반 노트북에서도 원활히 동작한다.

---

4. 핵심 컨셉 (Core Concept)

우주 메타포 구조

  요소       의미                   노트 매핑
  ─────────────────────────────────────────────
  은하        카테고리 (항해일지 분류)  항해일지 카테고리
  성단        주제 그룹              태그 클러스터
  항성        핵심 노트              자주 참조되는 노트
  행성        세부 노트              항성에 연결된 노트
  항로        관계 연결              노트 간 링크
  성운        미분류 아이디어         태그/연결 없는 노트
  블랙홀      보관 노트              보관된 노트

카테고리 ↔ 은하 자동 매핑 원칙

  항해일지에서 카테고리를 생성하면 성도에 은하가 자동 생성된다.
  해당 카테고리에 속한 노트는 그 은하 안에 배치된다.
  카테고리 삭제 → 은하 해체 (노트는 성운으로 이동)

  항해일지 카테고리    성도 은하
  연구               ●  파랑 은하
  프로젝트            ●  진홍 은하
  아이디어            ●  초록 은하
  개인               ●  황금 은하
  (미분류)           →  성운 영역

---

5. 대상 사용자 (Target Users)

Primary
  연구자 — 논문/자료 정리, 개념 연결
  개발자 — 기술 노트, 프로젝트 기록
  전략 기획자 — 아이디어 관리, 보고서 기초
  크리에이터 — 작업 로그, 영감 기록
  PKM 사용자 — 개인 지식 관리 (Obsidian 대체)

Secondary
  학생 — 강의 노트, 시험 준비
  작가 — 자료 조사, 스토리 구조

---

6. 핵심 기능 (Core Features)

6.1 항해일지 (노트 목록 + 카테고리 관리) (PRIMARY)
    SpaceNote의 메인 진입점.
    카테고리를 만들고, 각 카테고리 안에 노트(항해일지)를 생성한다.

    카테고리 관리
      + 새 카테고리 생성 → 성도에 은하 자동 생성
      카테고리 이름 변경 → 은하 이름 동기화
      카테고리 색상 지정 → 은하 색상 동기화
      카테고리 삭제 → 노트는 미분류(성운)로 이동

    노트 목록 보기
      전체 목록 (모든 카테고리 통합)
      카테고리별 보기 (은하별 필터)
      최근 수정 순
      오늘 작성한 노트
      + 새 항해일지 (노트 생성, 카테고리 선택)

    예시 구조
      ▶ 연구 (은하)
          드론 군집 제어.md
          센서 융합.md
      ▶ 프로젝트 (은하)
          SpaceNote 개발.md
      ▶ 아이디어 (은하)
          미래 기능 아이디어.md
      ─ 미분류 (성운)
          임시 메모.md

6.2 노트 편집기 (EDITOR)
    SpaceNote의 핵심 기능.

    지원 기능
      Markdown 실시간 편집 (Monaco Editor 기반)
      편집 / 미리보기 / 성도 탭 전환
      [[위키링크]] 자동완성
      코드 블록 신택스 하이라이팅
      수식 (KaTeX)
      표, 체크리스트, 인용
      자동 저장 (1초 디바운스)
      이미지/PDF 첨부 (로컬 파일)

    저장 방식
      로컬 .md 파일 (Obsidian vault 호환)
      메타데이터는 YAML frontmatter

    예시 frontmatter
      ---
      title: 드론 군집 제어 연구
      tags: [AI, 드론, 연구]
      category: 연구              ← 카테고리 = 은하
      created: 2026-05-28
      ---

6.3 은하 지도 (파일 트리 뷰)
    카테고리(은하)와 노트를 계층 구조로 탐색한다.
    항해일지와 동일한 카테고리 구조를 트리 형태로 표시.

    지원 기능
      카테고리(은하) 접기 / 펼치기
      드래그 앤 드롭 이동 (카테고리 간 노트 이동)
      노트 우클릭 메뉴
      최근 수정 노트 강조 표시
      빠른 노트 생성 (폴더 옆 + 버튼)

6.4 AI 엔티티 추출 (Autology 활용)
    Autology API를 호출해 노트 내 개념을 자동 추출한다.

    흐름
      노트 저장 → 백그라운드 분석 대기열 → Autology API 호출
      → 엔티티/관계 결과 → SQLite 저장 → 성도 업데이트

    Autology 연동
      POST http://localhost:8000/jobs/start
      body: { "topic": "<노트 내용>" }
      WebSocket으로 실시간 진행 상황 수신

6.5 미개척 항로 (AI 연결 발견)
    AI가 발견한 숨겨진 연결을 보여준다.
    수동으로 링크하지 않아도 의미적으로 연결된 노트를 추천한다.

    표시 항목
      추천 연결 (신뢰도 표시)
      발견된 공통 개념
      연결 수락 / 거절 버튼

6.6 성도 (우주 그래프 뷰)
    노트 그래프를 우주 공간으로 시각화한다.
    노트 편집기의 탭 중 하나로 접근 가능.

    렌더러: Pixi.js v8 (WebGL + Canvas 자동 폴백)
    레이아웃: D3-force (WebWorker)

    우주 시각화 (색상 적용 구간)
      은하별 색상 구분
      항성 밝기 = 연결 수 / 최근 수정 기반
      항로 = 관계 연결선
      성운 = 흐릿한 미연결 노드
      배경 = 별 파티클

    인터랙션
      드래그 / 줌 / 패닝
      노드 클릭 → 해당 노트 열기
      노드 우클릭 → 컨텍스트 메뉴
      미니맵 (우하단)

6.7 항법 (전체 검색)
    의미 기반 검색 + 전문 검색을 지원한다.

    지원
      전문 검색 (SQLite FTS)
      의미 검색 (ChromaDB + sentence-transformers)
      예: "드론 통신" 검색 → RF 간섭, 네트워크 지연 등도 결과에 포함

6.8 성운 (미분류 노트)
    태그도 없고, 연결도 없는 노트 모음.
    정리가 필요한 노트를 한 곳에 모아 보여준다.

---

7. 메뉴 구성 (Menu Structure)

7.1 전체 레이아웃

┌───────────────────────────────────────────────────────────────┐
│  SpaceNote                [탐색창________________]  [다크/라이트] │
├──────────┬────────────────────────────────────────────────────┤
│          │  [← →]  항해일지 / 드론 연구            [편집|미리보기|성도] │
│  SIDEBAR ├────────────────────────────────────────────────────┤
│          │                                                     │
│ 항해일지  │                                                     │
│ 은하 지도  │           NOTE EDITOR                              │
│          │          (Monaco Editor)                            │
│ ────────  │                                                     │
│ 성도      │                                                     │
│ 미개척    │                                                     │
│ 항로      │                                                     │
│          │                                                     │
│ ────────  │                                                     │
│ 항법      │                                                     │
│ 설정    │                                                     │
│          │                                                     │
│ ────────  │                                                     │
│ 성운      │                                                     │
└──────────┴────────────────────────────────────────────────────┘

7.2 사이드바 메뉴 구조

SpaceNote
────────────────────

항해일지                   ← 카테고리 + 노트 목록 (메인 진입점)
  ▶ 연구                  ← 카테고리 = 성도의 은하
      드론 군집 제어.md
      센서 융합.md
  ▶ 프로젝트               ← 카테고리 = 성도의 은하
      SpaceNote 개발.md
  ▶ 아이디어               ← 카테고리 = 성도의 은하
  ─ 미분류                ← 카테고리 없는 노트 → 성운
  + 새 카테고리 (은하 생성)
  + 새 항해일지

은하 지도                  ← 같은 카테고리를 트리 형태로 탐색
  연구/
    드론 군집 제어.md
    센서 융합.md
  프로젝트/
  아이디어/

────────────────────

성도                       ← 우주 그래프 뷰 (보조)
미개척 항로                ← AI 발견 연결/인사이트

────────────────────

항법                       ← 전체 검색
설정                     ← 앱 설정

────────────────────

성운                       ← 미분류/미연결 노트


7.3 메뉴명 대응표

  SpaceNote 메뉴명    기능                  Obsidian 대응
  ─────────────────────────────────────────────────────
  항해일지            노트 목록              Files (All notes)
  은하 지도           폴더 탐색기            File Explorer
  성도               우주 그래프 뷰         Graph View
  미개척 항로         AI 발견 연결          (없음, AI 기능)
  항법               전체 검색             Search
  설정             앱 설정              Settings
  성운               미분류 노트           Unlinked mentions


7.4 노트 영역 상단 탭

  [편집]  [미리보기]  [성도]

  편집    → Monaco 에디터 (Markdown)
  미리보기 → 렌더링된 노트
  성도    → 이 노트 중심의 우주 뷰 (색상 있음)


7.5 우측 패널 (토글)

  ──────────────────
  연결된 항로              ← 이 노트와 연결된 노트
    드론 프로젝트 (참조)
    AI 연구 (관련)

  발견된 항성              ← AI 추출 엔티티
    드론 / 센서 융합 / RF

  항로 분류               ← 태그
    #AI  #연구  #드론
  ──────────────────


7.6 컨텍스트 메뉴 (노트 우클릭)

  열기
  새 탭에서 열기
  ──────────
  이름 변경
  은하 이동 (폴더 이동)
  ──────────
  AI 재분석
  성도에서 보기
  ──────────
  보관 (블랙홀)
  삭제


7.7 성도 인터랙션

  마우스 드래그    우주 패닝
  스크롤          줌 인 / 아웃
  클릭            노드 선택 → 노트 미리보기
  더블클릭        해당 노트 열기
  우클릭          컨텍스트 메뉴
  미니맵 (우하단)  현재 위치 표시

---

8. 디자인 시스템 (Design System)

8.1 디자인 원칙

  메뉴 / 텍스트 / UI 요소  흑백만 사용
  우주 캔버스 (성도)        색상 허용 (은하별 컬러, 항성 밝기)
  아이콘                   없음 (텍스트 + 선 + 기하학 도형만)
  로고                     단일 기하학 도형 (궤도선 + 점)
  선택 상태                좌측 세로선 또는 밑줄


8.2 색상 팔레트

  다크 모드
  ─────────────────────────────
  앱 배경       #0A0A0A
  패널 배경     #111111
  경계선        #1E1E1E
  텍스트 기본   #F0F0F0
  텍스트 보조   #555555
  선택 강조     #F0F0F0 (텍스트 밝아짐 + 좌측 선)
  입력창 배경   #161616

  라이트 모드
  ─────────────────────────────
  앱 배경       #FAFAFA
  패널 배경     #FFFFFF
  경계선        #E8E8E8
  텍스트 기본   #0A0A0A
  텍스트 보조   #AAAAAA
  선택 강조     #0A0A0A (텍스트 진해짐 + 좌측 선)
  입력창 배경   #F5F5F5

  우주 캔버스 (항상 다크, 테마 무관)
  ─────────────────────────────
  배경          #020408
  은하 1        #3B5BDB  (파랑)
  은하 2        #C2255C  (진홍)
  은하 3        #2F9E44  (초록)
  은하 4        #E67700  (황금)
  항성          #FFFFFF  (흰색, 밝기 가변)
  항로          #FFFFFF  10-30% 투명도
  성운          #FFFFFF  5% 투명도


8.3 타이포그래피

  UI 폰트    Pretendard (한글) / Inter (영문)
  에디터 폰트  JetBrains Mono (코드 블록)
  사이드바    13px, letter-spacing: 0.02em
  노트 제목   24px, weight 600
  본문        16px, line-height 1.7


8.4 사이드바 선택 상태 표현 (아이콘 없음)

  비선택
    항해일지

  선택 (좌측 세로선 2px)
  │ 항해일지

  호버 (텍스트 밝아짐)
    항해일지   ← 보조색 → 기본색으로 변환


8.5 로고

  텍스트: SpaceNote  (Pretendard 600)
  심볼:   타원형 궤도선 + 중심점  (기하학 도형)
         다크모드: 흰색
         라이트모드: 검정

  예시 (ASCII)
       ·
    ─────────
         ·       →  S  SpaceNote
    ─────────
       ·

---

9. 시스템 구조 (Architecture)

9.1 전체 아키텍처

┌─────────────────────────────────────────────────────────┐
│                   SpaceNote Desktop                       │
│                   (Tauri + React)                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Frontend (React 18 + TS)              │  │
│  │                                                    │  │
│  │  NoteEditor   FileTree   SpaceCanvas  SearchBar    │  │
│  │  (Monaco)    (은하지도)  (Pixi.js)    (항법)        │  │
│  └──────────────────────┬─────────────────────────────┘  │
│                         │ Tauri IPC / HTTP                │
│  ┌──────────────────────▼─────────────────────────────┐  │
│  │         SpaceNote Backend (FastAPI :8001)           │  │
│  │                                                    │  │
│  │   NoteService  GraphService  SearchService          │  │
│  │   (SQLite)     (SQLite)      (ChromaDB)             │  │
│  │                    │                               │  │
│  │         ┌──────────▼──────────┐                   │  │
│  │         │  Autology Client    │                   │  │
│  │         │  (httpx async)      │                   │  │
│  └─────────┴──────────┬──────────┴───────────────────┘  │
│                       │ HTTP/WebSocket                    │
│  ┌────────────────────▼────────────────────────────────┐ │
│  │       Autology Backend (FastAPI :8000)               │ │
│  │   Research → Extraction → Relation → Validation      │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘


9.2 기술 스택

  Frontend
  ────────────────────────────────────────────
  React 18 + TypeScript      UI 컴포넌트
  Tauri v2                   .exe 패키징 (3-8MB)
  Monaco Editor              노트 편집기
  Pixi.js v8                 우주 그래프 렌더러 (WebGL + Canvas 폴백)
  D3-force (WebWorker)       그래프 레이아웃 계산
  Zustand                    전역 상태 관리
  TailwindCSS                스타일링
  Framer Motion              애니메이션

  Backend
  ────────────────────────────────────────────
  FastAPI (Python 3.10+)     API 서버 (:8001)
  SQLite                     노트 / 메타데이터 / 그래프 저장
  ChromaDB                   벡터 검색 (의미 검색)
  sentence-transformers      로컬 임베딩
  httpx                      Autology API 호출
  chokidar (Node)            파일 시스템 감시

  패키징
  ────────────────────────────────────────────
  Tauri v2                   .exe 빌드 (~5MB)
  Rust                       Tauri 빌드 의존성 (1회 설치)
  사전 번들                   Python 백엔드 (PyInstaller)


9.3 배포 구조 (.exe)

  SpaceNote.exe 실행 시
    1. Tauri 쉘 → Python 백엔드 자동 실행 (내장 바이너리)
    2. SpaceNote 백엔드 :8001 시작
    3. Autology 백엔드 :8000 자동 시작 (D:\autology\start.bat)
    4. Tauri WebView에 React 앱 로드
    5. 사용자에게 로딩 화면 → 완료

  폴더 구조
    SpaceNote.exe
    resources/
      backend/          ← PyInstaller로 패키징된 Python 백엔드
      autology/         ← Autology 백엔드 (선택적 내장 또는 별도 경로 지정)


9.4 데이터 저장

  노트 파일    사용자 지정 폴더 / .md 파일 (Obsidian 호환)
  메타데이터   %APPDATA%/SpaceNote/db.sqlite
  벡터 인덱스  %APPDATA%/SpaceNote/chroma/
  설정        %APPDATA%/SpaceNote/config.json

---

10. 데이터 구조 (Data Structure)

10.1 카테고리 (= 은하) (SQLite)

  CREATE TABLE categories (
    id         TEXT PRIMARY KEY,
    name       TEXT UNIQUE,         -- 카테고리명 = 은하명
    color      TEXT,                -- 성도에서 사용할 은하 색상 (#RRGGBB)
    icon       TEXT,                -- 선택적 기하학 심볼
    sort_order INTEGER,
    created_at TEXT
  );

  -- 기본 생성 시 성도 은하 자동 생성 트리거
  -- category.name 변경 → galaxy.name 동기화

10.2 노트 메타데이터 (SQLite)

  CREATE TABLE notes (
    id          TEXT PRIMARY KEY,
    path        TEXT UNIQUE,        -- 실제 .md 파일 경로
    title       TEXT,
    content     TEXT,               -- 캐시 (파일이 원본)
    category_id TEXT,               -- categories.id (= 은하 소속)
    tags        TEXT,               -- JSON 배열
    word_count  INTEGER,
    analysis_status TEXT,           -- pending / analyzed / failed
    created_at  TEXT,
    modified_at TEXT,
    FOREIGN KEY (category_id) REFERENCES categories(id)
  );

10.3 그래프 데이터 (SQLite)

  CREATE TABLE entities (
    id         TEXT PRIMARY KEY,
    note_id    TEXT,
    type       TEXT,               -- Class / Instance / Literal
    label      TEXT,
    confidence REAL
  );

  CREATE TABLE relations (
    id          TEXT PRIMARY KEY,
    source_id   TEXT,              -- note_id 또는 entity_id
    target_id   TEXT,
    type        TEXT,              -- related-to / is-a / part-of 등
    weight      REAL,
    auto_detected INTEGER          -- 1: AI 발견, 0: 수동
  );

10.4 성도 노드 위치 (SQLite)

  CREATE TABLE node_positions (
    note_id   TEXT PRIMARY KEY,
    x         REAL,
    y         REAL,
    locked    INTEGER              -- 1: 사용자 고정, 0: 레이아웃 자동
  );

---

11. 성능 전략 (Performance Strategy)

핵심 원칙: AI 분석은 백그라운드에서, 노트 저장은 즉시

  단계              처리                     비고
  ────────────────────────────────────────────────────────
  노트 저장          즉시 (파일 I/O)           블로킹 없음
  임베딩 생성        저장 후 2초 (비동기)       ChromaDB 인덱스
  AI 분석 대기       저장 후 큐 등록            Autology API 호출 대기
  AI 분석 실행       유휴 시 또는 수동 트리거    노트당 최대 30초
  성도 레이아웃      WebWorker (D3-force)      메인 스레드 차단 없음
  성도 렌더링        Pixi.js (WebGL 우선)       Canvas 폴백 자동

Pixi.js 성능 목표
  500 노드   60 FPS (WebGL/Canvas 모두)
  3,000 노드  60 FPS (WebGL), 30 FPS (Canvas 폴백)
  저사양 CPU  Canvas 폴백으로 자동 전환

최적화
  현재 뷰 노드만 렌더링 (뷰포트 컬링)
  Force 레이아웃 결과 캐싱 (변경 없으면 재계산 안 함)
  Autology 분석 결과 캐싱 (동일 내용 재분석 방지)
  성도는 별도 탭 — 열지 않으면 렌더링 없음

---

12. MVP 범위 (MVP Scope)

포함 (Phase 1-3)
  Markdown 노트 편집기 (Monaco)
  은하 지도 (폴더 탐색기)
  기본 태그 / 항로 분류
  전문 검색
  Autology AI 엔티티 추출
  성도 기본 (Pixi.js 2D 그래프)
  다크 / 라이트 테마
  Tauri .exe 패키징

제외 (MVP 이후)
  멀티유저 / 클라우드 동기화
  실시간 협업
  모바일 앱
  VR/AR 모드

---

13. 개발 로드맵 (Roadmap)

Phase 1 — 노트 핵심 (2주)
  목표: 동작하는 노트 앱
  - Tauri + React + TypeScript 프로젝트 설정
  - Monaco 에디터 통합
  - 로컬 .md 파일 CRUD (chokidar 감시)
  - 은하 지도 (폴더 탐색기)
  - Markdown 미리보기
  - 다크 / 라이트 테마 전환
  - 기본 단축키 (Ctrl+S, Ctrl+P)

Phase 2 — Autology AI 통합 (2주)
  목표: AI가 자동으로 관계를 만든다
  - Autology API 클라이언트 구현 (httpx)
  - 노트 저장 시 백그라운드 AI 분석 트리거
  - 엔티티 / 관계 결과 SQLite 저장
  - ChromaDB 임베딩 파이프라인
  - 의미 검색 (항법)
  - 미개척 항로 패널 (추천 연결 표시)

Phase 3 — 성도 (우주 뷰) (2주)
  목표: 노트 그래프를 우주에서 탐험한다
  - Pixi.js + D3-force WebWorker 설정
  - 노드 렌더링 (항성 / 행성 / 성운)
  - 은하별 색상 구분
  - 클릭 → 노트 열기 연동
  - 줌 / 패닝 / 미니맵
  - 편집 탭에서 성도 탭 전환

Phase 4 — 완성도 (1주)
  목표: 출시 가능한 품질
  - Tauri .exe 빌드 설정 (PyInstaller 백엔드 내장)
  - 온보딩 플로우
  - 설정 화면 (Ollama 모델, Autology 경로)
  - [[위키링크]] 자동완성
  - 성운 패널 (미분류 노트 정리)
  - 에러 처리 및 복구

---

14. 추가 기능 (Additional Features)

단기 (Phase 3-4 포함)
  노트 관련
    노트 템플릿 (일일 기록, 프로젝트, 회의)
    노트 버전 히스토리 (간단한 diff)
    PDF/이미지 첨부 → 텍스트 추출
    [[위키링크]] 자동완성 + 미리보기
    핀 고정 노트

  탐험 관련
    오늘 방문한 노트 경로 추적
    최근 7일 활동 히트맵
    가장 많이 연결된 항성 TOP 10
    고립된 성운 알림 (연결 없는 노트)

중기 (Phase 5 이후)
  Obsidian vault 양방향 동기화
  노트 통계 대시보드
  PDF 내보내기
  Notion 임포트

장기 비전 (v2+)
  클라우드 동기화 (선택적, E2E 암호화)
  모바일 뷰어 앱
  AI 대화형 탐험 ("이 노트와 관련된 걸 찾아줘")
  플러그인 시스템

---

15. 리스크 (Risks)

  리스크              설명                    대응
  ───────────────────────────────────────────────────────
  Tauri Rust 빌드     처음 설정이 복잡         Docker 빌드 또는 CI 활용
  Autology 의존성     Autology 서버 다운 시     기본 기능은 Autology 없이 동작
  Canvas 폴백 성능    저사양에서 3,000 노드      뷰포트 컬링 + 노드 수 제한 (현재 은하만)
  파일 충돌           Obsidian과 동시 사용       chokidar 감시 + 충돌 알림
  AI 분석 품질        Autology 잘못된 연결       사용자 수동 수정 + 신뢰도 임계값

---

16. 성공 지표 (Success Metrics)

  항목                    목표
  ──────────────────────────────────────
  노트 저장 속도          즉시 (< 100ms)
  앱 시작 시간            < 3초
  검색 응답              < 500ms
  AI 분석 완료            < 30초 / 노트
  성도 FPS (WebGL)        60 FPS / 3,000 노드
  성도 FPS (Canvas 폴백)  30 FPS / 500 노드
  .exe 파일 크기          < 50MB (백엔드 포함)

---

17. 기술 의존성 (Dependencies)

  의존성                  버전        용도
  ──────────────────────────────────────────────────
  Autology               D:\autology  AI 파이프라인
  Ollama                 최신         로컬 LLM
  Node.js                18+          프론트엔드 빌드
  Python                 3.10+        백엔드
  Rust                   최신         Tauri 빌드 (1회)
  Tauri CLI              v2           .exe 패키징

  실행 순서
    1. cd D:\autology && start.bat      → :8000
    2. cd D:\Space_Note_v100 && start.bat → :8001 + Tauri 앱

---

18. 장기 비전 (Vision)

SpaceNote는 노트 앱이다.
그런데 보통 노트 앱과 다르게, 당신이 기록한 것들이 서로 연결되기 시작한다.
AI가 찾아내는 연결은 당신이 몰랐던 것들이다.
성도를 열면 그 연결들이 우주처럼 펼쳐진다.

사용자는 기록하고, AI는 발견하고, 성도는 보여준다.
