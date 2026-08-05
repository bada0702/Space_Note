import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { useCategoriesStore } from '../../store/categoriesStore'
import { useNotesStore } from '../../store/notesStore'
import { searchApi } from '../../api/searchApi'
import { tagsApi } from '../../api/tagsApi'
import type { DiscoveryRoute } from '../../types'

interface Tooltip {
  title: string
  x: number
  y: number
}

interface OrbitData {
  center: THREE.Vector3
  radius: number
  e1: THREE.Vector3   // 궤도 평면 기저 벡터 1
  e2: THREE.Vector3   // 궤도 평면 기저 벡터 2
  speed: number
  angle: number
  selfRotY: number
  isRogue?: boolean
  velocity?: THREE.Vector3
  mass?: number
  planetR?: number
}

interface SunData {
  mesh: THREE.Mesh
  glow?: THREE.Sprite
  glowBase?: number
  phase: number
}

interface RouteVisual {
  aIdx: number
  bIdx: number
  line: THREE.Line
  ship: THREE.Mesh
  t: number
  dir: number
}

// 각 카테고리 항성의 3D 위치
const STAR_POSITIONS = [
  new THREE.Vector3(0, 0, 0),
  new THREE.Vector3(140, 35, -75),
  new THREE.Vector3(-115, -25, 85),
  new THREE.Vector3(75, 95, 95),
  new THREE.Vector3(-145, 45, -105),
  new THREE.Vector3(165, -55, 45),
  new THREE.Vector3(-65, -105, -85),
  new THREE.Vector3(55, -85, 125),
]

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

// 궤도 반경: 간격을 누적해 계산 — 바깥으로 갈수록 간격이 커지고(축소되지 않고),
// 각 간격에 불규칙한 요철을 더해 완전히 매끈한 등간격으로 보이지 않게 한다.
// 노트가 최대 800개까지 있을 수 있으므로(catNotes.slice(0, 800)), 누적 반경이
// 카메라 far plane(25000)을 넘지 않도록 간격 증가폭을 억제해야 한다 — 이전 계수
// (floor 38, base 55 + k^0.6*14)는 800개 누적 시 반경이 40만 단위까지 폭증해
// 카메라가 은하 전체를 far plane 밖에 두고 아무것도 렌더링하지 못하는 원인이었다.
function orbitRadius(sunR: number, j: number): number {
  // 첫 궤도는 태양 표면에 바짝 붙이고(스케일 배율 미적용), 노트가 쌓이며
  // 벌어지는 누적 간격만 ×10 스케일을 적용해 대형 성계에서도 far plane을
  // 넘지 않게 한다 — 그래야 태양 크기와 무관하게 행성들이 태양 가까이 모인다.
  const baseGap = 100
  let acc = 0
  for (let k = 1; k <= j; k++) {
    // k가 작을 때는 간격을 넓게 퍼뜨리고, k가 커질수록 증가율을 낮추어
    // 대형 성계(최대 800개)도 카메라 far plane(25000) 안쪽 범위(1만 이하)에 유지되도록 함
    const growth = 65.0 / (1.0 + Math.pow(k, 0.48)) + 6.0
    const irregular = 4.0 * Math.sin(k * 2.63) + 2.5 * Math.sin(k * 0.97 + 1.3)
    acc += Math.max(8, growth + irregular)
  }
  return sunR + baseGap + acc * 10
}

// 은하계(항성계)의 최대 궤도 반경: 궤도 배치 공식과 동일하게 유지할 것
function systemRadius(noteCount: number): number {
  const displayCount = Math.min(noteCount, 800)
  if (displayCount === 0) return 600
  const sunR = 500.0
  return orbitRadius(sunR, displayCount - 1) + 400
}

// 항성 위치를 동적으로 계산: 모든 쌍이 R_i + R_j + MARGIN 이상 떨어지도록
// 기존 STAR_POSITIONS의 방향만 쓰고 거리를 늘려가며 배치한다.
function computeStarPositions(counts: number[]): THREE.Vector3[] {
  const MARGIN = 1200
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
      d += 600
      placed = dir.clone().multiplyScalar(d)
    }
    out.push(placed)
  }
  return out
}

// ── 색 유틸 ──────────────────────────────────────────────────
const clamp255 = (v: number) => Math.max(0, Math.min(255, v | 0))
function rgb(r: number, g: number, b: number, a = 1) {
  return `rgba(${clamp255(r)},${clamp255(g)},${clamp255(b)},${a})`
}

// 절차적 표면 텍스처: 가스/얼음 거성용 가로 줄무늬
function paintBands(
  ctx: CanvasRenderingContext2D, w: number, h: number,
  palette: [number, number, number][], swirls: number, swirlAlpha: number,
) {
  for (let y = 0; y < h; y++) {
    const f = (y / h) * (palette.length - 1)
    const i = Math.floor(f)
    const frac = f - i
    const a = palette[i]
    const b = palette[Math.min(i + 1, palette.length - 1)]
    const n = (Math.random() - 0.5) * 12
    ctx.fillStyle = rgb(
      a[0] + (b[0] - a[0]) * frac + n,
      a[1] + (b[1] - a[1]) * frac + n,
      a[2] + (b[2] - a[2]) * frac + n,
    )
    ctx.fillRect(0, y, w, 1)
  }
  // 난류 소용돌이 (가로로 늘어난 타원)
  for (let k = 0; k < swirls; k++) {
    const y = Math.random() * h
    const x = Math.random() * w
    const rw = 8 + Math.random() * 40
    const rh = 1.5 + Math.random() * 4
    const tone = Math.random() < 0.5 ? 255 : 0
    ctx.fillStyle = rgb(tone, tone, tone, Math.random() * swirlAlpha)
    ctx.beginPath()
    ctx.ellipse(x, y, rw, rh, 0, 0, Math.PI * 2)
    ctx.fill()
  }
}

// 불규칙 얼룩 (대륙/지형/크레이터)
function blobs(
  ctx: CanvasRenderingContext2D, w: number, h: number,
  count: number, color: [number, number, number], rmin: number, rmax: number, alpha: number,
) {
  for (let k = 0; k < count; k++) {
    const x = Math.random() * w
    const y = h * (0.15 + Math.random() * 0.7) // 극지방은 비움
    const r = rmin + Math.random() * (rmax - rmin)
    const jitter = (Math.random() - 0.5) * 40
    ctx.fillStyle = rgb(color[0] + jitter, color[1] + jitter, color[2] + jitter, alpha)
    ctx.beginPath()
    ctx.ellipse(x, y, r, r * (0.6 + Math.random() * 0.6), Math.random() * Math.PI, 0, Math.PI * 2)
    ctx.fill()
  }
}

// 극관 (지구/화성)
function polarCaps(ctx: CanvasRenderingContext2D, w: number, h: number, depth: number) {
  const g1 = ctx.createLinearGradient(0, 0, 0, h * depth)
  g1.addColorStop(0, 'rgba(255,255,255,0.95)')
  g1.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g1
  ctx.fillRect(0, 0, w, h * depth)
  const g2 = ctx.createLinearGradient(0, h, 0, h * (1 - depth))
  g2.addColorStop(0, 'rgba(255,255,255,0.95)')
  g2.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g2
  ctx.fillRect(0, h * (1 - depth), w, h * depth)
}

type PlanetKind = {
  name: string
  size: number
  ring: 'saturn' | 'uranus' | null
  paint: (ctx: CanvasRenderingContext2D, w: number, h: number) => void
}

const PLANET_KINDS: PlanetKind[] = [
  {
    name: 'jupiter', size: 40.0, ring: null,
    paint: (c, w, h) => {
      paintBands(c, w, h, [
        [216, 176, 132], [240, 222, 188], [198, 150, 110], [232, 210, 178],
        [180, 130, 96], [238, 224, 196], [206, 162, 120],
      ], 220, 0.18)
      // 대적점
      c.fillStyle = rgb(196, 88, 64, 0.85)
      c.beginPath()
      c.ellipse(w * 0.32, h * 0.62, w * 0.06, h * 0.05, 0, 0, Math.PI * 2)
      c.fill()
    },
  },
  {
    name: 'saturn', size: 34.0, ring: 'saturn',
    paint: (c, w, h) => paintBands(c, w, h, [
      [228, 206, 158], [240, 226, 190], [214, 188, 140], [236, 220, 182], [206, 178, 130],
    ], 150, 0.12),
  },
  {
    name: 'venus', size: 20.0, ring: null,
    paint: (c, w, h) => paintBands(c, w, h, [
      [232, 206, 150], [246, 228, 184], [220, 188, 132], [240, 218, 168], [226, 198, 144],
    ], 320, 0.22),
  },
  {
    name: 'earth', size: 20.0, ring: null,
    paint: (c, w, h) => {
      // 바다
      c.fillStyle = rgb(28, 64, 120)
      c.fillRect(0, 0, w, h)
      paintBands(c, w, h, [[26, 60, 116], [34, 78, 140], [24, 56, 110]], 60, 0.06)
      // 대륙
      blobs(c, w, h, 22, [70, 120, 66], w * 0.03, w * 0.08, 0.9)
      blobs(c, w, h, 16, [120, 110, 70], w * 0.02, w * 0.05, 0.6)
      polarCaps(c, w, h, 0.1)
      // 구름
      blobs(c, w, h, 28, [255, 255, 255], w * 0.02, w * 0.06, 0.4)
    },
  },
  {
    name: 'mars', size: 16.0, ring: null,
    paint: (c, w, h) => {
      paintBands(c, w, h, [[196, 108, 66], [176, 92, 56], [206, 122, 78], [168, 84, 52]], 80, 0.1)
      blobs(c, w, h, 26, [128, 62, 40], w * 0.02, w * 0.06, 0.5)
      polarCaps(c, w, h, 0.07)
    },
  },
  {
    name: 'neptune', size: 26.0, ring: null,
    paint: (c, w, h) => {
      paintBands(c, w, h, [[42, 78, 168], [60, 104, 196], [38, 70, 150], [70, 116, 206]], 90, 0.1)
      // 대흑점
      c.fillStyle = rgb(20, 38, 96, 0.6)
      c.beginPath()
      c.ellipse(w * 0.6, h * 0.42, w * 0.05, h * 0.045, 0, 0, Math.PI * 2)
      c.fill()
    },
  },
  {
    name: 'uranus', size: 24.0, ring: 'uranus',
    paint: (c, w, h) => paintBands(c, w, h, [
      [150, 214, 214], [180, 230, 226], [136, 200, 202], [172, 224, 220],
    ], 50, 0.06),
  },
  {
    name: 'mercury', size: 14.0, ring: null,
    paint: (c, w, h) => {
      paintBands(c, w, h, [[126, 116, 104], [150, 140, 126], [110, 102, 92]], 40, 0.08)
      blobs(c, w, h, 40, [80, 74, 66], w * 0.008, w * 0.03, 0.5)
      blobs(c, w, h, 24, [180, 172, 158], w * 0.006, w * 0.02, 0.4)
    },
  },
]

function makePlanetTexture(kind: PlanetKind): THREE.Texture {
  const w = 1024
  const h = 512
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')!
  kind.paint(ctx, w, h)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.wrapS = THREE.RepeatWrapping
  return tex
}

// 토성형 고리 텍스처 (가로 = 반경 방향, Cassini 간극 포함)
function makeRingTexture(): THREE.Texture {
  const w = 256
  const h = 8
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')!
  for (let x = 0; x < w; x++) {
    const t = x / w
    let a = 0.85
    a *= 0.6 + 0.4 * Math.sin(t * 46)           // 미세 밴딩
    if (t < 0.04) a = 0                          // 안쪽 빈 공간
    if (t > 0.46 && t < 0.52) a *= 0.12          // Cassini 간극
    a *= 1 - t * 0.35                            // 바깥쪽 옅어짐
    const tone = 205 + Math.random() * 35
    ctx.fillStyle = rgb(tone, tone - 18, tone - 52, Math.max(0, a))
    ctx.fillRect(x, 0, 1, h)
  }
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

// 반경 방향으로 텍스처가 펼쳐지도록 UV를 재계산한 고리 지오메트리
function makeRingGeometry(inner: number, outer: number): THREE.RingGeometry {
  const g = new THREE.RingGeometry(inner, outer, 80, 1)
  const pos = g.attributes.position
  const uv = g.attributes.uv
  const v = new THREE.Vector3()
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i)
    const r = v.length()
    uv.setXY(i, (r - inner) / (outer - inner), 0.5)
  }
  return g
}

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

function makeGlowTexture(): THREE.Texture {
  const size = 256
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  grad.addColorStop(0, 'rgba(255,255,255,1)')
  grad.addColorStop(0.15, 'rgba(255,255,255,0.95)')
  grad.addColorStop(0.4, 'rgba(255,255,255,0.4)')
  grad.addColorStop(0.75, 'rgba(255,255,255,0.08)')
  grad.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, size, size)
  return new THREE.CanvasTexture(canvas)
}

// 부드러운 성운 구름 텍스처
function makeNebulaTexture(r: number, g: number, b: number): THREE.Texture {
  const size = 256
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, size, size)
  for (let k = 0; k < 14; k++) {
    const x = size / 2 + (Math.random() - 0.5) * size * 0.5
    const y = size / 2 + (Math.random() - 0.5) * size * 0.5
    const rad = size * (0.12 + Math.random() * 0.28)
    const grad = ctx.createRadialGradient(x, y, 0, x, y, rad)
    grad.addColorStop(0, rgb(r, g, b, 0.5))
    grad.addColorStop(1, rgb(r, g, b, 0))
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(x, y, rad, 0, Math.PI * 2)
    ctx.fill()
  }
  return new THREE.CanvasTexture(canvas)
}

function makeLabelSprite(name: string, color: THREE.Color): THREE.Sprite {
  const text = name.toUpperCase()
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  const font = '600 18px monospace'
  ctx.font = font
  const tw = ctx.measureText(text).width
  const cw = Math.ceil(tw) + 28
  const ch = 32
  canvas.width = cw
  canvas.height = ch
  ctx.clearRect(0, 0, cw, ch)
  ctx.font = font
  const hex = `#${color.getHexString()}`
  ctx.fillStyle = hex
  ctx.globalAlpha = 0.85
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, cw / 2, ch / 2)
  const tex = new THREE.CanvasTexture(canvas)
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(cw * 0.1, ch * 0.1, 1)
  return sprite
}

export function StarMapCanvas() {
  const containerRef = useRef<HTMLDivElement>(null)
  const { categories } = useCategoriesStore()
  const { notes, starMapFilter, openNote, setTab } = useNotesStore()
  const [tooltip, setTooltip] = useState<Tooltip | null>(null)
  const [tagNoteIds, setTagNoteIds] = useState<Set<string> | null>(null)

  // 태그 필터일 때는 해당 태그가 붙은 노트 id 집합을 먼저 가져와야
  // 아래 씬 구성 effect에서 필터링에 쓸 수 있다 (은하를 넘나드는 필터라
  // 카테고리처럼 동기적으로 계산할 수 없음).
  useEffect(() => {
    if (starMapFilter?.type !== 'tag') { setTagNoteIds(null); return }
    let alive = true
    tagsApi.notesForTag(starMapFilter.value).then(list => {
      if (alive) setTagNoteIds(new Set(list.map(n => n.id)))
    })
    return () => { alive = false }
  }, [starMapFilter])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const width = el.clientWidth || 800
    const height = el.clientHeight || 600
    const disposables: { dispose: () => void }[] = []

    // 표시 대상 필터링 — 카테고리 필터는 은하 하나로 좁히고, 태그 필터는
    // 은하를 그대로 둔 채(태그는 여러 은하에 걸칠 수 있음) 노트만 좁힌다.
    const visibleNotes = !starMapFilter
      ? notes
      : starMapFilter.type === 'category'
        ? notes.filter(n => n.category_id === starMapFilter.value)
        : notes.filter(n => tagNoteIds?.has(n.id) ?? false)
    const visibleCats = starMapFilter?.type === 'category'
      ? categories.filter(c => c.id === starMapFilter.value)
      : categories

    // 은하 간 간격이 보장되도록 항성 위치를 동적으로 계산 (필터와 무관하게
    // 전체 카테고리 기준으로 계산해 위치가 흔들리지 않게 유지)
    const noteCounts = categories.map(c => notes.filter(n => n.category_id === c.id).length)
    const starPositions = computeStarPositions(noteCounts)

    // ── Scene ────────────────────────────────────────────────
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x02030a)
    scene.fog = new THREE.FogExp2(0x02030a, 0.00004)

    // 카메라 초점: 전체 뷰는 모든 은하의 중심점(특정 은하에 치우치지 않게)
    let lookTarget = new THREE.Vector3(0, 0, 0)
    if (starPositions.length > 0) {
      starPositions.forEach(p => lookTarget.add(p))
      lookTarget.divideScalar(starPositions.length)
    }
    let initCamR = Math.max(
      4000,
      starPositions.reduce(
        (m, p, i) => Math.max(m, p.distanceTo(lookTarget) + systemRadius(noteCounts[i])),
        0,
      ) * 1.7,
    )
    if (starMapFilter?.type === 'category') {
      const ci = categories.findIndex(c => c.id === starMapFilter.value)
      if (ci >= 0) {
        // 선택한 은하계를 화면 중앙에 두고, 은하 전체가 들어오도록 거리 조정
        lookTarget = starPositions[ci].clone()
        initCamR = Math.max(2000, systemRadius(noteCounts[ci]) * 2.4)
      } else {
        initCamR = 2200
      }
    }
    const maxZoom = Math.max(12000, initCamR * 2)

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 250000)
    camera.position.set(lookTarget.x, lookTarget.y + 800, lookTarget.z + initCamR)
    camera.lookAt(lookTarget)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.15
    el.appendChild(renderer.domElement)
    renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;cursor:grab;'

    // ── 포스트프로세싱 (블룸) ────────────────────────────────
    const composer = new EffectComposer(renderer)
    composer.addPass(new RenderPass(scene, camera))
    const bloom = new UnrealBloomPass(
      new THREE.Vector2(width / 2, height / 2), // 절반 해상도
      0.85,  // strength
      0.6,   // radius
      0.78,  // threshold — 항성/밝은 별만 빛나게
    )
    composer.addPass(bloom)

    const starTex = makeStarSpriteTexture()
    disposables.push(starTex)

    // ── 조명 ─────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0x202a4a, 0.55))
    const mainLight = new THREE.DirectionalLight(0xfff4e8, 1.6)
    mainLight.position.set(200, 180, 100)
    scene.add(mainLight)
    const fillLight = new THREE.DirectionalLight(0x3344aa, 0.4)
    fillLight.position.set(-200, -100, -150)
    scene.add(fillLight)

    // ── 성운 배경 ────────────────────────────────────────────
    const nebulaSpecs: [number, number, number, THREE.Vector3, number][] = [
      [108, 70, 196, new THREE.Vector3(-900, 300, -1600), 2200],
      [40, 150, 170, new THREE.Vector3(1100, -400, -1400), 2000],
      [196, 70, 140, new THREE.Vector3(300, 700, -1900), 1700],
      [60, 90, 200, new THREE.Vector3(-400, -600, -2100), 2400],
      [170, 120, 60, new THREE.Vector3(1500, 500, -2300), 1900],
    ]
    nebulaSpecs.forEach(([r, g, b, pos, sc]) => {
      const tex = makeNebulaTexture(r, g, b)
      disposables.push(tex)
      const mat = new THREE.SpriteMaterial({
        map: tex, transparent: true, opacity: 0.12,
        depthWrite: false, blending: THREE.AdditiveBlending,
      })
      const spr = new THREE.Sprite(mat)
      spr.position.copy(pos.clone().multiplyScalar(10))
      spr.scale.setScalar(sc * 10)
      scene.add(spr)
    })

    // ── 별하늘 (색·크기 다양 + 밝은 별 레이어) ────────────────
    // 은하들이 카테고리 수에 따라 원점에서 멀리 흩어질 수 있어(computeStarPositions),
    // 별 배경을 원점 기준 고정 큐브로 두면 원점에서 먼 은하를 보는 중엔 배경이
    // 텅 비어 보인다 — 지금 카메라가 바라보는 lookTarget을 중심으로 생성해
    // 어떤 은하를 보든 주위에 별이 둘러싸도록 한다.
    function buildStars(count: number, spread: number, size: number, opacity: number, bright: boolean) {
      const pos = new Float32Array(count * 3)
      const col = new Float32Array(count * 3)
      const tint = new THREE.Color()
      for (let i = 0; i < count; i++) {
        // 구면 좌표로 뽑아서 둥글게 퍼지게 한다 — x/y/z를 각각 독립으로 뽑으면
        // 정육면체 모양 경계가 그대로 드러난다(예전엔 fog·감쇠가 가려줬지만
        // 지금은 배경별에 그 둘을 껐으므로 각진 경계가 눈에 보인다).
        const rad = (spread / 2) * Math.cbrt(Math.random())
        const theta = Math.random() * Math.PI * 2
        const phi = Math.acos(Math.random() * 2 - 1)
        pos[i * 3] = lookTarget.x + rad * Math.sin(phi) * Math.cos(theta)
        pos[i * 3 + 1] = lookTarget.y + rad * Math.sin(phi) * Math.sin(theta)
        pos[i * 3 + 2] = lookTarget.z + rad * Math.cos(phi)
        const r = Math.random()
        if (r < 0.7) tint.setRGB(1, 1, 1)                   // 백색
        else if (r < 0.85) tint.setRGB(0.7, 0.8, 1)         // 청백색
        else if (r < 0.95) tint.setRGB(1, 0.92, 0.7)        // 황색
        else tint.setRGB(1, 0.72, 0.6)                      // 적색
        const v = bright ? 1 : 0.6 + Math.random() * 0.4
        col[i * 3] = tint.r * v
        col[i * 3 + 1] = tint.g * v
        col[i * 3 + 2] = tint.b * v
      }
      const baseCol = col.slice() // 반짝임 배율을 곱할 원본 밝기 (매 프레임 여기서부터 다시 계산)
      // 별마다 다른 위상·주기를 줘서 다 같이 반짝이지 않고 제각각 가끔 반짝이게 한다
      const twinklePhase = new Float32Array(count)
      const twinkleSpeed = new Float32Array(count)
      for (let i = 0; i < count; i++) {
        twinklePhase[i] = Math.random() * Math.PI * 2
        twinkleSpeed[i] = 1.5 + Math.random() * 2.5
      }
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      const colorAttr = new THREE.BufferAttribute(col, 3)
      geo.setAttribute('color', colorAttr)
      const mat = new THREE.PointsMaterial({
        // 배경별은 우주의 무한히 먼 배경이라는 개념이라 카메라 거리와
        // 무관하게 항상 같은 화면상 크기·밝기여야 한다. sizeAttenuation을
        // 켜두면 줌아웃해서 카메라~별 거리가 멀어질수록 점이 서브픽셀로
        // 작아지고, fog를 켜두면 같은 이유로 안개에 완전히 가려져 축소했을
        // 때만 배경별이 사라지는 문제가 있었다.
        size, sizeAttenuation: false, vertexColors: true,
        map: starTex, transparent: true, opacity,
        depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
      })
      const pts = new THREE.Points(geo, mat)
      scene.add(pts)
      return { mat, col, baseCol, colorAttr, twinklePhase, twinkleSpeed, count }
    }
    const starLayer = buildStars(1800, 150000, 0.8, 0.75, false)
    const brightStarLayer = buildStars(100, 140000, 1.6, 0.95, true)

    // 별 반짝임: 대부분은 기본 밝기 근처에 머물다가 가끔 순간적으로 밝기가
    // 튀는 느낌을 내려고 sin을 높은 지수로 눌러(sin^6) 스파이크를 좁고
    // 뜸하게 만든다. 별마다 위상·속도가 달라 한꺼번에 반짝이지 않는다.
    function updateTwinkle(layer: typeof starLayer, t: number) {
      const { col, baseCol, colorAttr, twinklePhase, twinkleSpeed, count } = layer
      for (let i = 0; i < count; i++) {
        const s = Math.max(0, Math.sin(t * twinkleSpeed[i] + twinklePhase[i]))
        const twinkle = 1 + Math.pow(s, 6) * 2.2
        col[i * 3] = baseCol[i * 3] * twinkle
        col[i * 3 + 1] = baseCol[i * 3 + 1] * twinkle
        col[i * 3 + 2] = baseCol[i * 3 + 2] * twinkle
      }
      colorAttr.needsUpdate = true
    }

    // ── 은하수 밴드: 기울어진 원환에 밀집된 파티클 띠 ────────
    function buildMilkyWay() {
      const count = 3000
      const pos = new Float32Array(count * 3)
      const col = new Float32Array(count * 3)
      const euler = new THREE.Euler(0.5, 0, 0.35)
      const v = new THREE.Vector3()
      for (let i = 0; i < count; i++) {
        const a = Math.random() * Math.PI * 2
        const r = (1500 + (Math.random() - 0.5) * 700) * 10
        const spread = Math.pow(Math.random(), 2) * 2600 * (Math.random() < 0.5 ? 1 : -1)
        v.set(Math.cos(a) * r, spread, Math.sin(a) * r).applyEuler(euler)
        pos[i * 3] = v.x; pos[i * 3 + 1] = v.y; pos[i * 3 + 2] = v.z
        const w = 0.45 + Math.random() * 0.55
        col[i * 3] = 0.82 * w; col[i * 3 + 1] = 0.86 * w; col[i * 3 + 2] = w
      }
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
      const mat = new THREE.PointsMaterial({
        // 배경별과 달리 은하수 밴드는 원점에 고정된 국지적 장식이라, fog를
        // 꺼두면 어느 은하를 보든 늘 또렷한 고리 하나가 떠 있는 것처럼
        // 보인다(마치 운석 띠처럼). 가까이 있을 때만 은은히 보이도록 안개는
        // 다시 켠다.
        size: 1.4, sizeAttenuation: false, vertexColors: true, map: starTex,
        transparent: true, opacity: 0.35, depthWrite: false,
        blending: THREE.AdditiveBlending, fog: true,
      })
      scene.add(new THREE.Points(geo, mat))
    }
    buildMilkyWay()

    // ── 항성 주위 나선팔 성간먼지 ────────────────────────────
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
        pos[i * 3 + 1] = center.y + (Math.random() - 0.5) * 60
        pos[i * 3 + 2] = center.z + Math.sin(a) * r
        tmp.copy(color).lerp(white, t * 0.6)
        col[i * 3] = tmp.r; col[i * 3 + 1] = tmp.g; col[i * 3 + 2] = tmp.b
      }
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
      const mat = new THREE.PointsMaterial({
        size: 1.0, sizeAttenuation: false, vertexColors: true, map: starTex,
        transparent: true, opacity: 0.3, depthWrite: false,
        blending: THREE.AdditiveBlending, fog: false,
      })
      scene.add(new THREE.Points(geo, mat))
    }

    // ── 항성 (카테고리) ──────────────────────────────────────
    const glowTex = makeGlowTexture()
    disposables.push(glowTex)
    const sunDatas: SunData[] = []
    const sunMaterials: THREE.ShaderMaterial[] = []

    visibleCats.forEach(cat => {
      const ci = categories.findIndex(c => c.id === cat.id)
      const pos = starPositions[ci]
      const color = new THREE.Color(cat.color)
      const noteCount = visibleNotes.filter(n => n.category_id === cat.id).length

      const sunR = 500.0

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

      const innerGlow = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTex, color,
        transparent: true, opacity: 0.9,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      innerGlow.scale.setScalar(sunR * 5.5)
      sunMesh.add(innerGlow)

      const coronaGlowScale = sunR * 12
      const coronaGlow = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTex, color,
        transparent: true, opacity: 0.28,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      coronaGlow.scale.setScalar(coronaGlowScale)
      sunMesh.add(coronaGlow)

      const label = makeLabelSprite(cat.name, color)
      label.position.set(0, sunR + 6, 0)
      sunMesh.add(label)

      const nebulaR = Math.max(55, 30 + noteCount * 9)
      const nebula = new THREE.Mesh(
        new THREE.SphereGeometry(nebulaR, 18, 18),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.04, side: THREE.BackSide }),
      )
      nebula.position.copy(pos)
      scene.add(nebula)

      scene.add(sunMesh)
      sunDatas.push({ mesh: sunMesh, glow: coronaGlow, glowBase: coronaGlowScale, phase: Math.random() * Math.PI * 2 })
      buildSpiralDust(pos, color, systemRadius(noteCount))
    })

    // ── 노트 행성 (절차적 표면 텍스처) ───────────────────────
    const texCache = new Map<string, THREE.Texture>()
    const getTex = (kind: PlanetKind) => {
      let t = texCache.get(kind.name)
      if (!t) { t = makePlanetTexture(kind); texCache.set(kind.name, t); disposables.push(t) }
      return t
    }
    const ringTex = makeRingTexture()
    disposables.push(ringTex)

    const starMeshes: THREE.Mesh[] = []
    const orbits: OrbitData[] = []
    const noteIds: string[] = []
    const spinners: THREE.Object3D[] = []
    // 행성이 멀리서 1px 미만으로 작아져 안 보이는 문제 방지용 —
    // starMeshes/spinners/orbits와 같은 인덱스로 쌓아 애니메이션 루프에서
    // 위치를 같이 갱신하는 화면상 고정 크기 점 마커의 색상 버퍼
    const markerColors: number[] = []

    // 카테고리별로 노트를 묶어 같은 평면에서 동심원 궤도(태양계 형태)로 배치
    let kindCounter = 0
    visibleCats.forEach(cat => {
      const ci = categories.findIndex(c => c.id === cat.id)
      const center = starPositions[ci].clone()
      const catColor = new THREE.Color(cat.color)
      const catNotes = visibleNotes.filter(n => n.category_id === cat.id).slice(0, 800)
      if (catNotes.length === 0) return

      const sunR = 500.0

      // 이 항성계의 황도면(카테고리마다 다른 기울기로 전체가 평평해지지 않게)
      const tiltX = 0.12 + (ci % 4) * 0.14
      const tiltY = ci * 0.6
      const planeM = new THREE.Matrix4().makeRotationFromEuler(
        new THREE.Euler(tiltX, tiltY, 0),
      )
      const e1 = new THREE.Vector3(1, 0, 0).applyMatrix4(planeM)
      const e2 = new THREE.Vector3(0, 0, 1).applyMatrix4(planeM)

      catNotes.forEach((note, j) => {
        const kind = PLANET_KINDS[kindCounter % PLANET_KINDS.length]
        kindCounter++
        const planetR = kind.size

        // 행성 본체: 텍스처 + 표준 재질(태양광 방향으로 낮/밤 위상)
        const mesh = new THREE.Mesh(
          new THREE.SphereGeometry(planetR, 28, 20),
          new THREE.MeshStandardMaterial({
            map: getTex(kind),
            roughness: 0.92,
            metalness: 0.0,
            emissive: catColor.clone().multiplyScalar(0.06),
          }),
        )
        mesh.rotation.z = (j % 5) * 0.12 - 0.2 // 자전축 기울기

        // 고리 구성: 금성같은 고리가 있는 행성은 글의 내용이 1000줄 넘어가면 생겨야한다 2000줄이면 고리가 2줄
        const lineCount = note.content ? note.content.split('\n').length : 0
        const isVenus = kind.name === 'venus'
        const hasDefaultRing = !!kind.ring
        const ringsToRender: { inner: number, outer: number, opacity: number, rotationX: number }[] = []

        if (hasDefaultRing) {
          const rInner = planetR * 1.4
          const rOuter = planetR * (kind.ring === 'saturn' ? 2.3 : 1.9)
          ringsToRender.push({
            inner: rInner,
            outer: rOuter,
            opacity: kind.ring === 'saturn' ? 0.9 : 0.5,
            rotationX: kind.ring === 'saturn' ? Math.PI / 2 - 0.45 : 0.25
          })
        } else if (isVenus) {
          if (lineCount >= 2000) {
            ringsToRender.push({
              inner: planetR * 1.4,
              outer: planetR * 1.75,
              opacity: 0.8,
              rotationX: 0.25
            })
            ringsToRender.push({
              inner: planetR * 1.85,
              outer: planetR * 2.2,
              opacity: 0.6,
              rotationX: 0.25
            })
          } else if (lineCount >= 1000) {
            ringsToRender.push({
              inner: planetR * 1.4,
              outer: planetR * 1.9,
              opacity: 0.7,
              rotationX: 0.25
            })
          }
        }

        ringsToRender.forEach(rInfo => {
          const ring = new THREE.Mesh(
            makeRingGeometry(rInfo.inner, rInfo.outer),
            new THREE.MeshBasicMaterial({
              map: ringTex, transparent: true,
              opacity: rInfo.opacity,
              side: THREE.DoubleSide, depthWrite: false,
            }),
          )
          ring.rotation.x = rInfo.rotationX
          mesh.add(ring)
        })

        // 위성 구성 (첨부파일이나 링크가 있는 노트)
        const hasAttachmentOrLink = note.content && (
          /!?\[.*?\]\(.*?\)/.test(note.content) ||
          /https?:\/\//.test(note.content)
        )
        if (hasAttachmentOrLink) {
          const satGroup = new THREE.Group()
          mesh.add(satGroup)

          const satR = planetR * 0.22
          const satMat = new THREE.MeshStandardMaterial({
            color: new THREE.Color('#cbd5e1'), // slate-300
            roughness: 0.95,
            metalness: 0.05,
          })
          const satMesh = new THREE.Mesh(
            new THREE.SphereGeometry(satR, 12, 10),
            satMat
          )

          const hasRings = ringsToRender.length > 0
          const orbitRadius = planetR * (hasRings ? 2.5 : 1.7)
          satMesh.position.set(orbitRadius, planetR * 0.3, 0)
          satGroup.add(satMesh)
          mesh.userData.satelliteGroup = satGroup
        }

        // 프레넬 대기 셸 (카테고리 색 가장자리 산란 — 소속 단서)
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

        mesh.userData.categoryColor = catColor.clone()

        // 피보나치 로그 나선형 배치 (Accretion Disc): 궤도 간격은 바깥으로 갈수록 불규칙하게 벌어진다
        const radius = orbitRadius(sunR, j)
        const angle = (j * 2.399963) % (Math.PI * 2) // 황금각 분산

        // 노트 본문 크기(줄 수)에 따라 공전 및 자전 속도 다변화
        let speedMultiplier = 1.0
        let selfRotY = 0.005 + (j % 4) * 0.0025

        if (lineCount >= 2000) {
          speedMultiplier = 0.4  // 거대하고 무거운 행성은 느리고 중후하게 공전
          selfRotY = 0.024       // 목성/토성처럼 가스 거인으로서의 엄청나게 빠른 자전 속도
        } else if (lineCount >= 1000) {
          speedMultiplier = 0.7  // 1000줄 이상의 무거운 행성은 일반 행성보다 살짝 느리게 공전
          selfRotY = 0.015       // 빠른 자전 속도
        }

        const speed = (1.1 / Math.pow(radius / 10, 1.5)) * speedMultiplier

        const p = center.clone()
          .addScaledVector(e1, radius * Math.cos(angle))
          .addScaledVector(e2, radius * Math.sin(angle))
        mesh.position.copy(p)

        // 각 행성마다 고유의 희미한 공전 궤도 선을 그린다
        {
          const segs = 96
          const orbitPts: number[] = []
          for (let s = 0; s <= segs; s++) {
            const a = (s / segs) * Math.PI * 2
            const op = center.clone()
              .addScaledVector(e1, radius * Math.cos(a))
              .addScaledVector(e2, radius * Math.sin(a))
            orbitPts.push(op.x, op.y, op.z)
          }
          const orbitGeo = new THREE.BufferGeometry()
          orbitGeo.setAttribute('position', new THREE.Float32BufferAttribute(orbitPts, 3))
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
          scene.add(orbitLine)
        }

        scene.add(mesh)
        starMeshes.push(mesh)
        spinners.push(mesh)
        orbits.push({
          center, radius, e1, e2, angle, speed, selfRotY,
        })
        noteIds.push(note.id)
        markerColors.push(catColor.r, catColor.g, catColor.b)
      })
    })

    // 미분류 노트(Rogue Planets) 배치: 은하계에 소속되지 않고 우주 공간에 자유롭게 떠돌아다님
    const uncategorizedNotes = visibleNotes.filter(n => !n.category_id)
    if (uncategorizedNotes.length > 0) {
      const neutralColor = new THREE.Color('#94a3b8') // 성운 빛깔의 회백색 중립 색상

      uncategorizedNotes.forEach((note, j) => {
        const kind = PLANET_KINDS[kindCounter % PLANET_KINDS.length]
        kindCounter++
        // 미분류 행성 크기 축소 (기존 크기의 0.4배)
        const planetR = kind.size * 0.4

        // 행성 본체: 텍스처 + 표준 재질
        const mesh = new THREE.Mesh(
          new THREE.SphereGeometry(planetR, 28, 20),
          new THREE.MeshStandardMaterial({
            map: getTex(kind),
            roughness: 0.92,
            metalness: 0.0,
          }),
        )
        mesh.rotation.z = (j % 5) * 0.12 - 0.2

        // 고리 구성: 금성같은 고리가 있는 행성은 글의 내용이 1000줄 넘어가면 생겨야한다 2000줄이면 고리가 2줄
        const lineCount = note.content ? note.content.split('\n').length : 0
        const isVenus = kind.name === 'venus'
        const hasDefaultRing = !!kind.ring
        const ringsToRender: { inner: number, outer: number, opacity: number, rotationX: number }[] = []

        if (hasDefaultRing) {
          const rInner = planetR * 1.4
          const rOuter = planetR * (kind.ring === 'saturn' ? 2.3 : 1.9)
          ringsToRender.push({
            inner: rInner,
            outer: rOuter,
            opacity: kind.ring === 'saturn' ? 0.9 : 0.5,
            rotationX: kind.ring === 'saturn' ? Math.PI / 2 - 0.45 : 0.25
          })
        } else if (isVenus) {
          if (lineCount >= 2000) {
            ringsToRender.push({
              inner: planetR * 1.4,
              outer: planetR * 1.75,
              opacity: 0.8,
              rotationX: 0.25
            })
            ringsToRender.push({
              inner: planetR * 1.85,
              outer: planetR * 2.2,
              opacity: 0.6,
              rotationX: 0.25
            })
          } else if (lineCount >= 1000) {
            ringsToRender.push({
              inner: planetR * 1.4,
              outer: planetR * 1.9,
              opacity: 0.7,
              rotationX: 0.25
            })
          }
        }

        ringsToRender.forEach(rInfo => {
          const ring = new THREE.Mesh(
            makeRingGeometry(rInfo.inner, rInfo.outer),
            new THREE.MeshBasicMaterial({
              map: ringTex, transparent: true,
              opacity: rInfo.opacity,
              side: THREE.DoubleSide, depthWrite: false,
            }),
          )
          ring.rotation.x = rInfo.rotationX
          mesh.add(ring)
        })

        // 위성 구성 (첨부파일이나 링크가 있는 노트)
        const hasAttachmentOrLink = note.content && (
          /!?\[.*?\]\(.*?\)/.test(note.content) ||
          /https?:\/\//.test(note.content)
        )
        if (hasAttachmentOrLink) {
          const satGroup = new THREE.Group()
          mesh.add(satGroup)

          const satR = planetR * 0.22
          const satMat = new THREE.MeshStandardMaterial({
            color: new THREE.Color('#e2e8f0'), // slate-200 (미분류 행성은 살짝 더 밝은 위성)
            roughness: 0.95,
            metalness: 0.05,
          })
          const satMesh = new THREE.Mesh(
            new THREE.SphereGeometry(satR, 12, 10),
            satMat
          )

          const hasRings = ringsToRender.length > 0
          const orbitRadius = planetR * (hasRings ? 2.5 : 1.7)
          satMesh.position.set(orbitRadius, planetR * 0.3, 0)
          satGroup.add(satMesh)
          mesh.userData.satelliteGroup = satGroup
        }

        mesh.userData.categoryColor = neutralColor.clone()

        // 각 노트의 ID 해시를 바탕으로 고유한 우주 공간 3D 좌표 배치
        let h1 = 0, h2 = 0, h3 = 0
        const idStr = note.id
        for (let i = 0; i < idStr.length; i++) {
          const char = idStr.charCodeAt(i)
          h1 = (h1 * 31 + char) % 1000
          h2 = (h2 * 37 + char) % 1000
          h3 = (h3 * 41 + char) % 1000
        }

        // 반경 2400~6000 사이의 임의 구면 좌표
        const theta = (h1 / 1000) * Math.PI * 2
        const phi = Math.acos((h2 / 1000) * 2 - 1)
        const r = (240 + (h3 / 1000) * 360) * 10

        const roguePos = new THREE.Vector3(
          r * Math.sin(phi) * Math.cos(theta),
          (h2 - 500) * 0.35 * 10,
          r * Math.cos(phi)
        )

        mesh.position.copy(roguePos)
        scene.add(mesh)
        starMeshes.push(mesh)
        spinners.push(mesh)

        // 공전이 없으므로 radius=0, speed=0. 실제 우주 물리학(인력, 충돌) 적용을 위해 추가 필드 기록
        orbits.push({
          center: roguePos.clone(),
          radius: 0,
          e1: new THREE.Vector3(0, 0, 0),
          e2: new THREE.Vector3(0, 0, 0),
          angle: 0,
          speed: 0,
          selfRotY: 0.003 + (j % 4) * 0.003,
          isRogue: true,
          velocity: new THREE.Vector3(
            (Math.random() - 0.5) * 4.0,
            (Math.random() - 0.5) * 1.0,
            (Math.random() - 0.5) * 4.0
          ),
          mass: planetR * 10,
          planetR: planetR,
        })
        noteIds.push(note.id)
        markerColors.push(neutralColor.r, neutralColor.g, neutralColor.b)
      })
    }

    // ── 행성 위치 마커 (화면상 고정 크기 점) ──────────────────
    // 노트가 많은 은하는 전체를 담기 위해 카메라가 멀어지므로 3D 구체만으로는
    // 행성이 1px 미만으로 작아져 사실상 안 보인다. sizeAttenuation:false로
    // 거리와 무관하게 항상 화면상 일정 크기로 찍히는 점을 각 행성 위치에 겹쳐
    // 그려, 멀리서는 별처럼 보이고 가까이서는 실제 3D 행성이 보이게 한다.


    // ── 항로 (발견된 노트 연결) ──────────────────────────────
    const routeVisuals: RouteVisual[] = []
    const shipMeshes: THREE.Mesh[] = []
    // 콘의 뾰족한 끝을 +Z로 맞춰, 이동 방향(tangent) 벡터와
    // quaternion.setFromUnitVectors로 직접 정렬한다(lookAt은 카메라가 아닌
    // 일반 Mesh에서는 방향이 반대로 적용되는 특성이 있어 사용하지 않는다).
    const shipGeometry = new THREE.ConeGeometry(6, 22, 6)
    shipGeometry.rotateX(Math.PI / 2)

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

        // 항로의 색상(카테고리 연결 색상)에 맞춰 스스로 발광하는 가벼운 베이직 재질 개별 적용
        const shipMat = new THREE.MeshBasicMaterial({
          color: lineColor,
          transparent: true,
          opacity: 0.85,
          blending: THREE.AdditiveBlending,
        })
        const ship = new THREE.Mesh(shipGeometry, shipMat)
        ship.userData.shared = route.shared_entities
        scene.add(ship)
        shipMeshes.push(ship)

        routeVisuals.push({ aIdx, bIdx, line, ship, t: Math.random(), dir: 1 })
      })
    }).catch(err => {
      console.error('discovery routes 로드 실패:', err)
    })

    // ── 카메라 컨트롤 ────────────────────────────────────────
    let theta = 0.2
    let phi = 1.1
    let camR = initCamR
    let pointerDown = false
    let lastMouse = { x: 0, y: 0 }
    let moved = false

    function updateCamera() {
      camera.position.set(
        lookTarget.x + camR * Math.sin(phi) * Math.sin(theta),
        lookTarget.y + camR * Math.cos(phi),
        lookTarget.z + camR * Math.sin(phi) * Math.cos(theta),
      )
      camera.lookAt(lookTarget)
    }
    updateCamera()

    const canvas = renderer.domElement
    const raycaster = new THREE.Raycaster()

    function getHit(e: MouseEvent | PointerEvent) {
      const rect = canvas.getBoundingClientRect()
      const x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      const y = -((e.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(new THREE.Vector2(x, y), camera)
      const hits = raycaster.intersectObjects([...starMeshes, ...shipMeshes], false)
      return { hit: hits[0]?.object as THREE.Mesh | undefined, rect }
    }

    canvas.addEventListener('pointerdown', (e) => {
      pointerDown = true
      moved = false
      lastMouse = { x: e.clientX, y: e.clientY }
      canvas.setPointerCapture(e.pointerId)
      canvas.style.cursor = 'grabbing'
    })

    canvas.addEventListener('pointermove', (e) => {
      if (pointerDown) {
        const dx = e.clientX - lastMouse.x
        const dy = e.clientY - lastMouse.y
        if (Math.abs(dx) > 2 || Math.abs(dy) > 2) moved = true
        if (e.ctrlKey) {
          // Ctrl+드래그: 중심점(lookTarget) 이동 — 화면 기준 좌우/상하 팬
          const right = new THREE.Vector3(1, 0, 0).transformDirection(camera.matrixWorld)
          const up = new THREE.Vector3(0, 1, 0).transformDirection(camera.matrixWorld)
          const panSpeed = camR * 0.0015
          lookTarget.addScaledVector(right, -dx * panSpeed)
          lookTarget.addScaledVector(up, dy * panSpeed)
        } else {
          theta -= dx * 0.006
          phi = Math.max(0.12, Math.min(Math.PI - 0.12, phi + dy * 0.006))
        }
        lastMouse = { x: e.clientX, y: e.clientY }
        updateCamera()
        setTooltip(null)
        return
      }
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
    })

    canvas.addEventListener('pointerup', (e) => {
      pointerDown = false
      canvas.style.cursor = 'grab'
      if (!moved) {
        const { hit } = getHit(e)
        if (hit) {
          const idx = starMeshes.indexOf(hit)
          if (idx >= 0) openNote(noteIds[idx]).then(() => setTab('edit'))
        }
      }
    })

    canvas.addEventListener('pointerleave', () => setTooltip(null))

    canvas.addEventListener('wheel', (e) => {
      e.preventDefault()
      camR = Math.max(400, Math.min(maxZoom, camR + e.deltaY * 5.0))
      updateCamera()
    }, { passive: false })

    // ── 애니메이션 ───────────────────────────────────────────
    let animId: number
    function animate() {
      animId = requestAnimationFrame(animate)
      const t = Date.now() * 0.0012

      // 배경별 반짝임 (별마다 제각각 가끔 밝기가 튐)
      updateTwinkle(starLayer, t)
      updateTwinkle(brightStarLayer, t)

      sunDatas.forEach(s => {
        s.mesh.rotation.y += 0.003
        if (s.glow && s.glowBase !== undefined) {
          const pulse = 1 + Math.sin(t + s.phase) * 0.1
          s.glow.scale.setScalar(s.glowBase * pulse)
        }
      })
      sunMaterials.forEach(m => { m.uniforms.uTime.value += 0.016 })

      // 미분류 행성(Rogue Planets)들의 중력 인력 및 충돌 처리
      const rogueIndices: number[] = []
      orbits.forEach((od, idx) => {
        if (od.isRogue) {
          rogueIndices.push(idx)
        }
      })

      const physicsDt = 1.0
      const G_constant = 0.005 // 중력 상수를 크게 낮추어 부드럽고 느린 인력 유도
      const softSq = 150.0 // 거리가 매우 가까워질 때 중력이 급증하지 않도록 완충
      const centerGravity = 0.001 // 은하 중심 복원 강도
      const maxSpeed = 8.0 // 행성의 최대 이동 속도를 제한하여 수치적 폭발(빅뱅) 방지
      const dragFactor = 0.96 // 드래그(저항)를 도입하여 점진적으로 에너지를 분산하고 궤도 안정화

      // 1. 중력 계산 (만유인력 적용)
      for (let i = 0; i < rogueIndices.length; i++) {
        const idxA = rogueIndices[i]
        const odA = orbits[idxA]
        const posA = odA.center
        const velA = odA.velocity!
        const massA = odA.mass || 1

        // 속도 감쇄 (마찰/에너지 소실 모사)
        velA.multiplyScalar(dragFactor)

        // 은하 중심 방향 복원력 (일정 반경 4500 이상 벗어났을 때만 안쪽으로 유도)
        const distToCenter = posA.length()
        if (distToCenter > 4500.0) {
          const centerPull = posA.clone().normalize().multiplyScalar(-centerGravity * (distToCenter - 4500.0))
          velA.add(centerPull)
        }

        // 태양 안쪽/중심부로 들어오지 못하도록 척력 및 속도 반사 적용
        if (distToCenter < 2400.0 && distToCenter > 0.01) {
          const normal = posA.clone().normalize()
          // 중심부(태양)로부터 밀어내는 척력
          const pushStrength = (2400.0 - distToCenter) * 0.01
          velA.addScaledVector(normal, pushStrength)

          // 안쪽으로 향하는 속도가 있다면 튕겨냄 (반사)
          const dot = velA.dot(normal)
          if (dot < 0) {
            velA.addScaledVector(normal, -dot * 1.2)
          }

          // 강제 위치 보정 최소 안전선 (태양 크기 130 고려하여 2000 이하로 가지 못하게 방지)
          if (distToCenter < 2000.0) {
            posA.setLength(2000.0)
          }
        }

        // 행성 상호 간 만유인력
        for (let j = i + 1; j < rogueIndices.length; j++) {
          const idxB = rogueIndices[j]
          const odB = orbits[idxB]
          const posB = odB.center
          const velB = odB.velocity!
          const massB = odB.mass || 1

          const dir = new THREE.Vector3().subVectors(posB, posA)
          const distSq = dir.lengthSq()
          const dist = Math.sqrt(distSq)

          if (dist > 0.1) {
            const forceMag = (G_constant * massA * massB) / (distSq + softSq)
            const dirNorm = dir.clone().normalize()

            velA.addScaledVector(dirNorm, (forceMag / massA) * physicsDt)
            velB.addScaledVector(dirNorm, -(forceMag / massB) * physicsDt)
          }
        }
      }

      // 2. 충돌 감지 및 물리적 충돌 응답 (탄성 충돌)
      for (let i = 0; i < rogueIndices.length; i++) {
        const idxA = rogueIndices[i]
        const odA = orbits[idxA]
        const posA = odA.center
        const velA = odA.velocity!
        const rA = odA.planetR || 1.5
        const massA = odA.mass || 1

        for (let j = i + 1; j < rogueIndices.length; j++) {
          const idxB = rogueIndices[j]
          const odB = orbits[idxB]
          const posB = odB.center
          const velB = odB.velocity!
          const rB = odB.planetR || 1.5
          const massB = odB.mass || 1

          const dir = new THREE.Vector3().subVectors(posB, posA)
          const dist = dir.length()
          const minDist = rA + rB

          if (dist < minDist) {
            const overlap = minDist - dist
            const dirNorm = dist > 0.01 ? dir.clone().normalize() : new THREE.Vector3(1, 0, 0)

            // 중첩 상태 강제 분리 (위치 보정 - 밀어내는 힘을 0.5배 완화하여 충격 최소화)
            const totalMass = massA + massB
            const ratioA = massB / totalMass
            const ratioB = massA / totalMass
            posA.addScaledVector(dirNorm, -overlap * ratioA * 0.5)
            posB.addScaledVector(dirNorm, overlap * ratioB * 0.5)

            // 탄성 충돌 속도 변화 계산
            const relVel = new THREE.Vector3().subVectors(velB, velA)
            const velAlongNormal = relVel.dot(dirNorm)

            if (velAlongNormal < 0) {
              const restitution = 0.3 // 반반력을 낮추어 부드러운 튕김 유도
              const impulseScalar = -(1 + restitution) * velAlongNormal / (1 / massA + 1 / massB)

              velA.addScaledVector(dirNorm, -impulseScalar / massA)
              velB.addScaledVector(dirNorm, impulseScalar / massB)
            }
          }
        }

        // 각 행성의 물리 속도 상한선(Velocity Cap) 적용
        const speed = velA.length()
        if (speed > maxSpeed) {
          velA.setLength(maxSpeed)
        }
      }

      // 3. 전체 행성들 위치 갱신
      spinners.forEach((mesh, i) => {
        const od = orbits[i]
        if (od.isRogue) {
          // 미분류 행성은 누적된 속도로 위치 이동
          od.center.addScaledVector(od.velocity!, physicsDt)
          mesh.position.copy(od.center)
          mesh.rotation.y += od.selfRotY
        } else {
          // 일반 카테고리 행성들은 공전 궤도식 적용
          od.angle += od.speed
          mesh.position.copy(od.center)
            .addScaledVector(od.e1, od.radius * Math.cos(od.angle))
            .addScaledVector(od.e2, od.radius * Math.sin(od.angle))
          mesh.rotation.y += od.selfRotY
        }

        // 위성 공전 애니메이션
        const satGroup = mesh.userData.satelliteGroup as THREE.Group | undefined
        if (satGroup) {
          satGroup.rotation.y += 0.012 + (i % 3) * 0.004
        }
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
    }
    animate()

    const obs = new ResizeObserver(() => {
      const w = el.clientWidth
      const h = el.clientHeight
      renderer.setSize(w, h)
      composer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    })
    obs.observe(el)

    return () => {
      routesCancelled = true
      cancelAnimationFrame(animId)
      obs.disconnect()
      disposables.forEach(d => d.dispose())
      scene.traverse(obj => {
        const mesh = obj as THREE.Mesh
        mesh.geometry?.dispose()
        const material = mesh.material
        if (Array.isArray(material)) material.forEach(m => m.dispose())
        else material?.dispose()
      })
      composer.dispose()
      renderer.dispose()
      try { el.removeChild(canvas) } catch { /* */ }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories, notes, starMapFilter, tagNoteIds])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%', background: '#02030a', overflow: 'hidden' }}
      />

      {tooltip && (
        <div style={{
          position: 'absolute',
          left: tooltip.x + 16,
          top: tooltip.y - 38,
          background: 'rgba(2,4,10,0.92)',
          border: '1px solid rgba(120,140,220,0.35)',
          borderRadius: 7,
          padding: '5px 12px',
          fontSize: 12,
          color: '#dde0f5',
          pointerEvents: 'none',
          zIndex: 10,
          whiteSpace: 'nowrap',
          letterSpacing: '0.03em',
          boxShadow: '0 2px 14px rgba(0,0,0,0.55)',
        }}>
          {tooltip.title}
        </div>
      )}

      <div style={{
        position: 'absolute', bottom: 14, left: '50%', transform: 'translateX(-50%)',
        fontSize: 10, color: 'rgba(160,180,220,0.28)', letterSpacing: 2,
        pointerEvents: 'none', whiteSpace: 'nowrap',
      }}>
        {starMapFilter?.type === 'category' ? '현재 은하 성도' : starMapFilter?.type === 'tag' ? `#${starMapFilter.value} 성도` : '전체 성도'} · 드래그 회전 · Ctrl+드래그 이동 · 스크롤 줌 · 클릭으로 노트 열기
      </div>
    </div>
  )
}
