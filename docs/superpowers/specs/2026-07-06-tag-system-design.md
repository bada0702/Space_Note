# 태그 시스템

날짜: 2026-07-06
상태: 승인됨 (사용자 확인)

## 배경

- Space Note는 지금 노트당 카테고리(은하) 하나만 지정 가능한 단일 분류 체계와,
  AI가 본문에서 추출한 엔티티(`entities` 테이블)를 기준으로 한 자동 연결
  (미개척 항로 / 성도 항로)만 갖고 있다.
- 옵시디언과 비교했을 때 사용자가 직접, 다대다로 붙일 수 있는 수동 태그가
  없다는 게 대표적인 공백으로 꼽혔다.
- 목표: 본문에 `#태그`를 인라인으로 적으면 자동 인식되고, 같은 태그를 공유하는
  노트끼리도 기존 성도 항로 시스템에 그대로 편입되며, 태그 전용 탐색 패널과
  성도 필터를 제공한다.

## 기능 1 — 백엔드: 태그 파싱 & 저장

### 스키마

`entities`와 동일한 패턴으로 `tags` 테이블 추가:

```sql
CREATE TABLE tags (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL REFERENCES notes(id),
  tag TEXT NOT NULL,       -- 원문 표기 (예: "AIX")
  norm TEXT NOT NULL,      -- 정규화 키 (소문자, 공백 제거) — entities.norm과 동일 규칙
  created_at TEXT NOT NULL
);
```

### 파싱 규칙

- 정규식: `(?<!\S)#([A-Za-z0-9가-힣_-]+)` — `#` 직전이 공백/줄시작이어야 하고,
  `#` 바로 뒤에 공백 없이 문자가 와야 태그로 인정한다.
- 이 규칙으로 마크다운 헤딩(`# 제목`, `## 소제목`)과 자연스럽게 구분된다
  (헤딩은 `#` 뒤에 공백이 오므로 정규식에 안 걸림).
- 같은 노트 안에서 같은 태그가 여러 번 나와도 1개로 합친다(중복 제거는
  `norm` 기준).

### 저장 시점

- 노트 생성(`POST /notes`)과 본문 변경 패치(`PATCH /notes/{id}` — content가
  바뀔 때)에서, 기존 엔티티 백그라운드 분석과는 별개로 **동기적으로** 처리한다
  (AI 호출이 없는 순수 정규식 파싱이라 응답을 기다릴 필요가 없음).
- 처리: 해당 노트의 기존 `tags` 행을 삭제하고 새로 파싱한 태그를 재삽입
  (`_run_extraction`의 엔티티 갱신 방식과 동일한 delete-then-insert).

## 기능 2 — 백엔드: 기존 자동연결 시스템과 통합

### `GET /discoveries/routes` 수정 (`backend/routers/search.py`)

- 지금은 `entities` 테이블만 `norm` 기준으로 묶어 `norm_notes: dict[norm, set[note_id]]`를
  만드는데, 여기에 `tags` 테이블의 `(note_id, norm, tag)`도 같은 구조로 합쳐
  넣는다. 엔티티와 태그가 같은 텍스트로 우연히 겹치는 경우까지 고려해
  `norm` 앞에 짧은 접두사(`e:`/`t:`)를 붙여 네임스페이스를 분리한다
  (`entities`의 "AIX"와 태그 `#AIX`가 같은 항로로 뭉개지지 않게).
- 그 외 union-capping(노트당 상위 20개, 두 노트 중 하나라도 상위 20위 안이면
  유지) 로직은 그대로 재사용한다.

### `GET /discoveries` 수정

- `note_id`가 주어졌을 때 엔티티뿐 아니라 태그로 공유되는 노트도 함께 반환하도록
  같은 방식으로 UNION.

### 신규 엔드포인트

- `GET /tags` — 전체 태그를 노트 수 내림차순으로: `[{"tag": "AIX", "count": 4}, ...]`.
- `GET /tags/{tag}/notes` — 해당 태그가 붙은 노트 목록(제목/카테고리 포함,
  `discoveries()`의 note-list 응답과 같은 필드 구성).

## 기능 3 — 프론트: 태그 패널 & 사이드바 진입점

- 사이드바 하단 메뉴(`Sidebar.tsx`)에 `⟡ 미개척 항로` / `⊕ 항법` 옆에
  `# 태그` 항목 추가. 클릭 시 새 `TagsPanel.tsx`를 연다(기존
  `activePanel`/`setPanel` 메커니즘 재사용, `discoveries` | `search` | `tags`
  세 값 중 하나로 확장).
- `TagsPanel.tsx`: `GET /tags` 결과를 노트 수 순으로 나열(`DiscoveriesPanel`과
  같은 리스트 UI 톤 재사용). 태그 클릭 시 `GET /tags/{tag}/notes`로 드릴다운해
  노트 목록을 보여준다.
- `tagsApi.ts` 신규: `list()`, `notesForTag(tag)`.
- `types/index.ts`에 `TagSummary { tag: string; count: number }` 추가.

## 기능 4 — 프론트: 성도 필터 확장

- `notesStore`의 `starMapFilter: string | null`(카테고리 ID 전용)을
  `StarMapFilter = { type: 'category' | 'tag'; value: string } | null`로 확장.
- `setStarMapFilter`의 시그니처를 그에 맞게 바꾸고, 기존 카테고리 필터 호출부
  (`CategoryItem.tsx`의 "✦ 이 은하 성도에서 보기" 등)는 `{type:'category', value: category.id}`로
  감싸도록 수정.
- `StarMapCanvas.tsx`의 현재 `note.category_id === starMapFilter` 비교 지점을
  `starMapFilter.type`에 따라 분기(`category`면 지금처럼, `tag`면 해당 노트가
  그 태그를 갖는지로 판정 — 태그 목록은 씬 구성 시 `GET /tags/{tag}/notes`
  또는 이미 로드된 노트별 태그 맵으로 확인).
- `TagsPanel.tsx`에서 태그 클릭 시 `setStarMapFilter({type:'tag', value: tag})`
  + `setTab('starmap')` 호출(카테고리 쪽과 동일 패턴).
- 기존 `setStarMapFilter` 호출부 전부(`CategoryItem.tsx`의 "이 은하 성도에서
  보기", `EditorTabs.tsx`의 성도 탭 클릭, `Sidebar.tsx`의 `handleStarMap`)를
  새 타입에 맞게 `{type:'category', value:...}` 형태로 마이그레이션 — 하나라도
  빠뜨리면 해당 진입점에서 타입 에러 또는 필터 오동작이 난다.

## 성능/에러 처리

- 태그 파싱은 정규식 기반이라 실패 케이스가 사실상 없음(빈 배열이면 태그 없음
  으로 저장).
- `/discoveries/routes`, `/discoveries` 응답 형식은 기존과 동일하게 유지되므로
  이미 이 데이터를 쓰는 프론트 코드(StarMapCanvas 항로 렌더링)는 수정 없이도
  태그 기반 항로를 자동으로 함께 그린다.

## 테스트

- 백엔드: 태그 파싱 정규식 단위 테스트(헤딩과 구분, 중복 제거, 한글 태그,
  공백 태그 미인식) + `POST /notes`/`PATCH /notes/{id}` 시 `tags` 테이블 갱신
  확인 + `/discoveries/routes`에 태그로만 공유되는 노트 쌍이 섞여 나오는지
  + `/tags`, `/tags/{tag}/notes` 응답 검증.
- 프론트: 새 컴포넌트(`TagsPanel`)는 기존 `DiscoveriesPanel` 패턴을 그대로
  재사용하므로 별도 단위 테스트보다 타입체크 + 브라우저 수동 QA로 확인한다
  (태그 작성 → 사이드바 태그 패널에 반영 → 성도에서 항로/필터 확인).
