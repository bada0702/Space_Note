# 미개척 항로 AI 분석 버튼 + 성도 비주얼 개선

날짜: 2026-07-03
상태: 승인됨 (사용자 확인)

## 배경

- 노트 저장 시 엔티티 추출이 백그라운드로 실행되지만, 실패(`analysis_status='failed'`)하면
  다시 시도할 방법이 UI에 없다. entities 테이블이 비어 있어 미개척 항로가 항상 빈 상태.
- 성도(StarMap)의 행성/은하 표현이 평면적이어서 "가짜같다"는 피드백.
- 은하(카테고리 항성계)끼리 겹쳐 보임: 궤도 반경은 노트 수에 비례해 커지는데
  (`radius = sunR + 16 + j*12`) 항성 위치는 150~200 거리로 고정되어 있어
  노트가 많으면 궤도가 이웃 은하를 침범한다.

## 기능 1 — 미개척 항로 "항로 분석" 버튼

### 백엔드 (`backend/routers/notes.py`)

- `POST /notes/analyze` (일괄)
  - content가 비어있지 않고 `analysis_status IN ('pending','failed')`인 노트 전체를
    BackgroundTasks로 `_run_extraction` 실행.
  - 실행 전 API 키 확인(설정 DB 우선, 없으면 env). 키가 없으면
    `400 {"detail": "Anthropic API 키가 설정되지 않았습니다"}`.
  - 큐잉된 노트들의 status를 즉시 `pending`으로 갱신(폴링 판별용).
  - 응답: `{"queued": N}`.
- `POST /notes/{id}/analyze` (단일)
  - 해당 노트만 재분석. 같은 키 검증. 404/400 처리. 응답 `{"queued": 1}`.
- 버그 수정: `extract_entities`는 키가 없으면 빈 배열을 반환하고 `_run_extraction`이
  이를 `analyzed`로 기록한다. 키 부재 시 예외를 던져 `failed`가 되도록 수정.

### 프론트엔드 (`DiscoveriesPanel.tsx`, `searchApi`/`notesApi`)

- 버튼 줄에 "⟡ 전체 항로 분석" 추가. 클릭 → `POST /notes/analyze` →
  "N개 노트 분석 중..." 표시 → 3초 간격 폴링(최대 60초)으로 notes의
  `analysis_status`가 모두 pending을 벗어나면 discoveries 재로드.
- activeNote가 있으면 "이 노트 분석" 버튼 표시 → 단일 API.
- 400 응답이면 패널에 "설정에서 Anthropic API 키를 먼저 저장하세요" 안내 표시.

## 기능 2 — 성도 비주얼 개선 (`StarMapCanvas.tsx`)

순수 three.js 구조 유지. 외부 의존성 추가 없이 three/examples/jsm 모듈만 사용.

1. **블룸 포스트프로세싱**: `EffectComposer` + `RenderPass` + `UnrealBloomPass`,
   ACESFilmicToneMapping. 블룸 해상도는 절반으로 성능 유지.
2. **항성 표면 셰이더**: 애니메이션 노이즈(이글거리는 대류) + 색온도 그라데이션의
   커스텀 ShaderMaterial. 기존 MeshBasicMaterial 대체.
3. **행성 대기**: 스프라이트 글로우 대신 프레넬 기반 대기 셸(BackSide 셰이더)로
   가장자리 산란. 표면 텍스처 해상도 512→1024.
4. **배경 심화**: 원형 소프트 파티클 텍스처 별(현재 사각 점), 다층 별밭,
   은하수 밴드, 성운 레이어 추가.
5. **궤도선/은하**: 궤도선 페이드, 항성 주위 나선형 성간먼지 파티클.
6. **은하 간 간격 보장 (필수)**: 항성 위치를 고정 좌표가 아니라 동적으로 계산.
   각 은하계의 최대 궤도 반경 `R_i = sunR + 16 + (n_i-1)*12`를 구하고,
   모든 쌍에 대해 `dist(i,j) >= R_i + R_j + margin(>=80)`이 되도록
   기존 STAR_POSITIONS 방향 벡터에 스케일을 적용해 배치한다.

## 성능/제약

- pixelRatio 상한 2 유지, 블룸 저해상도 렌더.
- 폴링은 패널이 열려 있는 동안만, 언마운트 시 중단.
- 기존 클릭/툴팁/카메라 조작 동작은 그대로 유지.

## 테스트

- 백엔드: pytest — analyze 일괄/단일 엔드포인트(키 없음 400, 큐잉 개수,
  status 전이), 키 부재 시 failed 처리.
- 프론트: 수동 QA — 분석 버튼 → 폴링 → 항로 표시, 성도 렌더링/상호작용 확인.
