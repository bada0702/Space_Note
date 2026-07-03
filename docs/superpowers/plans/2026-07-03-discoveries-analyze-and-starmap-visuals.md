# 미개척 항로 AI 분석 + 성도 비주얼 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미개척 항로 패널에 AI 분석 트리거 버튼(전체/단일)을 추가하고, 성도 3D 씬을 블룸·셰이더·동적 배치로 개선한다.

**Architecture:** 백엔드는 기존 FastAPI `notes` 라우터에 analyze 엔드포인트 2개를 추가하고 키 부재 시 조용히 성공하는 버그를 고친다. 프론트는 DiscoveriesPanel에 버튼+폴링을 추가한다. 성도는 순수 three.js 구조를 유지하며 three/examples/jsm 포스트프로세싱과 커스텀 셰이더만 추가한다.

**Tech Stack:** FastAPI + SQLite + pytest / React + zustand + three.js 0.184 (외부 의존성 추가 없음)

## Global Constraints

- 외부 npm/pip 의존성 추가 금지 (three/examples/jsm은 three에 포함되므로 허용).
- 백엔드 스펙 에러 메시지: `"Anthropic API 키가 설정되지 않았습니다"` (400).
- 성도: pixelRatio 상한 2 유지, 블룸은 절반 해상도.
- 은하 간 최소 간격: `R_i + R_j + 120` (`R = sunR + 16 + (n-1)*12`, n=0이면 60).
- 테스트 실행: `cd /var/www/html/Space_Note_v100/backend && venv/bin/python -m pytest tests -q`
- 프론트 타입 검증: `cd /var/www/html/Space_Note_v100 && npx tsc --noEmit`
- 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` 추가.

---

### Task 1: 백엔드 — API 키 부재 시 실패 처리 + has_api_key

**Files:**
- Modify: `backend/services/anthropic_client.py` (extract_entities, 새 함수 has_api_key)
- Test: `backend/tests/test_anthropic_parse.py`

**Interfaces:**
- Produces: `anthropic_client.has_api_key() -> bool`, `extract_entities()`는 키 부재 시 `ValueError` 발생.

- [ ] **Step 1: 실패하는 테스트 작성** — `backend/tests/test_anthropic_parse.py`에 추가:

```python
def test_extract_entities_raises_without_key(client):
    # client 픽스처가 ANTHROPIC_API_KEY=""로 설정하고 DB를 초기화한다
    import pytest as _pytest
    from services import anthropic_client

    assert anthropic_client.has_api_key() is False
    with _pytest.raises(ValueError):
        anthropic_client.extract_entities("내용 있는 노트")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_anthropic_parse.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'has_api_key'`

- [ ] **Step 3: 구현** — `backend/services/anthropic_client.py`의 `extract_entities`를 다음으로 교체하고 `has_api_key`를 추가:

```python
def has_api_key() -> bool:
    return bool(_api_key())


def extract_entities(content: str) -> list[dict]:
    key = _api_key()
    if not key:
        raise ValueError("Anthropic API 키가 설정되지 않았습니다")
    if not content.strip():
        return []
    client = Anthropic(api_key=key)
    msg = client.messages.create(
        model=settings.EXTRACT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": _EXTRACT_PROMPT + content}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    return parse_entities(text)
```

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest tests -q`
Expected: 전부 PASS (기존 test_notes.py의 노트 생성 테스트는 키가 없으면 이제 failed 상태가 되지만, 백그라운드 태스크 예외는 `_run_extraction`이 삼키므로 응답에는 영향 없음)

- [ ] **Step 5: Commit** — `git add backend && git commit -m "fix(backend): fail extraction explicitly when API key missing"`

---

### Task 2: 백엔드 — POST /notes/analyze (일괄) + POST /notes/{id}/analyze (단일)

**Files:**
- Modify: `backend/routers/notes.py` (list_notes 아래에 라우트 추가)
- Test: `backend/tests/test_notes_analyze.py` (신규)

**Interfaces:**
- Consumes: Task 1의 `anthropic_client.has_api_key()`.
- Produces: `POST /notes/analyze -> {"queued": int}` / `POST /notes/{nid}/analyze -> {"queued": 1}` / 키 없음 400, 노트 없음 404.

- [ ] **Step 1: 실패하는 테스트 작성** — `backend/tests/test_notes_analyze.py` 생성:

```python
from tests.conftest import AUTH


def _make_note(client, title="노트", content="Claude와 우주에 대한 메모"):
    r = client.post("/notes", json={"title": title, "content": content}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def test_analyze_all_without_key_returns_400(client):
    r = client.post("/notes/analyze", headers=AUTH)
    assert r.status_code == 400
    assert "API 키" in r.json()["detail"]


def test_analyze_all_queues_failed_and_pending_notes(client, monkeypatch):
    from routers import notes as notes_router
    monkeypatch.setattr(notes_router.anthropic_client, "has_api_key", lambda: True)
    monkeypatch.setattr(
        notes_router.anthropic_client, "extract_entities",
        lambda content: [{"name": "Claude", "type": "개념"}],
    )
    n1 = _make_note(client, "a")          # 생성 시 추출 성공 → analyzed
    _make_note(client, "빈노트", "")       # 내용 없음 → 큐잉 대상 아님

    # n1을 failed로 되돌려 재분석 대상으로 만든다
    from db import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE notes SET analysis_status='failed' WHERE id=?", (n1["id"],))
        conn.execute("DELETE FROM entities WHERE note_id=?", (n1["id"],))

    r = client.post("/notes/analyze", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["queued"] == 1

    # TestClient는 응답 후 BackgroundTasks를 동기 실행 → 상태/엔티티 확인
    got = client.get(f"/notes/{n1['id']}", headers=AUTH).json()
    assert got["analysis_status"] == "analyzed"
    ents = client.get(f"/entities/{n1['id']}", headers=AUTH).json()
    assert [e["name"] for e in ents] == ["Claude"]


def test_analyze_one(client, monkeypatch):
    from routers import notes as notes_router
    monkeypatch.setattr(notes_router.anthropic_client, "has_api_key", lambda: True)
    monkeypatch.setattr(
        notes_router.anthropic_client, "extract_entities",
        lambda content: [{"name": "우주", "type": "개념"}],
    )
    n = _make_note(client)
    r = client.post(f"/notes/{n['id']}/analyze", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["queued"] == 1
    got = client.get(f"/notes/{n['id']}", headers=AUTH).json()
    assert got["analysis_status"] == "analyzed"


def test_analyze_one_missing_note_404(client, monkeypatch):
    from routers import notes as notes_router
    monkeypatch.setattr(notes_router.anthropic_client, "has_api_key", lambda: True)
    r = client.post("/notes/does-not-exist/analyze", headers=AUTH)
    assert r.status_code == 404
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && venv/bin/python -m pytest tests/test_notes_analyze.py -q`
Expected: FAIL — analyze 라우트 404/405

- [ ] **Step 3: 구현** — `backend/routers/notes.py`의 `list_notes` 함수 아래에 추가 (`create_note`보다 위여도 무방):

```python
def _require_api_key() -> None:
    if not anthropic_client.has_api_key():
        raise HTTPException(
            status_code=400, detail="Anthropic API 키가 설정되지 않았습니다"
        )


@router.post("/notes/analyze")
def analyze_all(bg: BackgroundTasks):
    """내용이 있는 pending/failed 노트 전체를 백그라운드로 재분석."""
    _require_api_key()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content FROM notes "
            "WHERE TRIM(COALESCE(content, '')) != '' "
            "AND analysis_status IN ('pending', 'failed')"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE notes SET analysis_status = 'pending' WHERE id = ?",
                (r["id"],),
            )
    for r in rows:
        bg.add_task(_run_extraction, r["id"], r["content"])
    return {"queued": len(rows)}


@router.post("/notes/{nid}/analyze")
def analyze_one(nid: str, bg: BackgroundTasks):
    _require_api_key()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, content FROM notes WHERE id = ?", (nid,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Note not found")
    with get_conn() as conn:
        conn.execute(
            "UPDATE notes SET analysis_status = 'pending' WHERE id = ?", (nid,)
        )
    bg.add_task(_run_extraction, nid, row["content"] or "")
    return {"queued": 1}
```

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `cd backend && venv/bin/python -m pytest tests -q`
Expected: 전부 PASS

- [ ] **Step 5: Commit** — `git add backend && git commit -m "feat(backend): batch and single note analyze endpoints"`

---

### Task 3: 프론트 — DiscoveriesPanel 분석 버튼 + 폴링

**Files:**
- Modify: `src/api/notesApi.ts` (analyzeAll/analyzeOne 추가)
- Modify: `src/components/Navigation/DiscoveriesPanel.tsx` (버튼 줄 교체)

**Interfaces:**
- Consumes: Task 2의 두 엔드포인트, 기존 `useNotesStore().fetchNotes`, `Note.analysis_status`, `Note.word_count`.
- Produces: 없음 (말단 UI).

- [ ] **Step 1: notesApi에 메서드 추가** — `src/api/notesApi.ts`의 `delete:` 줄 뒤에:

```ts
  analyzeAll: () =>
    apiFetch<{ queued: number }>('/notes/analyze', { method: 'POST' }),
  analyzeOne: (id: string) =>
    apiFetch<{ queued: number }>(`/notes/${id}/analyze`, { method: 'POST' }),
```

- [ ] **Step 2: DiscoveriesPanel 수정** — 임포트에 `notesApi`, `useRef` 추가:

```ts
import { useEffect, useRef, useState } from 'react'
import { notesApi } from '../../api/notesApi'
```

컴포넌트 상단(기존 훅 아래)에 상태와 핸들러 추가. `fetchNotes`는 `useNotesStore()`에서 함께 구조분해:

```ts
  const { activeNote, openNote, setTab, fetchNotes } = useNotesStore()
  const [analyzing, setAnalyzing] = useState(false)
  const [notice, setNotice] = useState('')
  const alive = useRef(true)
  useEffect(() => () => { alive.current = false }, [])

  // 내용 있는 노트의 pending이 모두 풀릴 때까지 3초 간격 폴링 (최대 60초)
  const pollUntilDone = async () => {
    for (let i = 0; i < 20 && alive.current; i++) {
      await new Promise(r => setTimeout(r, 3000))
      const list = await notesApi.list()
      const busy = list.some(n => n.analysis_status === 'pending' && n.word_count > 0)
      if (!busy) return
    }
  }

  const runAnalyze = async (call: () => Promise<{ queued: number }>) => {
    setNotice('')
    setAnalyzing(true)
    try {
      const { queued } = await call()
      if (queued === 0) {
        setNotice('분석할 노트가 없습니다')
        return
      }
      setNotice(`${queued}개 노트 분석 중...`)
      await pollUntilDone()
      if (!alive.current) return
      await fetchNotes()
      await loadDiscoveries(activeNote?.id)
      setNotice('')
    } catch (e: any) {
      setNotice(
        String(e?.message).includes('API 400')
          ? '설정에서 Anthropic API 키를 먼저 저장하세요'
          : '분석 요청에 실패했습니다',
      )
    } finally {
      if (alive.current) setAnalyzing(false)
    }
  }
```

- [ ] **Step 3: 버튼 줄 JSX 교체** — 기존 "새로고침" div 블록(`{/* 새로고침 */}` 주석부터 그 `</div>`까지)을 다음으로 교체:

```tsx
      {/* 분석/새로고침 */}
      <div style={{ padding: '6px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button
            onClick={() => runAnalyze(() => notesApi.analyzeAll())}
            disabled={analyzing}
            style={{
              fontSize: 11, color: 'var(--text-primary)',
              background: 'var(--bg-input)', border: '1px solid var(--accent-line)',
              borderRadius: 4, padding: '3px 10px',
              cursor: analyzing ? 'wait' : 'pointer', opacity: analyzing ? 0.6 : 1,
            }}
          >
            ⟡ 전체 항로 분석
          </button>
          {activeNote && (
            <button
              onClick={() => runAnalyze(() => notesApi.analyzeOne(activeNote.id))}
              disabled={analyzing}
              style={{
                fontSize: 11, color: 'var(--text-secondary)',
                background: 'var(--bg-input)', border: '1px solid var(--border)',
                borderRadius: 4, padding: '3px 10px',
                cursor: analyzing ? 'wait' : 'pointer', opacity: analyzing ? 0.6 : 1,
              }}
            >
              이 노트 분석
            </button>
          )}
          <button
            onClick={() => loadDiscoveries(activeNote?.id)}
            disabled={analyzing}
            style={{
              fontSize: 11, color: 'var(--text-secondary)',
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
            }}
          >
            ↺ 새로고침
          </button>
        </div>
        {notice && (
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--accent-line)' }}>
            {notice}
          </div>
        )}
      </div>
```

- [ ] **Step 4: 타입 검증**

Run: `npx tsc --noEmit`
Expected: 에러 없음 (Note에 word_count가 없으면 `src/types/index.ts`의 Note에 `word_count: number` 추가 — 백엔드 응답에는 이미 포함됨)

- [ ] **Step 5: Commit** — `git add src && git commit -m "feat(web): analyze buttons with polling in discoveries panel"`

---

### Task 4: 성도 — 은하 간 간격 보장 동적 배치

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Produces: `computeStarPositions(counts: number[]): THREE.Vector3[]` — 이후 Task 7이 systemRadii를 재사용.

- [ ] **Step 1: 배치 함수 추가** — `STAR_POSITIONS` 상수 선언 바로 아래에:

```ts
// 은하계(항성계)의 최대 궤도 반경: 궤도 배치 공식과 동일하게 유지할 것
function systemRadius(noteCount: number): number {
  const sunR = Math.max(5, 4 + noteCount * 0.25)
  return noteCount > 0 ? sunR + 16 + (noteCount - 1) * 12 : 60
}

// 항성 위치를 동적으로 계산: 모든 쌍이 R_i + R_j + MARGIN 이상 떨어지도록
// 기존 STAR_POSITIONS의 방향만 쓰고 거리를 늘려가며 배치한다.
function computeStarPositions(counts: number[]): THREE.Vector3[] {
  const MARGIN = 120
  const radii = counts.map(systemRadius)
  const out: THREE.Vector3[] = []
  for (let i = 0; i < counts.length; i++) {
    if (i === 0) { out.push(new THREE.Vector3(0, 0, 0)); continue }
    const base = STAR_POSITIONS[i % STAR_POSITIONS.length]
    const dir = base.lengthSq() > 0
      ? base.clone().normalize()
      : new THREE.Vector3(Math.sin(i * 2.4), Math.sin(i * 1.7) * 0.5, Math.cos(i * 2.4)).normalize()
    let d = radii[i] + radii[0] + MARGIN
    let placed = dir.clone().multiplyScalar(d)
    for (let guard = 0; guard < 400; guard++) {
      let ok = true
      for (let j = 0; j < i; j++) {
        if (placed.distanceTo(out[j]) < radii[i] + radii[j] + MARGIN) { ok = false; break }
      }
      if (ok) break
      d += 60
      placed = dir.clone().multiplyScalar(d)
    }
    out.push(placed)
  }
  return out
}
```

- [ ] **Step 2: 사용처 교체** — `useEffect` 안에서 `visibleNotes/visibleCats` 계산 직후에:

```ts
    const noteCounts = categories.map(c => notes.filter(n => n.category_id === c.id).length)
    const starPositions = computeStarPositions(noteCounts)
```

그리고 파일 내 `STAR_POSITIONS[ci % STAR_POSITIONS.length]` 3곳(카메라 초점, 항성 배치, 궤도 중심)을 모두 `starPositions[ci]`로 교체. 카메라 초기 거리 `initCamR`은 전체 뷰일 때 `Math.max(400, starPositions.reduce((m, p) => Math.max(m, p.length()), 0) * 1.6)`으로 변경(멀어진 은하가 모두 보이도록). 줌 상한도 `Math.min(1200, ...)` → `Math.min(Math.max(1200, initCamR * 2), ...)` 형태로:

```ts
    const maxZoom = Math.max(1200, initCamR * 2)
    // wheel 핸들러에서:
    camR = Math.max(40, Math.min(maxZoom, camR + e.deltaY * 0.5))
```

- [ ] **Step 3: 검증**

Run: `npx tsc --noEmit`
Expected: 에러 없음. 브라우저에서 성도 열어 은하들이 서로 떨어져 있는지 확인.

- [ ] **Step 4: Commit** — `git add src && git commit -m "feat(starmap): dynamic star placement guaranteeing galaxy separation"`

---

### Task 5: 성도 — 블룸 포스트프로세싱 + 원형 별 파티클

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Produces: `composer` (애니메이션 루프에서 사용), `makeStarSpriteTexture()` (Task 7 재사용).

- [ ] **Step 1: 임포트 추가**

```ts
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
```

- [ ] **Step 2: 톤매핑 + 컴포저** — renderer 생성 직후에:

```ts
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.15
```

조명 섹션 앞(또는 뒤 아무 곳)에:

```ts
    const composer = new EffectComposer(renderer)
    composer.addPass(new RenderPass(scene, camera))
    const bloom = new UnrealBloomPass(
      new THREE.Vector2(width / 2, height / 2), // 절반 해상도
      0.85,  // strength
      0.6,   // radius
      0.78,  // threshold — 항성/밝은 별만 빛나게
    )
    composer.addPass(bloom)
```

animate()의 `renderer.render(scene, camera)`를 `composer.render()`로 교체. ResizeObserver 콜백에 `composer.setSize(w, h)` 추가. cleanup에 `composer.dispose()` 추가.

- [ ] **Step 3: 원형 별 파티클** — `makeGlowTexture` 아래에 추가:

```ts
// 작은 원형 소프트 파티클 (별 포인트용 — 사각형 픽셀 제거)
function makeStarSpriteTexture(): THREE.Texture {
  const s = 64
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!
  const grad = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2)
  grad.addColorStop(0, 'rgba(255,255,255,1)')
  grad.addColorStop(0.35, 'rgba(255,255,255,0.7)')
  grad.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, s, s)
  return new THREE.CanvasTexture(canvas)
}
```

`buildStars`의 PointsMaterial을 다음으로 교체 (`starTex`는 useEffect 초입에서 한 번 생성해 disposables에 등록):

```ts
      const mat = new THREE.PointsMaterial({
        size, sizeAttenuation: true, vertexColors: true,
        map: starTex, transparent: true, opacity,
        depthWrite: false, blending: THREE.AdditiveBlending,
      })
```

- [ ] **Step 4: 검증**

Run: `npx tsc --noEmit` → 에러 없음. 브라우저에서 항성이 빛나고 별이 원형인지, 드래그/줌/클릭이 그대로 동작하는지 확인.

- [ ] **Step 5: Commit** — `git add src && git commit -m "feat(starmap): bloom post-processing and round star particles"`

---

### Task 6: 성도 — 항성 표면 셰이더 + 행성 대기 셸

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Consumes: Task 5의 composer 루프.
- Produces: `sunMaterials: THREE.ShaderMaterial[]` (animate에서 uTime 갱신).

- [ ] **Step 1: 셰이더 소스 추가** — 파일 상단 상수 영역에:

```ts
const SUN_VERT = /* glsl */ `
varying vec3 vPos;
void main() {
  vPos = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`

const SUN_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform float uTime;
varying vec3 vPos;
float hash(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float noise(vec3 p) {
  vec3 i = floor(p); vec3 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x),
        mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
    mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
        mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y),
    f.z);
}
float fbm(vec3 p) {
  float v = 0.0; float a = 0.5;
  for (int k = 0; k < 4; k++) { v += a * noise(p); p *= 2.1; a *= 0.5; }
  return v;
}
void main() {
  vec3 p = normalize(vPos);
  float n = fbm(p * 3.0 + vec3(uTime * 0.15, 0.0, uTime * 0.08));
  n += 0.5 * fbm(p * 9.0 - vec3(0.0, uTime * 0.22, 0.0));
  vec3 hot = vec3(1.0, 0.97, 0.88);
  vec3 col = mix(uColor * 0.9, hot, smoothstep(0.4, 1.15, n));
  col *= 1.2 + 0.7 * n; // 밝기를 1 이상으로 밀어 블룸을 유도
  gl_FragColor = vec4(col, 1.0);
}`

const ATMO_VERT = /* glsl */ `
varying vec3 vNormal;
varying vec3 vView;
void main() {
  vNormal = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`

const ATMO_FRAG = /* glsl */ `
uniform vec3 uColor;
varying vec3 vNormal;
varying vec3 vView;
void main() {
  float rim = pow(1.0 - abs(dot(normalize(vNormal), normalize(vView))), 2.5);
  gl_FragColor = vec4(uColor, rim * 0.55);
}`
```

- [ ] **Step 2: 항성 재질 교체** — `visibleCats.forEach` 내 항성 생성부에서 `MeshBasicMaterial({ color })`를 셰이더로 교체하고 흰 코어 메시는 삭제:

```ts
      const sunMat = new THREE.ShaderMaterial({
        vertexShader: SUN_VERT,
        fragmentShader: SUN_FRAG,
        uniforms: {
          uColor: { value: color.clone() },
          uTime: { value: Math.random() * 100 },
        },
      })
      const sunMesh = new THREE.Mesh(new THREE.SphereGeometry(sunR, 48, 32), sunMat)
      sunMesh.position.copy(pos)
      sunMaterials.push(sunMat)
```

`const sunMaterials: THREE.ShaderMaterial[] = []`를 sunDatas 선언 옆에 추가. animate()에 `sunMaterials.forEach(m => { m.uniforms.uTime.value += 0.016 })` 추가. (innerGlow/coronaGlow/라벨은 유지.)

- [ ] **Step 3: 행성 대기 셸** — 행성 생성부의 림 글로우 스프라이트 블록을 다음으로 교체:

```ts
        // 프레넬 대기 셸 (스프라이트 글로우 대체)
        const atmo = new THREE.Mesh(
          new THREE.SphereGeometry(planetR * 1.22, 28, 20),
          new THREE.ShaderMaterial({
            vertexShader: ATMO_VERT,
            fragmentShader: ATMO_FRAG,
            uniforms: { uColor: { value: catColor.clone() } },
            transparent: true,
            side: THREE.BackSide,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          }),
        )
        mesh.add(atmo)
```

- [ ] **Step 4: 텍스처 해상도 상향** — `makePlanetTexture`의 `const w = 512; const h = 256`을 `1024/512`로 변경.

- [ ] **Step 5: 검증** — `npx tsc --noEmit` 에러 없음. 브라우저에서 항성이 이글거리고 행성 가장자리에 대기 산란이 보이는지 확인.

- [ ] **Step 6: Commit** — `git add src && git commit -m "feat(starmap): animated sun shader and fresnel planet atmospheres"`

---

### Task 7: 성도 — 배경 심화(은하수·성운) + 궤도 페이드 + 나선 성간먼지

**Files:**
- Modify: `src/components/StarMap/StarMapCanvas.tsx`

**Interfaces:**
- Consumes: Task 5의 `makeStarSpriteTexture`(starTex), Task 4의 `systemRadius`.

- [ ] **Step 1: 은하수 밴드** — 별하늘 빌드 직후에 추가:

```ts
    // 은하수 밴드: 기울어진 원환에 밀집된 파티클 띠
    function buildMilkyWay() {
      const count = 9000
      const pos = new Float32Array(count * 3)
      const col = new Float32Array(count * 3)
      const euler = new THREE.Euler(0.5, 0, 0.35)
      const v = new THREE.Vector3()
      for (let i = 0; i < count; i++) {
        const a = Math.random() * Math.PI * 2
        const r = 1500 + (Math.random() - 0.5) * 700
        const spread = Math.pow(Math.random(), 2) * 260 * (Math.random() < 0.5 ? 1 : -1)
        v.set(Math.cos(a) * r, spread, Math.sin(a) * r).applyEuler(euler)
        pos[i * 3] = v.x; pos[i * 3 + 1] = v.y; pos[i * 3 + 2] = v.z
        const w = 0.45 + Math.random() * 0.55
        col[i * 3] = 0.82 * w; col[i * 3 + 1] = 0.86 * w; col[i * 3 + 2] = w
      }
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
      const mat = new THREE.PointsMaterial({
        size: 1.6, sizeAttenuation: true, vertexColors: true, map: starTex,
        transparent: true, opacity: 0.35, depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
      scene.add(new THREE.Points(geo, mat))
    }
    buildMilkyWay()
```

성운 스펙 배열에 2개 추가:

```ts
      [60, 90, 200, new THREE.Vector3(-400, -600, -2100), 2400],
      [170, 120, 60, new THREE.Vector3(1500, 500, -2300), 1900],
```

- [ ] **Step 2: 궤도선 페이드** — 궤도선 생성부의 `LineBasicMaterial`을 정점 색 그라데이션으로 교체:

```ts
        const orbitCols: number[] = []
        for (let s = 0; s <= segs; s++) {
          const fade = 0.25 + 0.75 * Math.abs(Math.sin((s / segs) * Math.PI * 2))
          orbitCols.push(catColor.r * fade, catColor.g * fade, catColor.b * fade)
        }
        orbitGeo.setAttribute('color', new THREE.Float32BufferAttribute(orbitCols, 3))
        const orbitLine = new THREE.Line(
          orbitGeo,
          new THREE.LineBasicMaterial({
            vertexColors: true, transparent: true, opacity: 0.18,
            depthWrite: false, blending: THREE.AdditiveBlending,
          }),
        )
```

- [ ] **Step 3: 나선 성간먼지** — 항성 생성부(sunDatas.push 근처)에서 카테고리별로 호출:

```ts
    // 항성 주위 나선팔 성간먼지
    function buildSpiralDust(center: THREE.Vector3, color: THREE.Color, maxR: number) {
      const count = 500
      const pos = new Float32Array(count * 3)
      const col = new Float32Array(count * 3)
      const white = new THREE.Color(1, 1, 1)
      const tmp = new THREE.Color()
      for (let i = 0; i < count; i++) {
        const t = Math.random()
        const arm = Math.random() < 0.5 ? 0 : Math.PI
        const a = arm + t * Math.PI * 3.2 + (Math.random() - 0.5) * 0.5
        const r = 8 + t * maxR
        pos[i * 3] = center.x + Math.cos(a) * r
        pos[i * 3 + 1] = center.y + (Math.random() - 0.5) * 6
        pos[i * 3 + 2] = center.z + Math.sin(a) * r
        tmp.copy(color).lerp(white, t * 0.6)
        col[i * 3] = tmp.r; col[i * 3 + 1] = tmp.g; col[i * 3 + 2] = tmp.b
      }
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
      const mat = new THREE.PointsMaterial({
        size: 1.1, sizeAttenuation: true, vertexColors: true, map: starTex,
        transparent: true, opacity: 0.3, depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
      scene.add(new THREE.Points(geo, mat))
    }
```

호출부 (항성 forEach 안, noteCount 계산 이후):

```ts
      buildSpiralDust(pos, color, systemRadius(noteCount))
```

- [ ] **Step 4: 검증** — `npx tsc --noEmit` 에러 없음. 브라우저에서 프레임 드랍 없이(60fps 근처) 은하수/성운/나선먼지가 보이는지, 필터 뷰(은하 클릭)도 정상인지 확인.

- [ ] **Step 5: Commit** — `git add src && git commit -m "feat(starmap): milky way band, orbit fade, spiral dust"`

---

## 최종 검증

- [ ] `cd backend && venv/bin/python -m pytest tests -q` 전부 PASS
- [ ] `npx tsc --noEmit` 에러 없음
- [ ] 브라우저 QA: 설정에서 API 키 저장 → 미개척 항로에서 "전체 항로 분석" → 항로 목록 표시 → 성도에서 은하 간 간격/블룸/셰이더 확인
