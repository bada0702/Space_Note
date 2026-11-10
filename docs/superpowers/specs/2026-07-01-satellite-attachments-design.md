# 위성(Satellite/첨부) 기능 — 설계 문서

> 작성일: 2026-07-01
> 상태: 승인 대기 (브레인스토밍 완료, 스펙 검토 요청 단계)

## 배경

SpaceNote는 우주 은유로 지식을 구조화한다. 현재 계층은 다음과 같다.

- 🌌 **Space** = 전체 지식 공간
- ✨ **성운(Nebula)** = 카테고리 (`categories` 테이블 / StarMap의 항성)
- 🪐 **행성(Planet)** = 노트 (`notes` 테이블 / 항성 주위를 공전하는 행성)
- ✦ **엔티티(Entity)** = 노트에서 추출된 개념 (`entities` 테이블 / 성좌 연결)

여기에 한 계층을 더한다.

- 🌙 **위성(Satellite/Moon)** = 행성(노트)에 종속되는 **첨부 자료**

천문학적으로 위성이 행성을 공전하듯, 위성은 노트를 보완하는 부속 자료(PDF·이미지·코드·
메모·URL)로서 노트에 종속되어 붙는다. 하나의 행성(노트)에 여러 위성이 붙는 1:N 구조다.

## 결정 사항 (브레인스토밍 확정)

| 항목 | 결정 |
|------|------|
| 위성의 정의 | **첨부 자료** (하위 세부 노트 아님) |
| 저장 범위 | **파일 업로드 포함(풀)** — PDF/이미지/코드 파일 업로드 + 링크 + 메모 |
| v1 범위 | **StarMap 3D 시각화 포함** (데이터/편집기 UI + 위성 궤도 렌더링) |
| AI 인덱싱 | **텍스트 위성 인덱싱 포함** — 메모/링크 설명/코드·텍스트 파일 추출본을 엔티티 추출·RAG·검색에 합류 |
| 스키마 종류 | **3종(`file`/`link`/`memo`)** — PDF·이미지·코드는 모두 `file`, mime으로 구분 |
| 테이블/필드명 | 기존 코드 관례에 맞춘 **영문 스네이크케이스** (`attachments`) |

## 비범위 (YAGNI)

- **PDF/이미지 텍스트 추출.** PDF 파서(별도 의존성)는 v1 제외. PDF·이미지는 저장·표시·
  다운로드만 하고 AI 인덱싱 대상이 아니다. (텍스트 파일·코드·메모·링크만 인덱싱.)
- **위성을 자체 콘텐츠를 가진 하위 노트로 취급하는 방향.** 위성은 노트가 아니라 첨부물이다.
- **위성에서 다시 위성이 붙는 다단계 중첩.** 위성은 노트에만 붙는다(1단계).
- **위성 자체의 독립 엔티티 추출.** 위성 텍스트는 소속 노트의 추출에 합류할 뿐, 위성이
  독립된 `entities` 행을 갖지 않는다.
- **이미지 썸네일/미리보기 렌더링.** v1은 파일명·타입 아이콘·다운로드 링크만.

## 1. 데이터 모델 — `attachments` 테이블

`backend/db.py`의 `SCHEMA`에 아래 테이블을 추가한다. 기존 `categories`/`notes`/
`entities`와 동일한 스타일(TEXT PK, ISO 문자열 타임스탬프)을 따른다.

```sql
CREATE TABLE IF NOT EXISTS attachments (
  id TEXT PRIMARY KEY,
  note_id TEXT NOT NULL,                   -- 소속 행성(노트)
  type TEXT NOT NULL,                      -- 'file' | 'link' | 'memo'
  name TEXT NOT NULL,                      -- 표시 이름 (파일명 / 링크 제목 / 메모 제목)
  file_path TEXT,                          -- type=file: vault 하위 상대경로, 그 외 NULL
  mime TEXT,                               -- type=file: MIME 타입, 그 외 NULL
  size INTEGER NOT NULL DEFAULT 0,         -- type=file: 바이트 수, 그 외 0
  url TEXT,                                -- type=link: 원본 URL, 그 외 NULL
  text_content TEXT NOT NULL DEFAULT '',   -- 인덱싱 대상 텍스트
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
```

**`type`별 필드 사용:**

| type | file_path | mime | size | url | text_content |
|------|-----------|------|------|-----|--------------|
| `file` (PDF/이미지) | ✅ | ✅ | ✅ | — | `''` (인덱싱 안 함) |
| `file` (코드/텍스트) | ✅ | ✅ | ✅ | — | 파일 내용(인덱싱) |
| `link` | — | — | 0 | ✅ | 링크 제목+설명(인덱싱) |
| `memo` | — | — | 0 | — | 메모 본문(인덱싱) |

**UI 아이콘은 5종**(🌙PDF/🖼️이미지/💻코드/📝메모/🔗URL)으로 노출하되, `file` 타입은
`mime`으로 PDF/이미지/코드를 판별한다. 스키마는 3종으로 단순하게 유지한다.

**정합성:**
- 노트 삭제 시 소속 위성 행 + 파일을 함께 삭제한다(앱 레벨 cascade, 기존 `notes` 삭제 시
  `entities`를 지우는 패턴과 동일).
- `text_content`가 비어 있지 않은 위성(= 인덱싱 대상)이 추가/삭제되면 소속 노트의
  `analysis_status`를 `'pending'`으로 되돌려 재추출을 트리거한다.

## 2. 파일 저장 — `backend/services/attachments.py`

`services/vault.py`와 대칭되는 신규 서비스. 파일 저장/삭제/경로 안전화를 담당한다.

- **저장 경로:** `VAULT_DIR/attachments/<note_id>/<uuid>.<ext>`
  - `VAULT_DIR`(config)를 재사용한다. `attachments/` 하위 디렉터리는 없으면 생성.
  - DB의 `file_path`에는 `VAULT_DIR` 기준 **상대경로**를 저장한다.
- **경로 이탈 방지:** `vault.py::write_md`가 쓰는 것과 동일하게, resolve한 경로가
  `VAULT_DIR` 내부인지 검증하고 아니면 `ValueError`.
- **확장자:** 업로드 원본 파일명에서 확장자만 취해 안전화. 실제 파일명은 `uuid`로 저장해
  충돌·경로 주입을 차단하고, 표시용 원본 이름은 DB `name`에 보관한다.
- **텍스트 추출:** 업로드 파일의 `mime`이 텍스트 계열(`text/*`, 코드 확장자,
  `application/json` 등)이면 내용을 읽어 `text_content`로 반환. PDF/이미지 등 바이너리는
  빈 문자열.
- **삭제:** 위성 삭제 시 `file_path`의 실제 파일을 제거(존재할 때만).

## 3. 백엔드 API — `backend/routers/attachments.py`

신규 라우터. `main.py`에 등록한다. 응답 모델은 `AttachmentOut`.

```
GET    /notes/{note_id}/attachments          # 노트의 위성 목록 (sort_order, created_at 순)
POST   /notes/{note_id}/attachments/file     # 파일 업로드 (multipart/form-data: file)
POST   /notes/{note_id}/attachments/link     # 링크 추가 (JSON: url, name, description?)
POST   /notes/{note_id}/attachments/memo     # 메모 추가 (JSON: name, text)
GET    /attachments/{id}/download            # 파일 다운로드 (FileResponse)
DELETE /attachments/{id}                      # 삭제 (파일 제거 포함, 204)
GET    /attachments                           # 전체 위성 벌크 조회 (StarMap용, note_id별)
```

- `POST .../file`: `note_id` 유효성 검사 → 파일 저장 → 텍스트 추출 → 행 삽입 → 소속 노트
  `analysis_status='pending'`으로 갱신 + 백그라운드 재추출 트리거.
- `POST .../link`, `POST .../memo`: 파일 없이 `text_content`만 구성해 동일 흐름.
- `GET /attachments/{id}/download`: `file_path`를 resolve해 `VAULT_DIR` 내부 검증 후
  `FileResponse`. 파일 없으면 404.
- `models.py` 추가: `LinkCreate {url, name, description?}`, `MemoCreate {name, text}`,
  `AttachmentOut` (테이블 필드 매핑).

## 4. AI 인덱싱 연동 (텍스트 위성)

인덱싱 가능한 위성(`text_content != ''`)의 텍스트를 소속 노트의 AI 처리 3지점에 합류시킨다.

1. **엔티티 추출** — `routers/notes.py::_run_extraction`
   추출 대상을 `노트 content + 인덱싱 가능한 위성들의 text_content 결합`으로 확장한다.
   위성 텍스트를 명확히 구분하는 헤더(`\n\n[위성: {name}]\n{text_content}`)를 붙여 합친다.
   위성 추가/삭제도 이 재추출을 트리거한다(§1 정합성 참고).

2. **RAG** — `routers/ai.py`의 컨텍스트 구성
   `context_note_id` 및 `use_rag` 컨텍스트를 만들 때, 각 노트 content 뒤에 해당 노트의
   인덱싱 가능한 위성 텍스트를 append한다.

3. **검색** — `routers/search.py::search`
   `notes`의 `title/content` LIKE에 더해, `attachments.text_content`도 LIKE로 검색해
   매칭되는 위성의 `note_id`로 노트를 결과에 포함한다(중복 제거). `content_preview`는
   기존대로 노트 본문 기준.

## 5. 프론트엔드 — 편집기 위성 패널

- **타입** (`src/types/index.ts`): `Attachment` 인터페이스 추가
  (`id, note_id, type, name, file_path, mime, size, url, text_content, sort_order, created_at`).
- **API** (`src/api/attachmentsApi.ts`): 목록/파일업로드/링크/메모/다운로드/삭제 래퍼.
  기존 `client.ts`의 인증 토큰 처리를 재사용한다.
- **스토어** (`src/store/attachmentsStore.ts`): 현재 노트의 위성 목록 상태 + CRUD 액션.
- **컴포넌트** (`src/components/Editor/`): **위성 패널** 신설.
  - 현재 노트의 위성 목록을 타입별 아이콘(🌙PDF/🖼️이미지/💻코드/📝메모/🔗URL)으로 표시.
  - 추가 UI: 파일 선택/드롭, 링크 입력(URL+제목+설명), 메모 입력(제목+본문).
  - 각 항목: 다운로드(파일)/열기(링크)/삭제.
  - 노트 전환 시 해당 노트의 위성을 로드.

## 6. StarMap 3D 시각화

`src/components/StarMap/StarMapCanvas.tsx`를 확장한다.

- **데이터 로드:** StarMap 진입 시 `GET /attachments`(벌크)로 전체 위성을 note_id별로
  그룹화해 확보한다.
- **메시 생성:** `catNotes.forEach((note, j) => ...)`(현재 ~514행)에서 행성 메시 생성 직후,
  해당 노트의 위성마다 작은 구체를 만들어 **행성 메시의 자식**으로 추가한다.
  - 위성은 행성 반경의 소궤도로 공전(행성 자전과 별개 속도).
  - **최대 8개까지만 렌더**하여 시각적 과밀을 방지한다. 8개 초과 시 8번째 위성 옆에
    "+N" 스프라이트 라벨로 나머지 개수를 표시한다(무음 절단 금지).
  - 타입별로 재질 색을 달리한다(예: `memo`=옅은 청록, `file`=회색, `link`=옅은 자주).
- **렌더 루프:** 기존 `orbits`/`spinners` 애니메이션 루프에 위성 공전 갱신을 추가.
  위성은 부모 행성의 자식이므로 행성 공전을 자동으로 따라간다.
- **툴팁:** 기존 planet 호버 툴팁 로직을 확장해, 위성 호버 시 위성 이름을 표시한다.

## 7. 테스트

- **백엔드 (pytest, `backend/tests`):**
  - attachments CRUD (파일/링크/메모 각각 생성·목록·삭제).
  - 파일 경로 안전화: `VAULT_DIR` 밖으로 이탈하는 경로 차단.
  - 텍스트 위성 추가/삭제 시 소속 노트 `analysis_status='pending'` 전이.
  - 노트 삭제 시 위성 행 + 파일 정리.
  - 검색이 위성 `text_content` 매칭 노트를 포함.
- **프론트엔드:** 기존 프론트 테스트 유무 확인 후, 있으면 위성 패널 상호작용 스모크
  테스트를 동일 패턴으로 추가. 없으면 수동 확인 절차를 계획에 명시.

## 컴포넌트 요약 (단위별 책임)

| 단위 | 책임 | 의존 |
|------|------|------|
| `attachments` 테이블 | 위성 데이터 영속화 | `db.py` SCHEMA |
| `services/attachments.py` | 파일 저장/삭제/경로안전/텍스트추출 | `config.VAULT_DIR` |
| `routers/attachments.py` | 위성 CRUD·업로드·다운로드 API | 위 서비스, `db`, `models` |
| 인덱싱 훅 | 위성 텍스트를 노트 AI 처리에 합류 | `notes.py`, `ai.py`, `search.py` |
| `attachmentsApi` + `attachmentsStore` | 프론트 위성 상태·통신 | `client.ts` |
| 위성 패널 컴포넌트 | 위성 조회·추가·삭제 UI | store, api |
| StarMap 위성 렌더 | 행성 자식 위성 궤도 3D 표현 | 벌크 위성 데이터, three.js |
