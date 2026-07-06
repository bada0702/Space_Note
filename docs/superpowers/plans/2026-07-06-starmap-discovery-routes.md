# 성도 항로 시각화 (Discovery Routes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미개척 항로(Discoveries)에서 발견된 노트-노트 연결을 성도(StarMap)에서 행성과 행성을 잇는 항로선 + 왕복하는 우주선으로 시각화한다.

**Architecture:** 백엔드에 노트 쌍 연결을 계산하는 새 엔드포인트(`GET /discoveries/routes`)를 추가하고, 프론트는 StarMap 마운트 시 1회 조회해 각 연결마다 곡선(Line)과 그 위를 왕복하는 작은 우주선(Mesh)을 만들어, 두 행성이 궤도를 도는 매 프레임마다 곡선/우주선 위치를 재계산한다. 호버 시 공유 엔티티를 툴팁으로 보여준다.

**Tech Stack:** FastAPI + sqlite3(backend), React + Three.js(frontend). 새 외부 의존성 없음.

## Global Constraints

- 노트 쌍 연결 상한: 노트 하나당 최대 20개(공유 엔티티 개수 많은 순), 두 노트 중 어느 한쪽 상위 20위 안에 들면 포함(합집합).
- 쌍 순서는 항상 `note_a < note_b`(문자열 비교)로 정렬, 중복 없음.
- `/discoveries/routes` 실패 시 성도의 나머지 렌더링(행성/궤도)은 정상 동작해야 한다 — 항로만 생략.
- 카테고리 필터로 숨겨진 노트가 걸린 항로는 건너뛴다.
- 기존 클릭/툴팁/카메라 조작, 씬 정리(scene.traverse dispose) 동작은 그대로 유지한다.

---

### Task 1: 백엔드 — `GET /discoveries/routes` 엔드포인트

**Files:**
- Modify: `backend/routers/search.py`
- Test: `backend/tests/test_search.py`

**Interfaces:**
- Produces: `GET /discoveries/routes` → `list[{"note_a": str, "note_b": str, "shared_entities": list[str]}]`, 정렬됨(`note_a` 오름차순, 동률이면 `note_b` 오름차순), 인증 필요(`require_auth` — `main.py`에서 이미 `search.router`에 걸려 있음).

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_search.py` 끝에 추가:

```python
def test_routes_requires_auth(client):
    assert client.get("/discoveries/routes").status_code == 401


def test_routes_returns_pair_for_shared_entity(client):
    from db import get_conn
    import uuid

    n1 = _make_note(client, "노트1")
    n2 = _make_note(client, "노트2")
    n3 = _make_note(client, "노트3")  # 엔티티 없음 — 연결 안 됨

    with get_conn() as conn:
        for note_id, name in [(n1["id"], "Ollama"), (n2["id"], "ollama")]:
            conn.execute(
                "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                "VALUES (?, ?, ?, 'concept', ?, 'now')",
                (str(uuid.uuid4()), note_id, name, "ollama"),
            )

    r = client.get("/discoveries/routes", headers=AUTH)
    assert r.status_code == 200
    routes = r.json()
    assert len(routes) == 1
    a, b = sorted([n1["id"], n2["id"]])
    assert routes[0]["note_a"] == a
    assert routes[0]["note_b"] == b
    assert routes[0]["shared_entities"] == ["Ollama"]
    assert not any(n3["id"] in (r["note_a"], r["note_b"]) for r in routes)


def test_routes_merges_multiple_shared_entities_into_one_pair(client):
    from db import get_conn
    import uuid

    n1 = _make_note(client, "노트1")
    n2 = _make_note(client, "노트2")
    with get_conn() as conn:
        for name, norm in [("Ollama", "ollama"), ("Docker", "docker")]:
            for note_id in (n1["id"], n2["id"]):
                conn.execute(
                    "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                    "VALUES (?, ?, ?, 'concept', ?, 'now')",
                    (str(uuid.uuid4()), note_id, name, norm),
                )

    r = client.get("/discoveries/routes", headers=AUTH)
    routes = r.json()
    assert len(routes) == 1
    assert sorted(routes[0]["shared_entities"]) == ["Docker", "Ollama"]


def test_routes_caps_at_20_connections_per_note(client):
    from db import get_conn
    import uuid

    x = _make_note(client, "중심노트")
    weakest_note_id = None
    with get_conn() as conn:
        for i in range(21):
            nid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO notes (id, path, title, content, tags, word_count, "
                "analysis_status, created_at, modified_at) "
                "VALUES (?, ?, ?, '', '[]', 0, 'analyzed', 'now', 'now')",
                (nid, f"/tmp/{nid}.md", f"n{i}"),
            )
            if i == 0:
                weakest_note_id = nid
            # n_i는 x와 (i+1)개의 엔티티를 공유 — i=0이 가장 약한(1개) 연결
            for k in range(i + 1):
                norm = f"ent{k}"
                conn.execute(
                    "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                    "VALUES (?, ?, ?, 'concept', ?, 'now')",
                    (str(uuid.uuid4()), x["id"], norm, norm),
                )
                conn.execute(
                    "INSERT INTO entities (id, note_id, name, type, norm, created_at) "
                    "VALUES (?, ?, ?, 'concept', ?, 'now')",
                    (str(uuid.uuid4()), nid, norm, norm),
                )

    r = client.get("/discoveries/routes", headers=AUTH)
    routes = r.json()
    pairs_with_x = [row for row in routes if x["id"] in (row["note_a"], row["note_b"])]
    assert len(pairs_with_x) == 20
    assert not any(
        weakest_note_id in (row["note_a"], row["note_b"]) for row in pairs_with_x
    )
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_search.py -v -k routes`
Expected: FAIL — `404 Not Found` (엔드포인트 없음)

- [ ] **Step 3: 엔드포인트 구현**

`backend/routers/search.py` 맨 위 import에 `combinations`, `defaultdict` 추가:

```python
from itertools import combinations
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter

from db import get_conn
```

파일 끝(`entities()` 함수 뒤)에 추가:

```python
_MAX_ROUTES_PER_NOTE = 20


@router.get("/discoveries/routes")
def discovery_routes():
    """엔티티를 공유하는 노트 쌍을 항로(route)로 반환 — 성도의 연결선 렌더링용."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT note_id, norm, name FROM entities WHERE norm IS NOT NULL AND norm != ''"
        ).fetchall()

    norm_notes: dict[str, set[str]] = defaultdict(set)
    norm_display: dict[str, str] = {}
    for r in rows:
        norm_notes[r["norm"]].add(r["note_id"])
        norm_display.setdefault(r["norm"], r["name"])

    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for norm, note_ids in norm_notes.items():
        if len(note_ids) < 2:
            continue
        display = norm_display[norm]
        for a, b in combinations(sorted(note_ids), 2):
            pairs[(a, b)].add(display)

    by_note: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in pairs:
        by_note[key[0]].append(key)
        by_note[key[1]].append(key)

    keep: set[tuple[str, str]] = set()
    for note_id, keys in by_note.items():
        keys.sort(key=lambda k: len(pairs[k]), reverse=True)
        keep.update(keys[:_MAX_ROUTES_PER_NOTE])

    return [
        {"note_a": a, "note_b": b, "shared_entities": sorted(pairs[(a, b)])}
        for a, b in sorted(keep)
    ]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_search.py -v`
Expected: PASS (전체)

Run: `cd backend && source venv/bin/activate && python -m pytest tests/ -q`
Expected: 전체 PASS (기존 54개 + 이번에 추가한 5개 = 59개)

- [ ] **Step 5: 커밋**

```bash
git add backend/routers/search.py backend/tests/test_search.py
git commit -m "feat(backend): add GET /discoveries/routes for note-pair connections"
```

---

### Task 2: 프론트 — 타입 + API 클라이언트

**Files:**
- Modify: `src/types/index.ts`
- Modify: `src/api/searchApi.ts`

**Interfaces:**
- Consumes: Task 1의 `GET /discoveries/routes` 응답 형식.
- Produces: `DiscoveryRoute` 타입, `searchApi.discoveryRoutes(): Promise<DiscoveryRoute[]>` — Task 3에서 사용.

- [ ] **Step 1: 타입 추가**

`src/types/index.ts`의 `Discovery` 인터페이스 뒤(현재 63-70번째 줄)에 추가:

```typescript
export interface DiscoveryRoute {
  note_a: string
  note_b: string
  shared_entities: string[]
}
```

- [ ] **Step 2: API 함수 추가**

`src/api/searchApi.ts`를 다음과 같이 수정:

```typescript
import { apiFetch } from './client'
import type { SearchResult, Discovery, DiscoveryRoute, Entity } from '../types'

export const searchApi = {
  search: (q: string): Promise<SearchResult[]> =>
    apiFetch<SearchResult[]>(`/search?q=${encodeURIComponent(q)}`),

  discoveries: (noteId?: string): Promise<Discovery[]> =>
    apiFetch<Discovery[]>(`/discoveries${noteId ? `?note_id=${noteId}` : ''}`),

  discoveryRoutes: (): Promise<DiscoveryRoute[]> =>
    apiFetch<DiscoveryRoute[]>('/discoveries/routes'),

  entities: (noteId: string): Promise<Entity[]> =>
    apiFetch<Entity[]>(`/entities/${noteId}`),
}
```

- [ ] **Step 3: 타입체크로 검증**

Run: `npx tsc --noEmit -p .`
Expected: 에러 없음 (출력 없음)

- [ ] **Step 4: 커밋**

```bash
git add src/types/index.ts src/api/searchApi.ts
git commit -m "feat(web): add DiscoveryRoute type and searchApi.discoveryRoutes()"
```

---

### Task 3: 프론트 — StarMap에 항로 데이터 로드 + 정적 시각 요소 생성

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Consumes: `searchApi.discoveryRoutes()` (Task 2), `starMeshes: THREE.Mesh[]` / `noteIds: string[]` (기존, 노트 행성 배치 루프에서 생성됨).
- Produces: `routeVisuals: RouteVisual[]`, `shipMeshes: THREE.Mesh[]` — Task 4(애니메이션)와 Task 5(호버)가 사용. `RouteVisual { aIdx: number; bIdx: number; line: THREE.Line; ship: THREE.Mesh; t: number; dir: number }`.

- [ ] **Step 1: import 추가**

파일 상단 (7번째 줄, `useNotesStore` import 뒤)에 추가:

```typescript
import { useNotesStore } from '../../store/notesStore'
import { searchApi } from '../../api/searchApi'
import type { DiscoveryRoute } from '../../types'
```

`Tooltip`/`OrbitData`/`SunData` 인터페이스 뒤(23번째 줄 부근)에 추가:

```typescript
interface RouteVisual {
  aIdx: number
  bIdx: number
  line: THREE.Line
  ship: THREE.Mesh
  t: number
  dir: number
}
```

- [ ] **Step 2: 행성 메시에 카테고리 색 태깅**

기존 노트 배치 루프(722번째 줄 `catNotes.forEach((note, j) => {`) 안, `scene.add(mesh)` 호출 직전(809번째 줄)에 한 줄 추가:

```typescript
        mesh.add(atmo)

        mesh.userData.categoryColor = catColor.clone()

        // 동심원 궤도 반경 (안쪽부터 바깥쪽으로 일정 간격)
```

(기존 `mesh.add(atmo)` 다음 줄, `// 동심원 궤도 반경` 주석 앞에 삽입)

- [ ] **Step 3: 항로 데이터 로드 + 시각 요소 생성**

`visibleCats.forEach(cat => { ... })` 노트 배치 블록이 끝나는 지점(818번째 줄, `})` 뒤) 그리고 `// ── 카메라 컨트롤 ──` 주석(820번째 줄) 앞에 추가:

```typescript
    // ── 항로 (발견된 노트 연결) ──────────────────────────────
    const routeVisuals: RouteVisual[] = []
    const shipMeshes: THREE.Mesh[] = []
    // 콘의 뾰족한 끝을 +Z로 맞춰, 이동 방향(tangent) 벡터와
    // quaternion.setFromUnitVectors로 직접 정렬한다(lookAt은 카메라가 아닌
    // 일반 Mesh에서는 방향이 반대로 적용되는 특성이 있어 사용하지 않는다).
    const shipGeometry = new THREE.ConeGeometry(0.6, 2.2, 6)
    shipGeometry.rotateX(Math.PI / 2)
    const shipMaterial = new THREE.MeshBasicMaterial({ color: 0xf5f5ff })

    function buildRouteCurvePoints(a: THREE.Vector3, b: THREE.Vector3): THREE.Vector3[] {
      const mid = a.clone().add(b).multiplyScalar(0.5)
      mid.y += a.distanceTo(b) * 0.15
      const curve = new THREE.CatmullRomCurve3([a, mid, b])
      return curve.getPoints(24)
    }

    let routesCancelled = false
    searchApi.discoveryRoutes().then(routes => {
      if (routesCancelled) return
      routes.forEach((route: DiscoveryRoute) => {
        const aIdx = noteIds.indexOf(route.note_a)
        const bIdx = noteIds.indexOf(route.note_b)
        if (aIdx < 0 || bIdx < 0) return // 카테고리 필터로 숨겨진 노트

        const colorA = starMeshes[aIdx].userData.categoryColor as THREE.Color
        const colorB = starMeshes[bIdx].userData.categoryColor as THREE.Color
        const lineColor = colorA.clone().lerp(colorB, 0.5)

        const points = buildRouteCurvePoints(starMeshes[aIdx].position, starMeshes[bIdx].position)
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points)
        const line = new THREE.Line(
          lineGeo,
          new THREE.LineBasicMaterial({
            color: lineColor, transparent: true, opacity: 0.35,
            depthWrite: false, blending: THREE.AdditiveBlending,
          }),
        )
        scene.add(line)

        const ship = new THREE.Mesh(shipGeometry, shipMaterial)
        ship.userData.shared = route.shared_entities
        scene.add(ship)
        shipMeshes.push(ship)

        routeVisuals.push({ aIdx, bIdx, line, ship, t: Math.random(), dir: 1 })
      })
    }).catch(err => {
      console.error('discovery routes 로드 실패:', err)
    })

    // ── 카메라 컨트롤 ────────────────────────────────────────
```

- [ ] **Step 4: 씬 정리에서 fetch 취소 플래그 설정**

`return () => { ... }` cleanup 블록(943번째 줄) 첫 줄에 추가:

```typescript
    return () => {
      routesCancelled = true
      cancelAnimationFrame(animId)
```

- [ ] **Step 5: 타입체크로 검증**

Run: `npx tsc --noEmit -p .`
Expected: 에러 없음

- [ ] **Step 6: 커밋**

```bash
git add src/components/StarMap/StarMapCanvas.tsx
git commit -m "feat(web): load discovery routes and build route line/ship meshes in StarMap"
```

---

### Task 4: 프론트 — 애니메이션 루프에서 항로/우주선 갱신

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Consumes: `routeVisuals: RouteVisual[]` (Task 3), 기존 `animate()` 루프.
- Produces: 매 프레임 갱신되는 항로 곡선/우주선 위치·방향.

- [ ] **Step 1: animate() 루프에 항로 갱신 추가**

기존 `spinners.forEach((mesh, i) => { ... })` 블록(920-927번째 줄) 바로 뒤, `composer.render()` 호출(929번째 줄) 앞에 추가:

```typescript
      spinners.forEach((mesh, i) => {
        const od = orbits[i]
        od.angle += od.speed
        mesh.position.copy(od.center)
          .addScaledVector(od.e1, od.radius * Math.cos(od.angle))
          .addScaledVector(od.e2, od.radius * Math.sin(od.angle))
        mesh.rotation.y += od.selfRotY
      })

      routeVisuals.forEach(rv => {
        const a = starMeshes[rv.aIdx].position
        const b = starMeshes[rv.bIdx].position
        const points = buildRouteCurvePoints(a, b)
        rv.line.geometry.setFromPoints(points)

        rv.t += rv.dir * 0.006
        if (rv.t >= 1) { rv.t = 1; rv.dir = -1 }
        if (rv.t <= 0) { rv.t = 0; rv.dir = 1 }
        const eased = rv.t * rv.t * (3 - 2 * rv.t) // smoothstep — 양 끝에서 감속

        const curve = new THREE.CatmullRomCurve3(points)
        const pos = curve.getPointAt(Math.min(0.999, Math.max(0.001, eased)))
        const tangent = curve.getTangentAt(Math.min(0.999, Math.max(0.001, eased)))
        rv.ship.position.copy(pos)
        rv.ship.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent.normalize())
      })

      composer.render()
```

(`getPointAt`/`getTangentAt`는 0과 1에서 탄젠트가 불안정할 수 있어 0.001~0.999로 clamp)

- [ ] **Step 2: 타입체크로 검증**

Run: `npx tsc --noEmit -p .`
Expected: 에러 없음

- [ ] **Step 3: 커밋**

```bash
git add src/components/StarMap/StarMapCanvas.tsx
git commit -m "feat(web): animate discovery route curves and ships every frame"
```

---

### Task 5: 프론트 — 우주선 호버 시 공유 엔티티 툴팁

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Consumes: `shipMeshes: THREE.Mesh[]` (Task 3), 기존 `getHit()`/`pointermove` 핸들러, 기존 `Tooltip` 상태(`{ title, x, y }` — 필드 재사용).
- Produces: 우주선 호버 시 `공유: A, B` 형태의 툴팁.

- [ ] **Step 1: getHit()가 우주선도 히트테스트하도록 수정**

기존 `getHit()` 함수(841-848번째 줄)를 다음으로 교체:

```typescript
    function getHit(e: MouseEvent | PointerEvent) {
      const rect = canvas.getBoundingClientRect()
      const x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      const y = -((e.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(new THREE.Vector2(x, y), camera)
      const hits = raycaster.intersectObjects([...starMeshes, ...shipMeshes], false)
      return { hit: hits[0]?.object as THREE.Mesh | undefined, rect }
    }
```

- [ ] **Step 2: pointermove 핸들러에서 우주선 호버 시 공유 엔티티 툴팁 표시**

기존 `pointermove` 핸들러(858-882번째 줄) 중 아래 부분을 교체:

```typescript
      const { hit, rect } = getHit(e)
      if (hit) {
        const idx = starMeshes.indexOf(hit)
        const note = idx >= 0 ? visibleNotes.find(n => n.id === noteIds[idx]) : null
        if (note) {
          canvas.style.cursor = 'pointer'
          setTooltip({ title: note.title, x: e.clientX - rect.left, y: e.clientY - rect.top })
          return
        }
        const shared = hit.userData.shared as string[] | undefined
        if (shared) {
          canvas.style.cursor = 'default'
          setTooltip({ title: `공유: ${shared.join(', ')}`, x: e.clientX - rect.left, y: e.clientY - rect.top })
          return
        }
      }
      canvas.style.cursor = 'grab'
      setTooltip(null)
```

(교체 대상은 기존 코드에서 `const { hit, rect } = getHit(e)`부터 그 아래 `canvas.style.cursor = 'grab'; setTooltip(null)`까지)

- [ ] **Step 3: 타입체크로 검증**

Run: `npx tsc --noEmit -p .`
Expected: 에러 없음

- [ ] **Step 4: 커밋**

```bash
git add src/components/StarMap/StarMapCanvas.tsx
git commit -m "feat(web): show shared-entity tooltip on discovery route ship hover"
```

---

### Task 6: 수동 QA — 브라우저에서 전체 흐름 확인

**Files:** 없음 (검증 전용 태스크)

**Interfaces:**
- Consumes: Task 1~5의 모든 결과물.

- [ ] **Step 1: 백엔드 + 프론트 기동**

Run: `./start.sh` (또는 `cd backend && source venv/bin/activate && uvicorn main:app --port 8001 --reload` 와 `npm run dev`를 각각 실행)

- [ ] **Step 2: 공통 엔티티를 가진 노트 2개 생성**

브라우저에서 노트 2개를 만들고, 둘 다 같은 개념(예: "Docker")이 포함된 내용을 적어 저장 → 미개척 항로 패널에서 "전체 항로 분석" 실행 → 두 노트가 미개척 항로에 서로 연결되어 나타나는지 확인.

- [ ] **Step 3: 성도에서 항로 확인**

성도(StarMap) 탭으로 이동 → 두 노트에 해당하는 행성 사이에 옅은 색 곡선과 그 위를 왕복하는 작은 우주선이 보이는지 확인. 우주선이 두 행성 사이를 부드럽게 왕복하는지(양 끝에서 감속하는지) 육안 확인.

- [ ] **Step 4: 우주선 방향 확인 (Task 4의 lookAt 대체 로직 검증)**

우주선이 이동 방향과 반대로(꽁무니가 앞서는 형태로) 보이면, `shipGeometry.rotateX(Math.PI / 2)`를 `shipGeometry.rotateX(-Math.PI / 2)`로 바꿔 재확인. (three.js의 콘 지오메트리 기본 축 방향에 대한 수동 검증 — 코드 리뷰만으로 100% 확신하기 어려운 부분이라 반드시 육안 확인 필요.)

- [ ] **Step 5: 호버 툴팁 확인**

우주선에 마우스를 올려 "공유: Docker" 같은 툴팁이 뜨는지 확인. 행성에 마우스를 올렸을 때 기존처럼 노트 제목 툴팁이 여전히 뜨는지도 함께 확인(회귀 없는지).

- [ ] **Step 6: 카테고리 필터 확인**

사이드바에서 특정 카테고리(은하)만 보기로 필터링했을 때, 필터링으로 숨겨진 노트와 연결된 항로가 에러 없이 조용히 사라지는지 확인.

- [ ] **Step 7: 최종 커밋 (필요 시)**

Task 4에서 우주선 방향을 수정했다면:

```bash
git add src/components/StarMap/StarMapCanvas.tsx
git commit -m "fix(web): correct discovery-route ship orientation"
```

수정 없었다면 이 태스크는 커밋 없이 완료.
