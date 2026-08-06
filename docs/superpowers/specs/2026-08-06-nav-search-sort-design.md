# 항법(검색 패널) 정렬 기능

날짜: 2026-08-06
상태: 승인됨 (사용자 확인)

## 배경

- 사이드바 `⊕ 항법` 패널(`SearchPanel.tsx`)은 검색 결과를 백엔드에서
  `modified_at DESC` 고정 정렬로만 받는다. 정렬 기준을 바꿀 방법이 없다.
- 검색 API(`GET /search`, `backend/routers/search.py`)가 결과마다
  `modified_at`, `title`을 이미 포함해 반환하고, 결과는 최대 50건으로
  제한되어 있어 백엔드 변경 없이 클라이언트 정렬로 충분하다.
- 범위는 항법(검색 결과)에 한정한다. 사이드바 상단 카테고리별 노트 목록
  (VoyageLog)은 이번 변경에 포함하지 않는다.

## 기능 — 프론트: 결과 정렬 상태 & UI

### 상태 (`src/store/searchStore.ts`)

- `sortBy: 'modified' | 'title'` — 기본 `'modified'`
- `sortDir: 'asc' | 'desc'` — 기본 `'desc'`
- `setSort(by: 'modified' | 'title')`:
  - 이미 선택된 기준을 다시 호출하면 `sortDir`만 토글
  - 다른 기준으로 바뀌면 그 기준의 기본 방향으로 설정
    (`modified` → `desc` = 최신순, `title` → `asc` = 가나다/A-Z순)
  - 매 호출 시 현재 `results`를 즉시 재정렬해 저장 (컴포넌트는 정렬된
    `results`를 그대로 렌더링, 별도 selector 불필요)
- `doSearch` 완료 후에도 현재 `sortBy`/`sortDir` 기준으로 정렬해서 저장

### 정렬 로직

```ts
function sortResults(results: SearchResult[], sortBy: 'modified' | 'title', sortDir: 'asc' | 'desc') {
  const sorted = [...results].sort((a, b) =>
    sortBy === 'title'
      ? a.title.localeCompare(b.title, 'ko')
      : a.modified_at.localeCompare(b.modified_at)
  )
  return sortDir === 'asc' ? sorted : sorted.reverse()
}
```

- 제목 비교는 `localeCompare(..., 'ko')`로 한글/영문이 섞여도 자연스러운
  순서가 나온다 (가나다순·ABC순을 별도 옵션으로 분리하지 않음).
- `modified_at`은 ISO 형식 문자열이라 문자열 비교로 시간순 정렬이 그대로
  맞는다.

### UI (`src/components/Navigation/SearchPanel.tsx`)

- 검색 입력창 아래에 "날짜순 / 제목순" 세그먼트 버튼 2개를 추가.
- 활성 버튼에 방향 화살표(▲ asc / ▼ desc)를 표시. 클릭 시:
  - 비활성 버튼 클릭 → 해당 기준으로 전환(기본 방향 적용)
  - 활성 버튼 재클릭 → 방향 토글
- 기존 결과 렌더링(`results.map(...)`) 로직은 변경 없음.

## 에러 처리 / 테스트

- 순수 클라이언트 배열 연산이라 별도 에러 케이스 없음(빈 배열 정렬은
  안전하게 빈 배열 반환).
- 기존 "검색 결과 없음" / "키워드를 입력하고..." 안내 문구 로직과는
  무관하게 동작.
- 수동 검증: 검색 후 두 버튼을 각각 클릭해 정렬 순서와 방향 토글이
  화면에 반영되는지 확인.
