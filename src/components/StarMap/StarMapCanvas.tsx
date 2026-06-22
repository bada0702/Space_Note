import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { useCategoriesStore } from '../../store/categoriesStore'
import { useNotesStore } from '../../store/notesStore'

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
}

interface SunData {
  mesh: THREE.Mesh
  glow: THREE.Sprite
  glowBase: number
  phase: number
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
    name: 'jupiter', size: 4.7, ring: null,
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
    name: 'saturn', size: 4.3, ring: 'saturn',
    paint: (c, w, h) => paintBands(c, w, h, [
      [228, 206, 158], [240, 226, 190], [214, 188, 140], [236, 220, 182], [206, 178, 130],
    ], 150, 0.12),
  },
  {
    name: 'venus', size: 3.1, ring: null,
    paint: (c, w, h) => paintBands(c, w, h, [
      [232, 206, 150], [246, 228, 184], [220, 188, 132], [240, 218, 168], [226, 198, 144],
    ], 320, 0.22),
  },
  {
    name: 'earth', size: 3.1, ring: null,
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
    name: 'mars', size: 2.6, ring: null,
    paint: (c, w, h) => {
      paintBands(c, w, h, [[196, 108, 66], [176, 92, 56], [206, 122, 78], [168, 84, 52]], 80, 0.1)
      blobs(c, w, h, 26, [128, 62, 40], w * 0.02, w * 0.06, 0.5)
      polarCaps(c, w, h, 0.07)
    },
  },
  {
    name: 'neptune', size: 3.7, ring: null,
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
    name: 'uranus', size: 3.6, ring: 'uranus',
    paint: (c, w, h) => paintBands(c, w, h, [
      [150, 214, 214], [180, 230, 226], [136, 200, 202], [172, 224, 220],
    ], 50, 0.06),
  },
  {
    name: 'mercury', size: 2.3, ring: null,
    paint: (c, w, h) => {
      paintBands(c, w, h, [[126, 116, 104], [150, 140, 126], [110, 102, 92]], 40, 0.08)
      blobs(c, w, h, 40, [80, 74, 66], w * 0.008, w * 0.03, 0.5)
      blobs(c, w, h, 24, [180, 172, 158], w * 0.006, w * 0.02, 0.4)
    },
  },
]

function makePlanetTexture(kind: PlanetKind): THREE.Texture {
  const w = 512
  const h = 256
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

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const width = el.clientWidth || 800
    const height = el.clientHeight || 600
    const disposables: { dispose: () => void }[] = []

    // 표시 대상 필터링
    const visibleNotes = starMapFilter
      ? notes.filter(n => n.category_id === starMapFilter)
      : notes
    const visibleCats = starMapFilter
      ? categories.filter(c => c.id === starMapFilter)
      : categories

    // ── Scene ────────────────────────────────────────────────
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x02030a)
    scene.fog = new THREE.FogExp2(0x02030a, 0.0004)

    // 카메라 초점 (필터 시 해당 항성 위치)
    let lookTarget = new THREE.Vector3(0, 0, 0)
    let initCamR = 400
    if (starMapFilter) {
      const ci = categories.findIndex(c => c.id === starMapFilter)
      if (ci >= 0) lookTarget = STAR_POSITIONS[ci % STAR_POSITIONS.length].clone()
      initCamR = 220
    }

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 6000)
    camera.position.set(lookTarget.x, lookTarget.y + 80, lookTarget.z + initCamR)
    camera.lookAt(lookTarget)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    el.appendChild(renderer.domElement)
    renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;cursor:grab;'

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
    ]
    nebulaSpecs.forEach(([r, g, b, pos, sc]) => {
      const tex = makeNebulaTexture(r, g, b)
      disposables.push(tex)
      const mat = new THREE.SpriteMaterial({
        map: tex, transparent: true, opacity: 0.12,
        depthWrite: false, blending: THREE.AdditiveBlending,
      })
      const spr = new THREE.Sprite(mat)
      spr.position.copy(pos)
      spr.scale.setScalar(sc)
      scene.add(spr)
    })

    // ── 별하늘 (색·크기 다양 + 밝은 별 레이어) ────────────────
    function buildStars(count: number, spread: number, size: number, opacity: number, bright: boolean) {
      const pos = new Float32Array(count * 3)
      const col = new Float32Array(count * 3)
      const tint = new THREE.Color()
      for (let i = 0; i < count; i++) {
        pos[i * 3] = (Math.random() - 0.5) * spread
        pos[i * 3 + 1] = (Math.random() - 0.5) * spread
        pos[i * 3 + 2] = (Math.random() - 0.5) * spread
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
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
      const mat = new THREE.PointsMaterial({
        size, sizeAttenuation: true, vertexColors: true,
        transparent: true, opacity, depthWrite: false,
      })
      const pts = new THREE.Points(geo, mat)
      scene.add(pts)
      return mat
    }
    buildStars(4200, 3000, 0.7, 0.75, false)
    const brightStarMat = buildStars(220, 2800, 2.1, 0.95, true)

    // ── 항성 (카테고리) ──────────────────────────────────────
    const glowTex = makeGlowTexture()
    disposables.push(glowTex)
    const sunDatas: SunData[] = []

    visibleCats.forEach(cat => {
      const ci = categories.findIndex(c => c.id === cat.id)
      const pos = STAR_POSITIONS[ci % STAR_POSITIONS.length]
      const color = new THREE.Color(cat.color)
      const noteCount = visibleNotes.filter(n => n.category_id === cat.id).length

      const sunR = Math.max(5, 4 + noteCount * 0.25)

      const sunMesh = new THREE.Mesh(
        new THREE.SphereGeometry(sunR, 24, 18),
        new THREE.MeshBasicMaterial({ color }),
      )
      sunMesh.position.copy(pos)

      const coreMesh = new THREE.Mesh(
        new THREE.SphereGeometry(sunR * 0.55, 16, 12),
        new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 }),
      )
      sunMesh.add(coreMesh)

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

    // 카테고리별로 노트를 묶어 같은 평면에서 동심원 궤도(태양계 형태)로 배치
    let kindCounter = 0
    visibleCats.forEach(cat => {
      const ci = categories.findIndex(c => c.id === cat.id)
      const center = STAR_POSITIONS[ci % STAR_POSITIONS.length].clone()
      const catColor = new THREE.Color(cat.color)
      const catNotes = visibleNotes.filter(n => n.category_id === cat.id)
      if (catNotes.length === 0) return

      const sunR = Math.max(5, 4 + catNotes.length * 0.25)

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

        // 고리
        if (kind.ring) {
          const rInner = planetR * 1.4
          const rOuter = planetR * (kind.ring === 'saturn' ? 2.3 : 1.9)
          const ring = new THREE.Mesh(
            makeRingGeometry(rInner, rOuter),
            new THREE.MeshBasicMaterial({
              map: ringTex, transparent: true,
              opacity: kind.ring === 'saturn' ? 0.9 : 0.5,
              side: THREE.DoubleSide, depthWrite: false,
            }),
          )
          ring.rotation.x = kind.ring === 'saturn' ? Math.PI / 2 - 0.45 : 0.25
          mesh.add(ring)
        }

        // 대기 림 글로우 (카테고리 색으로 은은하게 — 소속 단서)
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
          map: glowTex, color: catColor,
          transparent: true, opacity: 0.32,
          depthWrite: false, blending: THREE.AdditiveBlending,
        }))
        sprite.scale.setScalar(planetR * 3.4)
        mesh.add(sprite)

        // 동심원 궤도 반경 (안쪽부터 바깥쪽으로 일정 간격)
        const radius = sunR + 16 + j * 12 + (j % 2) * 2.5
        const angle = (j * 2.399963) % (Math.PI * 2) // 황금각으로 시작각 분산

        // 케플러식: 안쪽일수록 빠르게, 모두 같은 방향(순행)으로 공전
        const speed = 1.1 / Math.pow(radius, 1.5)

        const p = center.clone()
          .addScaledVector(e1, radius * Math.cos(angle))
          .addScaledVector(e2, radius * Math.sin(angle))
        mesh.position.copy(p)

        // 희미한 궤도 선 (태양계 느낌 강화)
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
        const orbitLine = new THREE.Line(
          orbitGeo,
          new THREE.LineBasicMaterial({
            color: catColor, transparent: true, opacity: 0.12, depthWrite: false,
          }),
        )
        scene.add(orbitLine)

        scene.add(mesh)
        starMeshes.push(mesh)
        spinners.push(mesh)
        orbits.push({
          center, radius, e1, e2, angle, speed,
          selfRotY: 0.004 + (j % 4) * 0.004,
        })
        noteIds.push(note.id)
      })
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
      const hits = raycaster.intersectObjects(starMeshes, false)
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
        theta -= dx * 0.006
        phi = Math.max(0.12, Math.min(Math.PI - 0.12, phi + dy * 0.006))
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
      camR = Math.max(40, Math.min(1200, camR + e.deltaY * 0.5))
      updateCamera()
    }, { passive: false })

    // ── 애니메이션 ───────────────────────────────────────────
    let animId: number
    function animate() {
      animId = requestAnimationFrame(animate)
      const t = Date.now() * 0.0012

      // 밝은 별 반짝임
      brightStarMat.opacity = 0.78 + Math.sin(t * 2.2) * 0.17

      sunDatas.forEach(s => {
        s.mesh.rotation.y += 0.003
        const pulse = 1 + Math.sin(t + s.phase) * 0.1
        s.glow.scale.setScalar(s.glowBase * pulse)
      })

      spinners.forEach((mesh, i) => {
        const od = orbits[i]
        od.angle += od.speed
        mesh.position.copy(od.center)
          .addScaledVector(od.e1, od.radius * Math.cos(od.angle))
          .addScaledVector(od.e2, od.radius * Math.sin(od.angle))
        mesh.rotation.y += od.selfRotY
      })

      renderer.render(scene, camera)
    }
    animate()

    const obs = new ResizeObserver(() => {
      const w = el.clientWidth
      const h = el.clientHeight
      renderer.setSize(w, h)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
    })
    obs.observe(el)

    return () => {
      cancelAnimationFrame(animId)
      obs.disconnect()
      disposables.forEach(d => d.dispose())
      renderer.dispose()
      try { el.removeChild(canvas) } catch { /* */ }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories, notes, starMapFilter])

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
        {starMapFilter ? '현재 은하 성도' : '전체 성도'} · 드래그 회전 · 스크롤 줌 · 클릭으로 노트 열기
      </div>
    </div>
  )
}
