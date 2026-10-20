import { useEffect, useMemo, useRef, useState } from 'react'
import LiquidGlass from 'liquid-glass-react'
import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { useCategoriesStore } from '../../store/categoriesStore'
import { useNotesStore } from '../../store/notesStore'
import { constellationsApi } from '../../api/constellationsApi'
import { searchApi } from '../../api/searchApi'
import type { DiscoveryRoute, Note } from '../../types'

// ─────────────────────────────────────────────────────────────
// 성도 — 나선 은하 스타일
// 카테고리 하나가 나선 은하 하나: 중심 코어 광원 + 나선팔의 별 + 성운 먼지.
// 장식용 별·먼지는 공전·반짝임·성장을 셰이더에서 계산해 CPU 갱신 없이 수천 개를 그린다.
// 타임라인 슬라이더로 첫 노트부터 최신 노트까지 은하가 자라고 우주가 팽창하는 모습을 되돌려 본다.
// 노트는 같은 나선팔 위에 놓인 밝은 별로, 클릭·라벨·별자리 선 때문에 CPU에서 위치를 계산한다.
// ─────────────────────────────────────────────────────────────

interface Tooltip {
  title: string
  x: number
  y: number
}

// 노트 한 개의 궤도 — 은하 로컬 좌표(원반 = xz 평면, 두께 = y)에서 극좌표로 돈다.
// r·z는 은하 반경(R)에 대한 비율이라 셰이더의 장식 별과 같은 식으로 움직인다.
interface NoteOrbit {
  matrix: THREE.Matrix4 // 은하 로컬 → 월드
  R: number
  ratio: number
  theta: number
  z: number
  omega: number         // rad/s
  rogue: boolean        // 떠돌이 행성 — 우주 팽창에 따라 궤도 반경이 커진다
}

interface RouteVisual {
  aIdx: number
  bIdx: number
  shared: string[]
  t: number
  dir: number
}

// 각 카테고리 은하의 3D 방향 (거리는 computeStarPositions에서 정함)
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

// 성도 배경 — 앱의 밤하늘 남색(#0D1524)보다 한 단계 깊게
const SPACE_BG = 0x060b16
const MAX_NOTES_PER_CAT = 800
const FAVORITE_LABEL_LIMIT = 40   // 이름표를 붙이는 기항지 상한 (스프라이트 수 억제)
const PICK_RADIUS_PX = 11          // 점 클릭/hover 판정 반경
// 행성 육각형은 확대했을 때만 — 카메라 거리 far 이상이면 숨기고 near 이하면 완전히 보인다
const HEX_FADE = { near: 1500, far: 2200, opacity: 0.75 }
const STAR_MAX_PX = 6
// 노트 이름 팻말 — 마우스를 올린 행성 + 확대했을 때 카메라에 가까운 행성
const SIGN = { max: 12, nearDist: 1400 }
// 검색으로 고른 행성에 다가갈 카메라 거리 — 육각형·팻말이 보이는 거리(HEX_FADE.near) 안쪽
const SEARCH_FLY_DIST = 700
const SEARCH_MAX_RESULTS = 8
const OVERLAY_LAYER = 1           // 라벨·마커 전용 레이어 — bloom 뒤에 따로 그려 번지지 않게 한다
// 성운 먼지 구름 수 — 노트(행성)보다 먼지가 많아 보이지 않도록 노트 수에 비례 (노트의 30%, 6~60개)
const dustCount = (n: number) => Math.min(60, Math.max(6, Math.round(n * 0.3)))

// bloom — 별이 겹쳐 밝아진 은하 중심부만 번지도록 임계값을 높게 둔다
const BLOOM = { strength: 0.35, radius: 0.2, threshold: 0.9 }

// 은하 회전 곡선 근사 — 중심은 빠르고 외곽은 완만 (레퍼런스보다 훨씬 느리게: 외곽 약 6분/바퀴)
const OMEGA_BASE = 0.02
const galaxyOmega = (ratio: number) => OMEGA_BASE / (0.18 + Math.pow(ratio, 0.65))

// 타임라인 — 노트가 하나도 없을 때의 우주 크기(비율)와 성장·팽창 보간 속도
const MIN_EXPANSION = 0.25
const TIMELINE_LERP = 0.08

// 노트의 탄생 시각(ms). 가져온 대화 노트는 created_at이 가져온 시각으로 몰려 있어,
// 본문 머리의 '**생성 일시**: YYYY-MM-DD HH:MM:SS'(원래 대화 시각)가 있으면 그것을 쓴다.
const ORIGINAL_DATE_RE = /\*\*생성 일시\*\*:\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)/
function noteBirthTime(note: Note): number {
  const m = ORIGINAL_DATE_RE.exec(note.content.slice(0, 1000))
  const original = m ? Date.parse(`${m[1]}T${m[2]}`) : NaN
  return Number.isNaN(original) ? Date.parse(note.created_at) || 0 : original
}

// 0~1 사이 결정적 의사난수 — 새로고침해도 같은 은하는 같은 모양이 되도록
function hash01(n: number): number {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453
  return x - Math.floor(x)
}

function mulberry32(seed: number): () => number {
  let a = seed | 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// 정규분포 난수 (Box-Muller)
function gaussian(rand: () => number): number {
  let u = 0
  let v = 0
  while (u === 0) u = rand()
  while (v === 0) v = rand()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}

// 은하 크기 — 노트가 많을수록 크게 (√n)
const galaxyRadius = (n: number) => 800 + Math.sqrt(Math.min(n, MAX_NOTES_PER_CAT)) * 50

// 은하의 최대 반경(먼지·후광 포함) — 은하 간 간격과 카메라 거리 계산에 쓴다
const systemRadius = (n: number) => galaxyRadius(n) * 1.15

// 항성 위치를 동적으로 계산: 모든 쌍이 R_i + R_j + MARGIN 이상 떨어지도록
// STAR_POSITIONS의 방향만 쓰고 거리를 늘려가며 배치한다.
function computeStarPositions(counts: number[]): THREE.Vector3[] {
  const MARGIN = 1500
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

// 은하 모양 — 카테고리마다 나선팔 수·감김 정도를 달리해 구별되게
function galaxyShape(ci: number) {
  return { arms: [4, 3, 2, 5][ci % 4], tightness: 3.2 + hash01(ci + 0.5) * 1.6 }
}

// 나선팔 위 한 점 (레퍼런스 initGalaxy의 분포를 그대로 따름). r·z는 은하 반경 비율.
function sampleSpiral(rand: () => number, armIndex: number, shape: { arms: number; tightness: number }) {
  const ratio = Math.pow(rand(), 1.55)                       // 중심에 더 많이
  const scatter = gaussian(rand) * (0.28 + ratio * 0.45)     // 외곽일수록 팔이 퍼짐
  const theta = rand() < 0.15
    ? rand() * Math.PI * 2                                   // 15%는 팔 사이에도
    : armIndex * (Math.PI * 2 / shape.arms) + ratio * shape.tightness + scatter
  const thickness = ((1 - ratio * 0.75) * 42 + 6) / 480      // 중심은 두껍고 외곽은 얇은 원반
  return { ratio, theta, z: gaussian(rand) * thickness * 0.45 }
}

// 카테고리 색에서 은하 팔레트를 만든다: 금빛 중심 → 카테고리 색 → 색상환에서 조금 돌린 외곽
function galaxyPalette(catColor: THREE.Color) {
  const hsl = { h: 0, s: 0, l: 0 }
  catColor.getHSL(hsl)
  return {
    inner: new THREE.Color().setHSL(0.1, 0.85, 0.85),
    mid: new THREE.Color().setHSL(hsl.h, 0.85, 0.7),
    outer: new THREE.Color().setHSL((hsl.h + 0.1) % 1, 0.8, 0.66),
    dust: [hsl.h, (hsl.h + 0.08) % 1, (hsl.h + 0.94) % 1].map(h => new THREE.Color().setHSL(h, 0.9, 0.6)),
    coreGlow: new THREE.Color().setHSL(0.11, 0.95, 0.6),
  }
}

// 거리 비율에 따른 별 색 — 색상환 대신 RGB로 보간해 중간에 엉뚱한 초록이 끼지 않게
function starColor(ratio: number, rand: () => number, pal: ReturnType<typeof galaxyPalette>, out: THREE.Color) {
  if (ratio < 0.16) out.copy(pal.inner)
  else if (ratio < 0.55) out.lerpColors(pal.inner, pal.mid, (ratio - 0.16) / 0.39)
  else out.lerpColors(pal.mid, pal.outer, (ratio - 0.55) / 0.45)
  return out.offsetHSL((rand() - 0.5) * 0.04, 0, (rand() - 0.5) * 0.18)
}

// 장식 별·먼지 셰이더 — 차등 회전, 반짝임, 은하 성장(aBirth ≤ uGrowth인 점만 보임)을 GPU에서 계산
const GALAXY_VERT = /* glsl */ `
  attribute float aR;
  attribute float aTheta;
  attribute float aZ;
  attribute float aOmega;
  attribute float aSize;
  attribute vec2 aTwinkle;
  attribute vec3 aColor;
  attribute float aBirth;
  uniform float uTime;
  uniform float uRadius;
  uniform float uGrowth;
  uniform float uSizeScale;
  uniform float uMinSize;
  uniform float uMaxSize;
  varying vec3 vColor;
  void main() {
    if (aBirth > uGrowth) {
      // 아직 생기지 않은 별 — 클립 공간 밖으로 보내 그리지 않는다
      gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
      gl_PointSize = 0.0;
      return;
    }
    float th = aTheta + aOmega * uTime;
    vec4 mv = modelViewMatrix * vec4(cos(th) * aR * uRadius, aZ * uRadius, sin(th) * aR * uRadius, 1.0);
    gl_Position = projectionMatrix * mv;
    float tw = 0.75 + 0.25 * sin(aTwinkle.x + aTwinkle.y * uTime);
    // 성장 경계에 막 생긴 별은 흐리게 시작해 서서히 밝아진다
    float born = smoothstep(0.0, 0.04, uGrowth - aBirth);
    gl_PointSize = clamp(aSize * uRadius * tw * uSizeScale / -mv.z, uMinSize, uMaxSize);
    vColor = aColor * born;
  }
`
const GALAXY_FRAG = /* glsl */ `
  uniform sampler2D uMap;
  uniform float uOpacity;
  varying vec3 vColor;
  void main() {
    gl_FragColor = vec4(vColor, texture2D(uMap, gl_PointCoord).a * uOpacity);
  }
`

// 원형 소프트 파티클 — 별·노트 점 표현용
function makeRadialTexture(stops: [number, number][], size = 64): THREE.Texture {
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  stops.forEach(([at, a]) => grad.addColorStop(at, `rgba(255,255,255,${a})`))
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
    // 중심 오프셋(최대 0.25) + 반경이 0.5를 넘으면 캔버스 경계에서 잘려 화면에 직선 경계가 생긴다
    const rad = size * (0.08 + Math.random() * 0.17)
    const grad = ctx.createRadialGradient(x, y, 0, x, y, rad)
    grad.addColorStop(0, `rgba(${r},${g},${b},0.5)`)
    grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(x, y, rad, 0, Math.PI * 2)
    ctx.fill()
  }
  return new THREE.CanvasTexture(canvas)
}

// 은하 중심 코어 광원 (레퍼런스의 coreColor → coreGlow → 투명)
function makeCoreTexture(glow: THREE.Color): THREE.Texture {
  const s = 256
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!
  const grad = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2)
  grad.addColorStop(0, '#fff7ed')
  grad.addColorStop(0.12, `#${glow.getHexString()}d9`)
  grad.addColorStop(0.4, `#${glow.getHexString()}30`)
  grad.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, s, s)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

// 행성(노트) 표시용 육각형 테두리 — 장식 별과 구분되도록 노트 점 둘레에 겹쳐 그린다
function makeHexMarkerTexture(): THREE.Texture {
  const s = 64
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!
  ctx.strokeStyle = 'rgba(255,255,255,1)'
  ctx.lineWidth = 3.5
  ctx.lineJoin = 'round'
  ctx.beginPath()
  for (let k = 0; k < 6; k++) {
    const a = Math.PI / 6 + k * Math.PI / 3 // 꼭짓점이 위·아래로 오는 육각형
    const x = s / 2 + (s / 2 - 4) * Math.cos(a)
    const y = s / 2 + (s / 2 - 4) * Math.sin(a)
    if (k === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.closePath()
  ctx.stroke()
  return new THREE.CanvasTexture(canvas)
}

// 이름 붙은 천체 표시용 가는 고리 마커
function makeRingMarkerTexture(): THREE.Texture {
  const s = 64
  const canvas = document.createElement('canvas')
  canvas.width = s
  canvas.height = s
  const ctx = canvas.getContext('2d')!
  ctx.strokeStyle = 'rgba(255,255,255,0.95)'
  ctx.lineWidth = 5
  ctx.beginPath()
  ctx.arc(s / 2, s / 2, s / 2 - 6, 0, Math.PI * 2)
  ctx.stroke()
  return new THREE.CanvasTexture(canvas)
}

// 라벨 스프라이트 — 화면상 고정 크기(sizeAttenuation: false), 배경 없는 얇은 글씨.
// 'title': 은하 이름(은하색, 굵게) / 'right': 기항지 이름(흰색에 가깝게). 둘 다 왼쪽 끝이 천체 위치.
// 웹폰트는 쓰인 글자만 내려받으므로 해당 글자를 명시적으로 로드한 뒤 다시 그린다.
function makeLabelSprite(name: string, color: THREE.Color, placement: 'title' | 'right'): THREE.Sprite {
  const scale = 3 // 고해상도로 그려 축소 — 작은 글씨도 선명하게
  const isTitle = placement === 'title'
  const fontPx = (isTitle ? 10 : 12) * scale
  // 한글은 넓은 자간에서 글자가 흩어져 보여 약하게만 준다
  const spacing = (isTitle ? 0.08 : 0.02) * fontPx
  const font = `${isTitle ? 600 : 400} ${fontPx}px "Pretendard Variable", "Pretendard", sans-serif`
  const padLeft = 14 * scale // 마커와 겹치지 않게 왼쪽 여백
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  // 라벨은 UI 역할 — 깊이 판정 없이 항상 위에
  const mat = new THREE.SpriteMaterial({
    map: tex, transparent: true, depthWrite: false, depthTest: false, sizeAttenuation: false,
    opacity: isTitle ? 0.95 : 0.85, toneMapped: false,
  })
  const sprite = new THREE.Sprite(mat)
  sprite.layers.set(OVERLAY_LAYER)
  // 은하 이름은 은하 색, 기항지 이름은 별빛 흰색에 가깝게
  const tint = `#${color.clone().lerp(new THREE.Color(0xe6eaf2), isTitle ? 0.15 : 0.75).getHexString()}`
  type Ctx2D = CanvasRenderingContext2D & { letterSpacing?: string }

  const draw = () => {
    ctx.font = font
    ;(ctx as Ctx2D).letterSpacing = `${spacing}px`
    const cw = Math.ceil(ctx.measureText(name).width) + padLeft + 8 * scale
    const ch = 22 * scale
    canvas.width = cw
    canvas.height = ch
    ctx.font = font
    ;(ctx as Ctx2D).letterSpacing = `${spacing}px`
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.shadowColor = 'rgba(0, 0, 0, 0.9)'
    ctx.shadowBlur = 3 * scale
    ctx.fillStyle = tint
    ctx.fillText(name, padLeft, ch / 2)
    // 캔버스 px 13*scale ≈ 화면 13px (화면 높이 기준)
    const k = 1 / (scale * 745)
    sprite.scale.set(cw * k, ch * k, 1)
    tex.dispose() // 캔버스 크기가 바뀌면 GPU 텍스처를 새로 만들게 한다
    tex.needsUpdate = true
  }
  draw()
  document.fonts?.load(font, name).then(draw).catch(() => { /* 폴백 글꼴 유지 */ })

  sprite.center.set(0, 0.5) // 왼쪽 끝이 천체 위치 (padLeft만큼 오른쪽에 글자)
  sprite.renderOrder = 10
  return sprite
}

export function StarMapCanvas() {
  const containerRef = useRef<HTMLDivElement>(null)
  const { categories } = useCategoriesStore()
  const { notes, starMapFilter, openNote, setTab, setStarMapFilter } = useNotesStore()
  const [tooltip, setTooltip] = useState<Tooltip | null>(null)
  const [constellationNoteIds, setConstellationNoteIds] = useState<Set<string> | null>(null)
  // 타임라인 시각(ms). null = 현재(최신). 씬은 매 프레임 ref를 읽어 다시 만들지 않고 반영한다
  const [timeline, setTimeline] = useState<number | null>(null)
  const timelineRef = useRef<number | null>(null)
  const births = useMemo(() => new Map(notes.map(n => [n.id, noteBirthTime(n)])), [notes])
  const timeRange = useMemo(() => {
    const ts = [...births.values()]
    return ts.length ? { min: Math.min(...ts), max: Math.max(...ts) } : null
  }, [births])
  // 성도 검색 — 고른 행성으로 카메라를 보낸다. 씬 안 flyTo는 ref로 연결한다
  const flyToRef = useRef<((id: string) => boolean) | null>(null)
  const pendingFlyRef = useRef<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchActive, setSearchActive] = useState(0)
  const searchMatches = useMemo(() => {
    // 제목이 'PHP_구문_오류_해결'처럼 밑줄로 이어져 있어 띄어쓰기·밑줄·하이픈을 같은 구분자로 보고,
    // 검색어의 단어가 모두 들어 있으면 일치. 제목 일치를 먼저, 본문 일치를 그다음에 보여 준다.
    const norm = (t: string) => t.toLowerCase().replace(/[_\-\s]+/g, ' ')
    const words = norm(searchQuery).trim().split(' ').filter(Boolean)
    if (!words.length) return []
    const hasAll = (t: string) => words.every(w => t.includes(w))
    const inTitle = notes.filter(n => hasAll(norm(n.title)))
    const inBody = inTitle.length >= SEARCH_MAX_RESULTS
      ? []
      : notes.filter(n => !inTitle.includes(n) && hasAll(norm(n.content)))
    return [...inTitle, ...inBody].slice(0, SEARCH_MAX_RESULTS)
  }, [notes, searchQuery])
  const selectSearch = (note: Note) => {
    setSearchQuery(note.title)
    setSearchOpen(false)
    // 타임라인상 아직 없는 행성일 수 있으니 현재 우주로
    timelineRef.current = null
    setTimeline(null)
    if (flyToRef.current?.(note.id)) return
    // 필터로 숨겨진 행성 — 전체 성도로 돌아가 씬을 다시 만든 뒤 날아간다
    pendingFlyRef.current = note.id
    setStarMapFilter(null)
  }
  const onSearchKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSearchActive(i => Math.min(i + 1, searchMatches.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSearchActive(i => Math.max(i - 1, 0)) }
    // 한글 조합 중 Enter는 글자 확정용이라 무시
    else if (e.key === 'Enter' && !e.nativeEvent.isComposing && searchMatches[searchActive]) selectSearch(searchMatches[searchActive])
    else if (e.key === 'Escape') { setSearchOpen(false); e.currentTarget.blur() }
  }

  const changeTimeline = (v: number) => {
    const t = timeRange && v < timeRange.max ? v : null // 끝까지 당기면 현재
    timelineRef.current = t
    setTimeline(t)
  }
  // 범례 접기 — 좁은 화면에서는 기본으로 접어 은하를 가리지 않게
  const [legendOpen, setLegendOpen] = useState(() => {
    try {
      const saved = localStorage.getItem('sn-starmap-legend')
      if (saved !== null) return saved === 'open'
    } catch { /* 저장소 접근 불가 시 기본값 */ }
    return window.innerWidth >= 1100
  })
  const toggleLegend = () => setLegendOpen(o => {
    try { localStorage.setItem('sn-starmap-legend', o ? 'closed' : 'open') } catch { /* */ }
    return !o
  })

  // 별자리 필터일 때는 그 개념을 가진 노트 id 집합을 먼저 가져와야
  // 아래 씬 구성 effect에서 필터링에 쓸 수 있다 (은하를 넘나드는 필터라
  // 카테고리처럼 동기적으로 계산할 수 없음).
  useEffect(() => {
    if (starMapFilter?.type !== 'constellation') { setConstellationNoteIds(null); return }
    let alive = true
    constellationsApi.notes(starMapFilter.value).then(list => {
      if (alive) setConstellationNoteIds(new Set(list.map(n => n.id)))
    })
    return () => { alive = false }
  }, [starMapFilter])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const width = el.clientWidth || 800
    const height = el.clientHeight || 600
    const disposables: { dispose: () => void }[] = []

    // 표시 대상 필터링 — 카테고리 필터는 은하 하나로 좁히고, 별자리 필터는
    // 은하를 그대로 둔 채(별자리는 여러 은하에 걸침) 노트만 좁힌다.
    const visibleNotes = !starMapFilter
      ? notes
      : starMapFilter.type === 'category'
        ? notes.filter(n => n.category_id === starMapFilter.value)
        : notes.filter(n => constellationNoteIds?.has(n.id) ?? false)
    const visibleCats = starMapFilter?.type === 'category'
      ? categories.filter(c => c.id === starMapFilter.value)
      : categories

    // 은하 간 간격이 보장되도록 위치를 동적으로 계산 (필터와 무관하게
    // 전체 카테고리 기준으로 계산해 위치가 흔들리지 않게 유지)
    const noteCounts = categories.map(c => notes.filter(n => n.category_id === c.id).length)
    const starPositions = computeStarPositions(noteCounts)

    // ── Scene ────────────────────────────────────────────────
    const scene = new THREE.Scene()
    // 배경색은 renderer.setClearColor로 칠한다 — scene.background는 bloom composer 출력에서 장면을 덮어 버린다
    scene.fog = new THREE.FogExp2(SPACE_BG, 0.00004)

    // 카메라 초점: 전체 뷰는 모든 은하의 중심점(특정 은하에 치우치지 않게)
    const lookTarget = new THREE.Vector3(0, 0, 0)
    if (starPositions.length > 0) {
      starPositions.forEach(p => lookTarget.add(p))
      lookTarget.divideScalar(starPositions.length)
    }
    const universeCenter = lookTarget.clone()
    const universeRadius = starPositions.reduce(
      (m, p, i) => Math.max(m, p.distanceTo(universeCenter) + systemRadius(noteCounts[i])),
      0,
    )
    let initCamR = Math.max(4000, universeRadius * 1.5)
    if (starMapFilter?.type === 'category') {
      const ci = categories.findIndex(c => c.id === starMapFilter.value)
      if (ci >= 0) {
        // 선택한 은하를 화면 중앙에 두고, 은하 전체가 들어오도록 거리 조정
        lookTarget.copy(starPositions[ci])
        initCamR = Math.max(2000, systemRadius(noteCounts[ci]) * 2.2)
      } else {
        initCamR = 2200
      }
    }
    const maxZoom = Math.max(12000, initCamR * 2)

    const camera = new THREE.PerspectiveCamera(60, width / height, 1, 250000)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    // composer 렌더 타깃을 지울 때 지우기 색이 sRGB로 한 번 더 인코딩돼 밝은 회청색이 되므로 미리 선형으로 내려 준다
    renderer.setClearColor(new THREE.Color(SPACE_BG).convertSRGBToLinear())
    el.appendChild(renderer.domElement)

    // 후처리: 장면 → bloom(반해상도) → 톤매핑·sRGB 출력. 라벨은 그 뒤에 따로 그린다.
    const composer = new EffectComposer(renderer)
    composer.addPass(new RenderPass(scene, camera))
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(width / 2, height / 2), BLOOM.strength, BLOOM.radius, BLOOM.threshold)
    composer.addPass(bloomPass)
    composer.addPass(new OutputPass())
    disposables.push(composer, bloomPass)

    renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;cursor:grab;'

    // 팻말은 DOM으로 캔버스 위에 띄운다 (글자가 선명하고 스타일을 CSS로 다루기 쉽다).
    // 요소를 미리 만들어 두고 매 프레임 위치·내용만 바꾼다.
    const signLayer = document.createElement('div')
    signLayer.className = 'sn-signposts'
    el.appendChild(signLayer)
    const signs = Array.from({ length: SIGN.max + 2 }, () => { // + 마우스 올린 행성, 검색한 행성
      const root = document.createElement('div')
      root.className = 'sn-signpost'
      const board = document.createElement('span')
      board.className = 'sn-signpost-board'
      const text = document.createElement('span')
      text.className = 'sn-signpost-text'
      board.appendChild(text)
      const pole = document.createElement('span')
      pole.className = 'sn-signpost-pole'
      root.append(board, pole)
      root.style.display = 'none'
      signLayer.appendChild(root)
      return { root, text, idx: -1 }
    })

    const starTex = makeRadialTexture([[0, 1], [0.35, 0.7], [1, 0]])
    // 성운 먼지 — 레퍼런스처럼 알파가 아주 낮은 큰 원 (겹칠수록 밝아짐)
    const dustTex = makeRadialTexture([[0, 0.16], [0.35, 0.06], [1, 0]], 128)
    const markerTex = makeRingMarkerTexture()
    const hexTex = makeHexMarkerTexture()
    disposables.push(starTex, dustTex, markerTex, hexTex)
    const white = new THREE.Color(0xffffff)

    // 모든 은하 재질이 같은 uniform 객체를 공유 — 매 프레임 한 번만 갱신하면 된다
    const shared = {
      uTime: { value: 0 },
      uSizeScale: { value: 1 },
      uMinSize: { value: 1 },
    }
    function updateSizeScale() {
      const h = renderer.getDrawingBufferSize(new THREE.Vector2()).y
      shared.uSizeScale.value = h / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)))
      shared.uMinSize.value = 1.2 * renderer.getPixelRatio()
    }
    updateSizeScale()

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

    // ── 은하 (카테고리) ──────────────────────────────────────
    // 은하마다 원반을 조금씩 기울여 우주 전체가 한 평면으로 납작해지지 않게 한다
    const galaxyQuat = (ci: number) =>
      new THREE.Quaternion().setFromEuler(new THREE.Euler(0.12 + (ci % 4) * 0.14, ci * 0.6, 0))

    // 장식용 점 집합 (별 또는 먼지) — position은 셰이더가 무시하지만 draw count를 위해 필요
    function makeGalaxyPoints(
      count: number, R: number, tex: THREE.Texture, opacity: number, maxPx: number,
      growth: { value: number },
      fill: (i: number, a: { r: Float32Array; theta: Float32Array; z: Float32Array; omega: Float32Array; size: Float32Array; tw: Float32Array; col: Float32Array; birth: Float32Array }) => void,
    ): THREE.Points {
      const a = {
        r: new Float32Array(count), theta: new Float32Array(count), z: new Float32Array(count),
        omega: new Float32Array(count), size: new Float32Array(count),
        tw: new Float32Array(count * 2), col: new Float32Array(count * 3), birth: new Float32Array(count),
      }
      for (let i = 0; i < count; i++) fill(i, a)
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
      geo.setAttribute('aR', new THREE.BufferAttribute(a.r, 1))
      geo.setAttribute('aTheta', new THREE.BufferAttribute(a.theta, 1))
      geo.setAttribute('aZ', new THREE.BufferAttribute(a.z, 1))
      geo.setAttribute('aOmega', new THREE.BufferAttribute(a.omega, 1))
      geo.setAttribute('aSize', new THREE.BufferAttribute(a.size, 1))
      geo.setAttribute('aTwinkle', new THREE.BufferAttribute(a.tw, 2))
      geo.setAttribute('aColor', new THREE.BufferAttribute(a.col, 3))
      geo.setAttribute('aBirth', new THREE.BufferAttribute(a.birth, 1))
      const points = new THREE.Points(geo, new THREE.ShaderMaterial({
        uniforms: {
          ...shared, uRadius: { value: R }, uGrowth: growth, uMap: { value: tex }, uOpacity: { value: opacity },
          uMaxSize: { value: maxPx * renderer.getPixelRatio() },
        },
        vertexShader: GALAXY_VERT,
        fragmentShader: GALAXY_FRAG,
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      points.frustumCulled = false // 실제 위치는 셰이더에서 정해져 바운딩 구가 의미 없다
      return points
    }

    // 타임라인용 은하 상태 — 성장률(growth)은 셰이더 uniform을 그대로 공유해 매 프레임 보간한다
    interface GalaxyState {
      ci: number
      catId: string
      group: THREE.Group
      base: THREE.Vector3   // 현재 시점(팽창 1)의 위치
      R: number
      matrix: THREE.Matrix4
      growth: { value: number }
      core: THREE.Sprite
      title: THREE.Sprite
    }
    const galaxies = new Map<number, GalaxyState>()

    visibleCats.forEach(cat => {
      const ci = categories.findIndex(c => c.id === cat.id)
      const n = noteCounts[ci]
      const R = galaxyRadius(n)
      const shape = galaxyShape(ci)
      const color = new THREE.Color(cat.color ?? '#94a3b8')
      const pal = galaxyPalette(color)

      const group = new THREE.Group()
      group.position.copy(starPositions[ci])
      group.quaternion.copy(galaxyQuat(ci))
      group.updateMatrixWorld()
      scene.add(group)
      const growth = { value: 1 }

      // 1. 나선팔의 별
      const rand = mulberry32(ci * 7919 + 17)
      const c = new THREE.Color()
      const starCount = Math.min(6000, 2500 + n * 4)
      // 별은 확대해도 화면상 6px까지만 — 고정 크기인 행성(노트)보다 커져 묻히지 않게
      group.add(makeGalaxyPoints(starCount, R, starTex, 1, STAR_MAX_PX, growth, (i, a) => {
        const s = sampleSpiral(rand, i % shape.arms, shape)
        const giant = rand() < 0.025 // 드물게 밝은 거성
        const base = giant ? rand() * 2.2 + 2.0 : rand() * 1.4 + 0.5
        a.r[i] = s.ratio
        a.theta[i] = s.theta
        a.z[i] = s.z
        a.omega[i] = galaxyOmega(s.ratio)
        a.size[i] = base * 0.012
        a.tw[i * 2] = rand() * Math.PI * 2
        a.tw[i * 2 + 1] = (rand() * 0.04 + 0.01) * 60
        starColor(s.ratio, rand, pal, c)
        a.col.set([c.r, c.g, c.b], i * 3)
        a.birth[i] = Math.min(1, s.ratio * 0.8 + rand() * 0.2) // 중심부터 바깥으로 생겨난다
      }))

      // 2. 성운·우주 먼지 — 나선팔을 따라 큰 반투명 구름
      group.add(makeGalaxyPoints(dustCount(n), R, dustTex, 1, 4096, growth, (i, a) => {
        const ratio = Math.pow(rand(), 1.2) * 0.9 + 0.05
        const dc = pal.dust[i % pal.dust.length]
        a.r[i] = ratio
        a.theta[i] = (i % shape.arms) * (Math.PI * 2 / shape.arms) + ratio * shape.tightness + gaussian(rand) * 0.22
        a.z[i] = gaussian(rand) * 12 / 480
        a.omega[i] = galaxyOmega(ratio)
        a.size[i] = ((rand() * 55 + 45) * (1 - ratio * 0.3) * 2) / 480
        a.col.set([dc.r, dc.g, dc.b], i * 3)
        a.birth[i] = Math.min(1, ratio * 0.9 + 0.1)
      }))

      // 3. 은하 중심 코어 광원
      const core = new THREE.Sprite(new THREE.SpriteMaterial({
        map: makeCoreTexture(pal.coreGlow), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      core.scale.setScalar(R * 0.6)
      group.add(core)

      // 이름표는 코어 오른쪽 — 매 프레임 카메라 오른쪽 방향으로 밀어 가까이서도 코어와 겹치지 않게
      const title = makeLabelSprite(cat.name, color, 'title')
      scene.add(title)
      galaxies.set(ci, {
        ci, catId: cat.id, group, base: starPositions[ci].clone(), R, matrix: group.matrixWorld, growth, core, title,
      })
    })

    // ── 노트 (나선팔 위의 밝은 별, Points 하나) ─────────────
    const orbits: NoteOrbit[] = []
    const notePos: THREE.Vector3[] = []
    const noteColors: THREE.Color[] = []
    const noteIds: string[] = []
    const noteTitles: string[] = []
    const noteBirth: number[] = [] // noteBirthTime (ms)
    const noteAlive: boolean[] = []
    const favoriteIdx: number[] = []

    const addNote = (id: string, title: string, isFavorite: boolean, orbit: NoteOrbit, color: THREE.Color, birth: number) => {
      const i = orbits.length
      orbits.push(orbit)
      notePos.push(new THREE.Vector3())
      noteColors.push(color)
      noteIds.push(id)
      noteTitles.push(title)
      noteBirth.push(birth)
      noteAlive.push(true)
      if (isFavorite && favoriteIdx.length < FAVORITE_LABEL_LIMIT) favoriteIdx.push(i)
    }

    visibleCats.forEach(cat => {
      const ci = categories.findIndex(c => c.id === cat.id)
      const g = galaxies.get(ci)
      const catNotes = visibleNotes.filter(n => n.category_id === cat.id).slice(0, MAX_NOTES_PER_CAT)
      if (!g || catNotes.length === 0) return
      const shape = galaxyShape(ci)
      const color = new THREE.Color(cat.color ?? '#94a3b8').lerp(white, 0.5)
      catNotes.forEach((note, j) => {
        // 노트마다 고정 시드 — 새로고침해도 같은 노트는 같은 자리
        const s = sampleSpiral(mulberry32(ci * 100003 + j * 31 + 7), j % shape.arms, shape)
        // 코어 광원에 묻히지 않게 중심 가까이는 비운다
        const ratio = 0.14 + s.ratio * 0.86
        addNote(note.id, note.title, !!note.is_favorite, {
          matrix: g.matrix, R: g.R, ratio, theta: s.theta, z: s.z, omega: galaxyOmega(ratio), rogue: false,
        }, color, noteBirthTime(note))
      })
    })

    // 미분류 노트(떠돌이 행성): 은하에 속하지 않고 우주 전체를 크게 느리게 돈다
    const uncategorized = visibleNotes.filter(n => !n.category_id)
    if (uncategorized.length > 0) {
      const neutral = new THREE.Color('#94a3b8')
      uncategorized.forEach((note, j) => {
        const seed = 90000 + j
        const tilt = new THREE.Quaternion().setFromEuler(
          new THREE.Euler((hash01(seed) - 0.5) * 1.2, hash01(seed + 0.4) * Math.PI * 2, 0),
        )
        addNote(note.id, note.title, !!note.is_favorite, {
          matrix: new THREE.Matrix4().compose(universeCenter, tilt, new THREE.Vector3(1, 1, 1)),
          R: universeRadius,
          ratio: 0.55 + 0.4 * hash01(seed + 0.2),
          theta: hash01(seed + 0.9) * Math.PI * 2,
          z: 0,
          omega: OMEGA_BASE * 0.05,
          rogue: true,
        }, neutral, noteBirthTime(note))
      })
    }

    // 셰이더와 같은 식 — 노트도 장식 별과 같은 속도로 돈다. 떠돌이 행성은 우주 팽창만큼 궤도가 커진다
    let expansion = 1
    function updateNotePositions() {
      const t = shared.uTime.value
      orbits.forEach((o, i) => {
        const th = o.theta + o.omega * t
        const R = o.rogue ? o.R * expansion : o.R
        notePos[i].set(Math.cos(th) * o.ratio * R, o.z * R, Math.sin(th) * o.ratio * R).applyMatrix4(o.matrix)
      })
    }
    updateNotePositions()

    const notePosAttr = new THREE.BufferAttribute(new Float32Array(orbits.length * 3), 3)
    notePosAttr.setUsage(THREE.DynamicDrawUsage)
    const noteColAttr = new THREE.BufferAttribute(new Float32Array(orbits.length * 3), 3)
    noteColors.forEach((c, i) => noteColAttr.setXYZ(i, c.r, c.g, c.b))
    const noteGeo = new THREE.BufferGeometry()
    noteGeo.setAttribute('position', notePosAttr)
    noteGeo.setAttribute('color', noteColAttr)
    const notePoints = new THREE.Points(noteGeo, new THREE.PointsMaterial({
      size: 10, sizeAttenuation: false, vertexColors: true, map: starTex,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
    }))
    notePoints.frustumCulled = false // 점이 매 프레임 움직여 바운딩 구가 금방 낡는다
    scene.add(notePoints)

    // 행성 표시 육각형 — 위치·색 버퍼를 노트 점과 공유해 공전과 타임라인 표시 여부를 그대로 따른다
    const hexGeo = new THREE.BufferGeometry()
    hexGeo.setAttribute('position', notePosAttr)
    hexGeo.setAttribute('color', noteColAttr)
    const hexMat = new THREE.PointsMaterial({
      size: 20, sizeAttenuation: false, vertexColors: true, map: hexTex,
      transparent: true, opacity: HEX_FADE.opacity, depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
    })
    const noteHexes = new THREE.Points(hexGeo, hexMat)
    noteHexes.frustumCulled = false
    scene.add(noteHexes)

    // ── 기항지(즐겨찾기): ◯ 마커 + 이름표 ───────────────────
    const favoriteSprites: { idx: number; marker: THREE.Sprite; label: THREE.Sprite }[] = []
    favoriteIdx.forEach(idx => {
      const marker = new THREE.Sprite(new THREE.SpriteMaterial({
        map: markerTex, color: 0xdfe5f0, transparent: true, depthWrite: false, depthTest: false, sizeAttenuation: false,
        toneMapped: false,
      }))
      marker.layers.set(OVERLAY_LAYER)
      marker.scale.setScalar(14 / 745) // 화면 약 14px
      const label = makeLabelSprite(noteTitles[idx], noteColors[idx], 'right')
      scene.add(marker, label)
      favoriteSprites.push({ idx, marker, label })
    })

    function syncNoteBuffers() {
      notePos.forEach((p, i) => notePosAttr.setXYZ(i, p.x, p.y, p.z))
      notePosAttr.needsUpdate = true
      favoriteSprites.forEach(f => {
        f.marker.position.copy(notePos[f.idx])
        f.label.position.copy(notePos[f.idx])
      })
    }
    syncNoteBuffers()

    // ── 별자리 선 ───────────────────────────────────────────
    // 별자리 필터에서는 보이는 노트가 모두 그 별자리의 별이다. 처음 위치 기준
    // 최소 신장 트리(가장 가까운 별끼리, 고리 없이)로 이어 실제 별자리처럼 보이게 하고,
    // 선의 양 끝은 매 프레임 공전하는 노트 위치를 따라간다.
    let constellationLines: THREE.LineSegments | null = null
    const constellationEdges: [number, number][] = []
    if (starMapFilter?.type === 'constellation' && notePos.length >= 2) {
      const n = notePos.length
      const inTree = new Array(n).fill(false)
      const best = new Array(n).fill(Infinity)
      const parent = new Array(n).fill(-1)
      best[0] = 0
      for (let k = 0; k < n; k++) {
        let u = -1
        for (let i = 0; i < n; i++) if (!inTree[i] && (u < 0 || best[i] < best[u])) u = i
        inTree[u] = true
        if (parent[u] >= 0) constellationEdges.push([parent[u], u])
        for (let v = 0; v < n; v++) {
          if (inTree[v]) continue
          const d = notePos[u].distanceToSquared(notePos[v])
          if (d < best[v]) { best[v] = d; parent[v] = u }
        }
      }
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(constellationEdges.length * 6), 3))
      constellationLines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
        color: 0xbfd4ff, transparent: true, opacity: 0.6,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      constellationLines.frustumCulled = false
      scene.add(constellationLines)
    }
    function updateConstellationLines() {
      if (!constellationLines) return
      const attr = constellationLines.geometry.getAttribute('position') as THREE.BufferAttribute
      constellationEdges.forEach(([a, b], i) => {
        const pa = notePos[a]
        const pb = noteAlive[a] && noteAlive[b] ? notePos[b] : pa // 아직 없는 노트에 닿는 선은 길이 0으로 접는다
        attr.setXYZ(i * 2, pa.x, pa.y, pa.z)
        attr.setXYZ(i * 2 + 1, pb.x, pb.y, pb.z)
      })
      attr.needsUpdate = true
    }
    updateConstellationLines()

    // ── 항로 (발견된 노트 연결) + 왕복하는 빛 ───────────────
    const routeVisuals: RouteVisual[] = []
    const lightPos: THREE.Vector3[] = [] // 빛의 머리 위치 — 화면 좌표 hover 판정용
    const routeAlive: boolean[] = []     // 타임라인상 두 노트가 모두 생긴 항로
    let routeLineBaseCol: Float32Array | null = null
    let routeLightBaseCol: Float32Array | null = null
    // 항로마다 빛 점 하나 (꼬리 없음). 모든 빛을 Points 하나로 묶는다.

    // 항로 곡선: 두 노트 사이를 위로 볼록하게 잇는 2차 베지어.
    // 항로가 수천 개라 곡선 객체·버퍼를 매 프레임 새로 만들지 않고 식으로 직접 계산한다.
    const ROUTE_SEGS = 16
    const routeCtrl = new THREE.Vector3()
    function routePoint(a: THREE.Vector3, b: THREE.Vector3, t: number, out: THREE.Vector3) {
      const u = 1 - t
      return out.set(
        u * u * a.x + 2 * u * t * routeCtrl.x + t * t * b.x,
        u * u * a.y + 2 * u * t * routeCtrl.y + t * t * b.y,
        u * u * a.z + 2 * u * t * routeCtrl.z + t * t * b.z,
      )
    }
    function setRouteCtrl(a: THREE.Vector3, b: THREE.Vector3) {
      // 중간점을 거리의 15%만큼 띄우도록 (베지어 정점은 제어점의 절반 높이)
      routeCtrl.copy(a).add(b).multiplyScalar(0.5)
      routeCtrl.y += a.distanceTo(b) * 0.3
    }

    let routeLines: THREE.LineSegments | null = null
    let routeLights: THREE.Points | null = null
    let routesCancelled = false
    searchApi.discoveryRoutes().then(routes => {
      if (routesCancelled) return
      const routeColors: THREE.Color[] = []
      routes.forEach((route: DiscoveryRoute) => {
        const aIdx = noteIds.indexOf(route.note_a)
        const bIdx = noteIds.indexOf(route.note_b)
        if (aIdx < 0 || bIdx < 0) return // 필터로 숨겨진 노트
        routeColors.push(noteColors[aIdx].clone().lerp(noteColors[bIdx], 0.5))
        lightPos.push(new THREE.Vector3())
        routeAlive.push(true)
        routeVisuals.push({ aIdx, bIdx, shared: route.shared_entities, t: Math.random(), dir: 1 })
      })
      if (!routeVisuals.length) return
      // 모든 항로를 LineSegments 하나로 — draw call 1회
      const vertsPerRoute = ROUTE_SEGS * 2
      const col = new Float32Array(routeVisuals.length * vertsPerRoute * 3)
      routeColors.forEach((c, i) => {
        for (let v = 0; v < vertsPerRoute; v++) col.set([c.r, c.g, c.b], (i * vertsPerRoute + v) * 3)
      })
      const geo = new THREE.BufferGeometry()
      const posAttr = new THREE.BufferAttribute(new Float32Array(routeVisuals.length * vertsPerRoute * 3), 3)
      posAttr.setUsage(THREE.DynamicDrawUsage)
      geo.setAttribute('position', posAttr)
      routeLineBaseCol = col.slice()
      geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
      routeLines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({
        vertexColors: true, transparent: true, opacity: 0.05,
        depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
      }))
      routeLines.frustumCulled = false
      scene.add(routeLines)

      // 빛: 항로 색을 흰빛 쪽으로 밝힌 점 하나
      const lightCol = new Float32Array(routeVisuals.length * 3)
      const c = new THREE.Color()
      routeColors.forEach((rc, i) => {
        c.copy(rc).lerp(white, 0.7)
        lightCol.set([c.r, c.g, c.b], i * 3)
      })
      const lightGeo = new THREE.BufferGeometry()
      const lightPosAttr = new THREE.BufferAttribute(new Float32Array(routeVisuals.length * 3), 3)
      lightPosAttr.setUsage(THREE.DynamicDrawUsage)
      lightGeo.setAttribute('position', lightPosAttr)
      routeLightBaseCol = lightCol.slice()
      lightGeo.setAttribute('color', new THREE.BufferAttribute(lightCol, 3))
      routeLights = new THREE.Points(lightGeo, new THREE.PointsMaterial({
        size: 2.5, sizeAttenuation: false, vertexColors: true, map: starTex,
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
      }))
      routeLights.frustumCulled = false
      scene.add(routeLights)
      appliedTime = undefined // 항로가 늦게 도착했으니 현재 타임라인을 다시 적용
    }).catch(err => {
      console.error('discovery routes 로드 실패:', err)
    })

    const routeP0 = new THREE.Vector3()
    const routeP1 = new THREE.Vector3()
    function updateRoutes() {
      if (!routeLines || !routeLights) return
      const posAttr = routeLines.geometry.getAttribute('position') as THREE.BufferAttribute
      const lightAttr = routeLights.geometry.getAttribute('position') as THREE.BufferAttribute
      routeVisuals.forEach((rv, i) => {
        // 양 끝 노트가 공전하므로 곡선을 매 프레임 다시 잇는다
        const a = notePos[rv.aIdx]
        const b = notePos[rv.bIdx]
        setRouteCtrl(a, b)
        routeP0.copy(a)
        for (let s = 1; s <= ROUTE_SEGS; s++) {
          routePoint(a, b, s / ROUTE_SEGS, routeP1)
          const v = (i * ROUTE_SEGS + s - 1) * 2
          posAttr.setXYZ(v, routeP0.x, routeP0.y, routeP0.z)
          posAttr.setXYZ(v + 1, routeP1.x, routeP1.y, routeP1.z)
          routeP0.copy(routeP1)
        }

        rv.t += rv.dir * 0.006
        if (rv.t >= 1) { rv.t = 1; rv.dir = -1 }
        if (rv.t <= 0) { rv.t = 0; rv.dir = 1 }
        // smoothstep — 양 끝에서 감속
        routePoint(a, b, rv.t * rv.t * (3 - 2 * rv.t), lightPos[i])
        lightAttr.setXYZ(i, lightPos[i].x, lightPos[i].y, lightPos[i].z)
      })
      posAttr.needsUpdate = true
      lightAttr.needsUpdate = true
    }

    // ── 타임라인: 은하 성장 + 우주 팽창 ─────────────────────
    // 슬라이더 시각(T) 이전에 생성된 노트만 보이고, 은하는 그 카테고리 노트가 생긴 비율만큼
    // 중심부터 자라며, 우주는 전체 노트가 생긴 비율만큼 중심(universeCenter)에서 팽창한다.
    // 성장률·팽창은 목표값으로 매 프레임 보간해 슬라이더를 끌 때 부드럽게 움직인다.
    const birthsByCat = new Map<string, number[]>()
    notes.forEach(n => {
      if (!n.category_id) return
      const list = birthsByCat.get(n.category_id) ?? []
      list.push(noteBirthTime(n))
      birthsByCat.set(n.category_id, list)
    })
    const allBirths = notes.map(noteBirthTime)
    const countUntil = (births: number[], t: number) => births.reduce((k, b) => k + (b <= t ? 1 : 0), 0)
    const growthTarget = new Map<number, number>()
    let expansionTarget = 1
    let appliedTime: number | null | undefined // undefined = 아직 적용 전
    const galaxyOffset = new THREE.Vector3()

    function setColorRange(attr: THREE.BufferAttribute, base: Float32Array, from: number, count: number, on: boolean) {
      const arr = attr.array as Float32Array
      for (let k = from * 3; k < (from + count) * 3; k++) arr[k] = on ? base[k] : 0
    }
    const noteBaseCol = (noteColAttr.array as Float32Array).slice()

    function applyTimeline() {
      const t = timelineRef.current
      if (t !== appliedTime) {
        appliedTime = t
        const T = t ?? Infinity
        // 노트 — 아직 생기지 않은 노트는 색을 0으로(가산 혼합이라 보이지 않음)
        noteBirth.forEach((b, i) => {
          noteAlive[i] = b <= T
          setColorRange(noteColAttr, noteBaseCol, i, 1, noteAlive[i])
        })
        noteColAttr.needsUpdate = true
        favoriteSprites.forEach(f => {
          f.marker.visible = noteAlive[f.idx]
          f.label.visible = noteAlive[f.idx]
        })
        // 항로 — 양 끝 노트가 모두 생겨야 보인다
        routeVisuals.forEach((rv, i) => { routeAlive[i] = noteAlive[rv.aIdx] && noteAlive[rv.bIdx] })
        if (routeLines && routeLights && routeLineBaseCol && routeLightBaseCol) {
          const lineAttr = routeLines.geometry.getAttribute('color') as THREE.BufferAttribute
          const lightAttr = routeLights.geometry.getAttribute('color') as THREE.BufferAttribute
          routeAlive.forEach((on, i) => {
            setColorRange(lineAttr, routeLineBaseCol!, i * ROUTE_SEGS * 2, ROUTE_SEGS * 2, on)
            setColorRange(lightAttr, routeLightBaseCol!, i, 1, on)
          })
          lineAttr.needsUpdate = true
          lightAttr.needsUpdate = true
        }
        // 은하 성장률 — 노트 없는 빈 카테고리는 현재 시점에만 보인다
        galaxies.forEach(g => {
          const births = birthsByCat.get(g.catId) ?? []
          growthTarget.set(g.ci, births.length ? countUntil(births, T) / births.length : t === null ? 1 : 0)
        })
        // 단일 은하 보기에서는 팽창하면 은하가 화면 밖으로 밀려나므로 성장만 보여 준다
        expansionTarget = starMapFilter?.type === 'category' || !allBirths.length
          ? 1
          : MIN_EXPANSION + (1 - MIN_EXPANSION) * countUntil(allBirths, T) / allBirths.length
      }

      expansion += (expansionTarget - expansion) * TIMELINE_LERP
      galaxies.forEach(g => {
        g.growth.value += ((growthTarget.get(g.ci) ?? 1) - g.growth.value) * TIMELINE_LERP
        const born = g.growth.value > 0.002
        g.core.visible = born
        g.title.visible = born
        g.core.scale.setScalar(g.R * 0.6 * Math.sqrt(Math.max(0, g.growth.value)))
        galaxyOffset.copy(g.base).sub(universeCenter)
        g.group.position.copy(universeCenter).addScaledVector(galaxyOffset, expansion)
        g.group.updateMatrixWorld()
      })
    }

    // ── 카메라 컨트롤 ────────────────────────────────────────
    // 입력은 target 값만 바꾸고 매 프레임 보간해 부드럽게 따라간다 (레퍼런스의 damping)
    const cam = { theta: 0.2, phi: 1.05, r: initCamR }
    const camTarget = { ...cam }
    let pointerDown = false
    let lastMouse = { x: 0, y: 0 }
    let moved = false

    function updateCamera() {
      camera.position.set(
        lookTarget.x + cam.r * Math.sin(cam.phi) * Math.sin(cam.theta),
        lookTarget.y + cam.r * Math.cos(cam.phi),
        lookTarget.z + cam.r * Math.sin(cam.phi) * Math.cos(cam.theta),
      )
      camera.lookAt(lookTarget)
      camera.updateMatrixWorld()
    }
    updateCamera()

    const canvas = renderer.domElement

    // 점은 화면상 고정 크기라 3D 레이캐스트 대신 화면 좌표에서 가장 가까운 점을 고른다
    const proj = new THREE.Vector3()
    let hoverIdx = -1 // 마우스가 올라간 노트
    let focusIdx = -1 // 검색으로 고른 노트 — 팻말을 강조하고 카메라가 따라간다
    let following = false
    function flyTo(id: string): boolean {
      const i = noteIds.indexOf(id)
      if (i < 0) return false
      focusIdx = i
      following = true
      camTarget.r = SEARCH_FLY_DIST
      return true
    }
    function pickNearest(
      points: THREE.Vector3[], e: PointerEvent, rect: DOMRect, alive: boolean[], radiusPx = PICK_RADIUS_PX,
    ): number {
      let best = -1
      let bestD = radiusPx * radiusPx
      points.forEach((p, i) => {
        if (!alive[i]) return // 타임라인상 아직 생기지 않은 노트·항로
        proj.copy(p).project(camera)
        if (proj.z > 1) return // 카메라 뒤
        const dx = (proj.x + 1) / 2 * rect.width + rect.left - e.clientX
        const dy = (1 - proj.y) / 2 * rect.height + rect.top - e.clientY
        const d = dx * dx + dy * dy
        if (d < bestD) { bestD = d; best = i }
      })
      return best
    }

    canvas.addEventListener('pointerdown', (e) => {
      pointerDown = true
      following = false // 직접 조작하면 검색 행성 따라가기를 멈춘다
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
          const panSpeed = cam.r * 0.0015
          lookTarget.addScaledVector(right, -dx * panSpeed)
          lookTarget.addScaledVector(up, dy * panSpeed)
        } else {
          camTarget.theta -= dx * 0.006
          camTarget.phi = Math.max(0.12, Math.min(Math.PI - 0.12, camTarget.phi + dy * 0.006))
        }
        lastMouse = { x: e.clientX, y: e.clientY }
        setTooltip(null)
        return
      }
      const rect = canvas.getBoundingClientRect()
      const ni = pickNearest(notePos, e, rect, noteAlive)
      hoverIdx = ni
      if (ni >= 0) {
        canvas.style.cursor = 'pointer'
        setTooltip(null) // 노트 이름은 팻말로 보여 준다
        return
      }
      const si = pickNearest(lightPos, e, rect, routeAlive, 12)
      if (si >= 0) {
        canvas.style.cursor = 'default'
        setTooltip({ title: `공유: ${routeVisuals[si].shared.join(', ')}`, x: e.clientX - rect.left, y: e.clientY - rect.top })
        return
      }
      canvas.style.cursor = 'grab'
      setTooltip(null)
    })

    canvas.addEventListener('pointerup', (e) => {
      pointerDown = false
      canvas.style.cursor = 'grab'
      if (!moved) {
        const ni = pickNearest(notePos, e, canvas.getBoundingClientRect(), noteAlive)
        if (ni >= 0) openNote(noteIds[ni]).then(() => setTab('edit'))
      }
    })

    canvas.addEventListener('pointerleave', () => { hoverIdx = -1; setTooltip(null) })

    canvas.addEventListener('wheel', (e) => {
      e.preventDefault()
      camTarget.r = Math.max(400, Math.min(maxZoom, camTarget.r * (e.deltaY < 0 ? 0.9 : 1.1)))
    }, { passive: false })

    // ── 노트 이름 팻말 ───────────────────────────────────────
    const signCandidates: { i: number; d: number }[] = []
    const signProj = new THREE.Vector3()
    function placeSign(sign: typeof signs[number], i: number, hover: boolean) {
      signProj.copy(notePos[i]).project(camera)
      if (signProj.z > 1 || Math.abs(signProj.x) > 1.1 || Math.abs(signProj.y) > 1.1) {
        sign.root.style.display = 'none'
        return
      }
      if (sign.idx !== i) {
        sign.idx = i
        sign.text.textContent = noteTitles[i]
        sign.root.style.setProperty('--sign-color', `#${noteColors[i].getHexString()}`)
      }
      const x = (signProj.x + 1) / 2 * el!.clientWidth
      const y = (1 - signProj.y) / 2 * el!.clientHeight
      sign.root.style.display = ''
      sign.root.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`
      sign.root.classList.toggle('is-hover', hover)
    }
    function updateSigns(nearFade: number) {
      // 확대했을 때(육각형이 보일 때) 카메라에서 가까운 행성부터 최대 SIGN.max개
      signCandidates.length = 0
      if (nearFade > 0) {
        notePos.forEach((p, i) => {
          if (!noteAlive[i] || i === hoverIdx || i === focusIdx) return
          const d = p.distanceTo(camera.position)
          if (d < SIGN.nearDist) signCandidates.push({ i, d })
        })
        signCandidates.sort((a, b) => a.d - b.d)
      }
      let used = 0
      if (hoverIdx >= 0 && noteAlive[hoverIdx]) placeSign(signs[used++], hoverIdx, true)
      if (focusIdx >= 0 && focusIdx !== hoverIdx && noteAlive[focusIdx]) placeSign(signs[used++], focusIdx, true)
      for (const c of signCandidates) {
        if (used >= signs.length) break
        placeSign(signs[used++], c.i, false)
      }
      for (let k = used; k < signs.length; k++) {
        signs[k].root.style.display = 'none'
        signs[k].idx = -1
      }
    }

    // ── 애니메이션 ───────────────────────────────────────────
    const clock = new THREE.Clock()
    const camRight = new THREE.Vector3()
    let animId: number
    function animate() {
      animId = requestAnimationFrame(animate)
      const dt = Math.min(clock.getDelta(), 0.1) // 탭 전환 후 복귀 시 한 번에 튀지 않게
      shared.uTime.value += dt

      // 배경별 반짝임 (별마다 제각각 가끔 밝기가 튐)
      const t = Date.now() * 0.0012
      updateTwinkle(starLayer, t)
      updateTwinkle(brightStarLayer, t)

      cam.theta += (camTarget.theta - cam.theta) * 0.08
      cam.phi += (camTarget.phi - cam.phi) * 0.08
      cam.r += (camTarget.r - cam.r) * 0.08
      // 검색한 행성은 공전 중이라 시선 중심이 계속 따라간다
      if (following && focusIdx >= 0) lookTarget.lerp(notePos[focusIdx], 0.08)
      updateCamera()
      const hexFade = THREE.MathUtils.clamp((HEX_FADE.far - cam.r) / (HEX_FADE.far - HEX_FADE.near), 0, 1)
      noteHexes.visible = hexFade > 0
      hexMat.opacity = HEX_FADE.opacity * hexFade

      applyTimeline()

      updateSigns(hexFade)
      camRight.setFromMatrixColumn(camera.matrixWorld, 0)
      galaxies.forEach(g => g.title.position.copy(g.group.position).addScaledVector(camRight, g.R * 0.12))
      updateNotePositions()
      syncNoteBuffers()
      updateConstellationLines()
      updateRoutes()

      composer.render()
      // 라벨·마커는 bloom 없이 최종 화면 위에 덧그린다
      renderer.autoClear = false
      camera.layers.set(OVERLAY_LAYER)
      renderer.render(scene, camera)
      camera.layers.set(0)
      renderer.autoClear = true
    }
    animate()

    // 검색 상자와 연결 — 필터를 풀고 씬을 다시 만든 경우 기다리던 행성으로 바로 날아간다
    flyToRef.current = flyTo
    if (pendingFlyRef.current && flyTo(pendingFlyRef.current)) pendingFlyRef.current = null

    const obs = new ResizeObserver(() => {
      const w = el.clientWidth
      const h = el.clientHeight
      renderer.setSize(w, h)
      composer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      updateSizeScale()
    })
    obs.observe(el)

    return () => {
      flyToRef.current = null
      routesCancelled = true
      cancelAnimationFrame(animId)
      obs.disconnect()
      disposables.forEach(d => d.dispose())
      scene.traverse(obj => {
        const mesh = obj as THREE.Mesh
        mesh.geometry?.dispose()
        const material = mesh.material
        // 재질 dispose는 텍스처를 해제하지 않으므로 라벨·코어 캔버스 텍스처(map)도 함께 해제
        const mats = Array.isArray(material) ? material : material ? [material] : []
        mats.forEach(m => { (m as THREE.SpriteMaterial).map?.dispose(); m.dispose() })
      })
      renderer.dispose()
      try { el.removeChild(canvas) } catch { /* */ }
      signLayer.remove()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories, notes, starMapFilter, constellationNoteIds])

  // ── HUD 데이터 ──
  const countByCat = new Map<string, number>()
  notes.forEach(n => { if (n.category_id) countByCat.set(n.category_id, (countByCat.get(n.category_id) ?? 0) + 1) })
  const uncategorizedCount = notes.filter(n => !n.category_id).length
  const focusedCat = starMapFilter?.type === 'category' ? categories.find(c => c.id === starMapFilter.value) : undefined
  const hudTitle = focusedCat ? focusedCat.name : starMapFilter?.type === 'constellation' ? `✧ ${starMapFilter.label}` : '전체 성도'
  const constellationNotes = starMapFilter?.type === 'constellation' && constellationNoteIds
    ? notes.filter(n => constellationNoteIds.has(n.id))
    : null
  const hudSub = focusedCat
    ? `노트 ${countByCat.get(focusedCat.id) ?? 0}개`
    : constellationNotes
      ? `별자리 · 노트 ${constellationNotes.length}개, 은하 ${new Set(constellationNotes.map(n => n.category_id).filter(Boolean)).size}개`
      : `노트 ${notes.length}개, 은하 ${categories.length}개`

  const timelineValue = timeline ?? timeRange?.max ?? 0
  const timelineCount = timeline === null ? notes.length : notes.filter(n => (births.get(n.id) ?? 0) <= timeline).length
  const formatDate = (t: number) => new Date(t).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' })

  return (
    // 성도는 라이트 모드에서도 밤하늘 — 다크 토큰을 강제 적용
    <div className="dark sn-starmap" style={{ position: 'relative', width: '100%', height: '100%' }}>
      {/* 캔버스는 화면 전체에 깔고, 사이드바·탭 바는 그 위에 유리 패널로 뜬다.
          범례 등 HUD는 이 루트(메인 영역) 기준으로 남는다. */}
      <div
        ref={containerRef}
        style={{ position: 'fixed', inset: 0, zIndex: 0, background: '#060b16', overflow: 'hidden' }}
      />

      {/* 성도 범례 */}
      <section className="sn-atlas" aria-label="성도 범례">
        <button
          className="sn-atlas-head"
          onClick={toggleLegend}
          aria-expanded={legendOpen}
          title={legendOpen ? '범례 접기' : '범례 펼치기'}
        >
          <span className="sn-atlas-titles">
            <h2>{hudTitle}</h2>
            <p>{hudSub}</p>
          </span>
          <span className="sn-atlas-caret" aria-hidden="true">{legendOpen ? '▴' : '▾'}</span>
        </button>
        {legendOpen && <>
        <ul className="sn-atlas-list">
          {categories.map(cat => {
            const active = focusedCat?.id === cat.id
            return (
              <li key={cat.id}>
                <button
                  className="sn-atlas-item"
                  aria-pressed={active}
                  onClick={() => setStarMapFilter(active ? null : { type: 'category', value: cat.id })}
                  title={active ? '전체 성도로 돌아가기' : `${cat.name} 은하로 이동`}
                >
                  <span className="sn-atlas-dot" style={{ background: cat.color ?? '#94a3b8', color: cat.color ?? '#94a3b8' }} />
                  <span className="sn-atlas-name">{cat.name}</span>
                  <span className="sn-atlas-count">{countByCat.get(cat.id) ?? 0}</span>
                </button>
              </li>
            )
          })}
          {uncategorizedCount > 0 && !focusedCat && (
            <li>
              <div className="sn-atlas-item is-static">
                <span className="sn-atlas-dot is-rogue" />
                <span className="sn-atlas-name">떠돌이 행성 (미분류)</span>
                <span className="sn-atlas-count">{uncategorizedCount}</span>
              </div>
            </li>
          )}
        </ul>
        {starMapFilter && (
          <button className="sn-atlas-reset" onClick={() => setStarMapFilter(null)}>
            전체 성도 보기
          </button>
        )}
        </>}
      </section>

      {/* 행성 검색 — 고르면 카메라가 그 행성 가까이 날아간다 */}
      <div className="sn-starsearch" role="search">
        <input
          type="search"
          value={searchQuery}
          placeholder="행성 검색"
          aria-label="성도에서 노트 검색"
          aria-expanded={searchOpen && searchMatches.length > 0}
          aria-controls="sn-starsearch-list"
          onChange={e => { setSearchQuery(e.target.value); setSearchOpen(true); setSearchActive(0) }}
          onFocus={() => setSearchOpen(true)}
          onBlur={() => setSearchOpen(false)}
          onKeyDown={onSearchKey}
        />
        {searchOpen && searchQuery.trim() && (
          searchMatches.length > 0 ? (
            <ul id="sn-starsearch-list" role="listbox">
              {searchMatches.map((n, i) => {
                const cat = categories.find(c => c.id === n.category_id)
                return (
                  <li key={n.id} role="option" aria-selected={i === searchActive}>
                    <button
                      className="sn-starsearch-item"
                      // 입력창 blur보다 먼저 처리되도록 mousedown에서 기본 동작을 막는다
                      onMouseDown={e => e.preventDefault()}
                      onMouseEnter={() => setSearchActive(i)}
                      onClick={() => selectSearch(n)}
                    >
                      <span className="sn-atlas-dot" style={{ background: cat?.color ?? '#94a3b8', color: cat?.color ?? '#94a3b8' }} />
                      <span className="sn-starsearch-title">{n.title}</span>
                      <span className="sn-starsearch-cat">{cat?.name ?? '떠돌이'}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="sn-starsearch-empty">찾는 행성이 없습니다</p>
          )
        )}
      </div>

      {/* 우주의 역사 — 첫 노트부터 최신 노트까지 은하가 자라고 우주가 팽창한다 */}
      {timeRange && timeRange.max > timeRange.min && (
        <section className="sn-timeline" aria-label="우주의 역사">
          <div className="sn-timeline-head">
            <span>{timeline === null ? '현재 우주' : formatDate(timelineValue)}</span>
            <span className="sn-timeline-count">노트 {timelineCount}개</span>
          </div>
          <input
            type="range"
            min={timeRange.min}
            max={timeRange.max}
            step={Math.max(1, (timeRange.max - timeRange.min) / 1000)}
            value={timelineValue}
            onChange={e => changeTimeline(Number(e.target.value))}
            aria-label="노트 생성 시점"
            aria-valuetext={timeline === null ? '현재' : formatDate(timelineValue)}
          />
          <div className="sn-timeline-ends">
            <span>{formatDate(timeRange.min)}</span>
            <span>{formatDate(timeRange.max)}</span>
          </div>
        </section>
      )}

      {tooltip && (
        <div className="sn-star-tip" style={{ left: tooltip.x + 16, top: tooltip.y - 40 }}>
          {tooltip.title}
        </div>
      )}

      {/* 앵커(크기 0) 위치가 알약의 중심. 클릭은 막고, 굴절·늘어남은 캔버스 위 마우스를 따른다 */}
      <div className="sn-controls" aria-hidden="true" style={{ pointerEvents: 'none' }}>
        <LiquidGlass
          cornerRadius={999}
          padding="8px 18px"
          displacementScale={48}
          elasticity={0.2}
          mouseContainer={containerRef}
          style={{ position: 'absolute', top: '0px', left: '0px' }}
        >
          <span className="sn-controls-text">
            <span><kbd>드래그</kbd> 회전</span>
            <span><kbd>Ctrl</kbd>+<kbd>드래그</kbd> 이동</span>
            <span><kbd>스크롤</kbd> 확대</span>
            <span><kbd>클릭</kbd> 노트 열기</span>
          </span>
        </LiquidGlass>
      </div>
    </div>
  )
}
