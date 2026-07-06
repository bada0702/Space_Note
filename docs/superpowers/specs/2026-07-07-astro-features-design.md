# 천문 기능 4종 — 기항지·블랙홀·항로 승격·초신성

날짜: 2026-07-07
상태: 승인됨 (사용자 확인)

## 배경

PRD의 우주 메타포 개념 중 미구현 항목을 선별해 도입한다. 사용자가 선택한 기능은
기항지(즐겨찾기), 블랙홀(보관), 항로 승격(관측소 흐름), 초신성(발견 이벤트) 4가지.
항도·성문·중력권은 현재 노트 규모 대비 가치가 낮아 이번 범위에서 제외한다.

공통 원칙:

- 기존 패턴에 얹는다 — SQLite PRAGMA 마이그레이션(`backend/db.py`의 `norm` 컬럼
  추가 방식), zustand store, Three.js 성도(`StarMapCanvas.tsx`).
- 웹 UI 품질을 우선한다. 각 기능은 성도 시각 요소를 1개 이상 가진다.
- 구현 순서: 기항지 → 블랙홀 → 항로 승격 → 초신성 (초신성은 항로 데이터에 의존).

## 기능 1 — 기항지 (즐겨찾기)

### 백엔드

- `notes` 테이블에 `is_favorite INTEGER NOT NULL DEFAULT 0` 컬럼 추가.
  `init_db()`에서 `PRAGMA table_info(notes)`로 존재 확인 후 `ALTER TABLE`.
- `NotePatch`에 `is_favorite: Optional[bool]` 추가 — 기존 `PATCH /notes/{nid}`로
  토글. 별도 엔드포인트 없음.
- `_row_to_note()` 응답에 `is_favorite` 포함 (SQLite 정수 → bool 변환).
- 즐겨찾기 여부는 .md frontmatter에 쓰지 않는다 (DB 전용 — vault 파일 형식 불변).

### 프론트

- `Note` 타입에 `is_favorite: boolean` 추가.
- `notesStore`에 `toggleFavorite(id)` 액션 — 기존 PATCH 후 목록/activeNote 갱신
  패턴(`renameNote`와 동일) 재사용.
- 항해일지(`VoyageLog.tsx`):
  - 목록 최상단에 "⚓ 기항지" 섹션 — 즐겨찾기 노트를 고정 표시. 즐겨찾기가
    없으면 섹션 자체를 렌더링하지 않는다.
  - 각 노트 항목 호버 시 별(☆/★) 토글 버튼 표시.
- 에디터 헤더(제목 영역)에도 별 토글 1개.

### 성도

- 즐겨찾기 노트의 행성에 맥동하는 비콘 링 추가: 행성 반지름의 1.6~2.0배
  사이를 오가는 얇은 `THREE.RingGeometry` + 투명 머티리얼, 매 프레임 스케일과
  opacity를 사인파로 변조. 카메라를 향하도록 빌보드 처리.
- 행성 툴팁에 ⚓ 표시 추가.

## 기능 2 — 블랙홀 (보관)

### 백엔드

- `notes` 테이블에 `is_archived INTEGER NOT NULL DEFAULT 0` 컬럼 추가
  (기항지와 같은 마이그레이션 방식).
- `GET /notes`는 기본으로 보관 노트를 제외한다. `?archived=true`일 때는
  보관 노트만 반환.
- `NotePatch`에 `is_archived: Optional[bool]` 추가 — PATCH로 보관/복원.
- 보관 노트 제외 범위:
  - `/discoveries`, `/discoveries/routes`: 보관 노트가 포함된 발견/쌍 제외.
  - `/search`: 보관 노트 제외.
  - `POST /notes/analyze` (전체 분석): 보관 노트 큐잉 제외.
- .md 파일은 삭제하지 않고 그대로 둔다 (보관은 앱 내 상태일 뿐, vault 불변).

### 프론트

- `notesStore.notes`는 활성 노트만 유지(현행 유지). 보관 목록은 블랙홀 섹션을
  열 때 `notesApi.list({ archived: true })`로 지연 로드.
- 항해일지:
  - 노트 항목 호버 액션에 "블랙홀로 보내기" 추가 (기존 삭제 버튼 옆).
  - 목록 하단에 접이식 "🕳 블랙홀 (N)" 섹션 — 펼치면 보관 노트 목록,
    각 항목에 복원 / 영구 삭제 버튼. 영구 삭제는 confirm 후 기존
    `DELETE /notes/{nid}` 호출(이때만 .md 삭제됨).
- 보관 중인 노트가 `activeNote`면 보관 시 에디터에서 닫는다.

### 성도

- 맵 외곽 고정 위치에 블랙홀 오브젝트 1개: 검은 구(`MeshBasicMaterial`,
  color 0x000000) + 강착원반(기존 `makeRingGeometry`/`makeRingTexture` 재사용,
  주황~보라 틴트) + 매 프레임 원반 회전.
- 보관 노트는 행성으로 그리지 않는다 (`visibleNotes`에서 이미 빠짐 —
  `GET /notes` 기본 응답에 없으므로 성도 코드 변경은 오브젝트 추가만).
- 블랙홀 호버 시 툴팁 "블랙홀 — 보관된 노트 N개". N은 store의
  `archivedCount`에서 읽는다 — 앱 시작 시 1회 로드하고 보관/복원/영구 삭제
  액션마다 갱신. 클릭 동작은 없음(1차 범위).

## 기능 3 — 항로 승격 (관측소 흐름)

### 백엔드

- 새 테이블:
  ```sql
  CREATE TABLE IF NOT EXISTS routes (
    id TEXT PRIMARY KEY,
    note_a TEXT NOT NULL,
    note_b TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(note_a, note_b)
  );
  ```
  저장 시 항상 `note_a < note_b` (기존 discovery_routes와 같은 정렬 규칙).
- `POST /routes {note_a, note_b}` — 승인. 순서 정규화 후 INSERT OR IGNORE.
  존재하지 않는 노트 id면 404.
- `DELETE /routes?note_a=..&note_b=..` — 승인 해제 (순서 정규화 후 삭제).
- `GET /discoveries/routes` 응답 각 항목에 `confirmed: boolean` 추가
  (routes 테이블과 조인). 확정 항로는 발견 쌍에서 사라져도(엔티티 변화)
  응답에 유지한다 — 확정은 사용자의 명시적 선택이므로 AI 재계산에
  좌우되지 않는다. 이 경우 `shared_entities`는 빈 배열일 수 있다.
- 노트 삭제 시 해당 노트가 포함된 routes 행도 삭제.

### 프론트

- `DiscoveryRoute` 타입에 `confirmed: boolean` 추가.
- 미개척 항로 패널(`DiscoveriesPanel.tsx`):
  - 각 발견 항목(activeNote ↔ 대상 노트)에 "⟡ 항로 확정" 버튼.
    확정된 쌍은 버튼 대신 "✦ 확정됨" 배지 + 클릭 시 해제.
  - 확정 여부는 `GET /discoveries/routes`를 패널에서 함께 로드해 판정.
- 성도(`StarMapCanvas.tsx`):
  - 확정 항로: 밝은 금색 계열 실선(높은 opacity) + 우주선.
  - 미개척 항로: 현재보다 opacity를 낮춰 흐리게 — 확정/미개척의 시각적
    위계를 만든다. 우주선은 확정 항로에만 띄운다(성능·시각 소음 절감).
  - 항로/우주선 툴팁에 확정 여부 표시.

## 기능 4 — 초신성 (발견 이벤트)

### 판정 (프론트 전용 — 백엔드 이벤트 테이블 없음)

- `DiscoveriesPanel`의 분석 실행(`runAnalyze` — 전체/단일 공통) 직전에
  `searchApi.discoveryRoutes()` 스냅샷을 찍는다.
- 분석 완료 후 다시 로드해 diff: 노트별 새로 생긴 연결 수를 센다.
- **새 연결이 3개 이상 생긴 노트**를 초신성으로 판정 (여러 개면 모두).
- 일회성 이벤트 — 저장하지 않는다.

### UI

- 토스트 알림: "💥 초신성 발견: {노트 제목} — 새 항로 N개". 여러 노트면
  순차 스택. 클릭하면 성도 탭으로 전환.
- 토스트는 이번에 만드는 경량 공용 컴포넌트(전역 zustand `uiStore` +
  고정 위치 스택)로 구현 — 외부 라이브러리 없음.

### 성도

- 초신성 노트 id 목록을 store에 담아 성도가 읽는다. 성도 진입(또는 이미
  열려 있으면 즉시) 시 해당 행성에서 버스트 연출: 플래시 스프라이트
  (기존 `makeGlowTexture` 재사용) 확대+페이드 + 확장 링 1~2개, 약 2.5초 후
  제거하고 store에서 소비 처리(재생 1회).

## 오류 처리

- 모든 신규 API는 기존 라우터의 인증/오류 패턴을 따른다.
- 성도의 신규 시각 요소는 데이터 로드 실패 시 콘솔 기록 후 생략 —
  기존 항로 로드 실패 처리와 동일하게 씬의 나머지는 정상 렌더링.

## 테스트 / 검증

- 백엔드: `backend/tests`에 기능별 테스트 추가 —
  favorite/archive 마이그레이션·PATCH·목록 필터, 보관 노트의
  discoveries/routes/search/analyze 제외, routes CRUD와 confirmed 플래그,
  확정 항로의 발견-소멸 후 유지.
- 프론트: 타입체크 + 빌드 통과.
- 웹 UI: 실제 브라우저로 4개 기능 흐름 QA (기항지 토글→섹션 표시→성도 비콘,
  보관→목록 제외→블랙홀 오브젝트, 항로 확정→성도 스타일 변화,
  분석 후 초신성 토스트→성도 버스트).

## 범위 제외 (이번에 하지 않음)

- 항도(경로 탐색), 성문(멀티 스페이스), 중력권(레이아웃 변경).
- 즐겨찾기/보관 상태의 frontmatter 기록.
- 블랙홀 오브젝트 클릭으로 보관함 열기.
- 초신성 이벤트 이력 저장.
