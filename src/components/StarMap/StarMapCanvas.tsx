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
  speed: number
  angle: number
  inclination: number
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

// 행성 팔레트 (목성, 금성, 지구, 화성, 해왕성, 토성, 천왕성, 분홍거성)
const PLANET_PALETTES = [
  { base: 0xd4956a, ring: 0x9a5020 },
  { base: 0xe8d580, ring: 0xb09030 },
  { base: 0x5a90e0, ring: 0x2050a0 },
  { base: 0xd04040, ring: 0x882020 },
  { base: 0x90b8e0, ring: 0x4070a0 },
  { base: 0xd8b870, ring: 0x907030 },
  { base: 0x60d8d0, ring: 0x2090a0 },
  { base: 0xe0a0d8, ring: 0xa060a0 },
]

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

    // 표시 대상 필터링
    const visibleNotes = starMapFilter
      ? notes.filter(n => n.category_id === starMapFilter)
      : notes
    const visibleCats = starMapFilter
      ? categories.filter(c => c.id === starMapFilter)
      : categories

    // ── Scene ────────────────────────────────────────────────
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x020408)
    scene.fog = new THREE.FogExp2(0x020408, 0.0005)

    // 카메라 초점 (필터 시 해당 항성 위치)
    let lookTarget = new THREE.Vector3(0, 0, 0)
    let initCamR = 400
    if (starMapFilter) {
      const ci = categories.findIndex(c => c.id === starMapFilter)
      if (ci >= 0) lookTarget = STAR_POSITIONS[ci % STAR_POSITIONS.length].clone()
      initCamR = 220
    }

    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 3000)
    camera.position.set(lookTarget.x, lookTarget.y + 80, lookTarget.z + initCamR)
    camera.lookAt(lookTarget)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(window.devicePixelRatio)
    el.appendChild(renderer.domElement)
    renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;cursor:grab;'

    // ── 조명 ─────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0x1a2244, 0.8))
    const mainLight = new THREE.DirectionalLight(0xfff4e8, 1.3)
    mainLight.position.set(200, 180, 100)
    scene.add(mainLight)
    const fillLight = new THREE.DirectionalLight(0x334488, 0.35)
    fillLight.position.set(-200, -100, -150)
    scene.add(fillLight)

    // ── 배경 파티클 ──────────────────────────────────────────
    const bgPos = new Float32Array(3000 * 3)
    for (let i = 0; i < 3000; i++) {
      bgPos[i * 3]     = (Math.random() - 0.5) * 2600
      bgPos[i * 3 + 1] = (Math.random() - 0.5) * 2600
      bgPos[i * 3 + 2] = (Math.random() - 0.5) * 2600
    }
    const bgGeo = new THREE.BufferGeometry()
    bgGeo.setAttribute('position', new THREE.BufferAttribute(bgPos, 3))
    scene.add(new THREE.Points(bgGeo, new THREE.PointsMaterial({
      color: 0xffffff, size: 0.6, sizeAttenuation: true,
      transparent: true, opacity: 0.42, depthWrite: false,
    })))

    // ── 항성 (카테고리) ──────────────────────────────────────
    const glowTex = makeGlowTexture()
    const sunDatas: SunData[] = []

    visibleCats.forEach(cat => {
      const ci = categories.findIndex(c => c.id === cat.id)
      const pos = STAR_POSITIONS[ci % STAR_POSITIONS.length]
      const color = new THREE.Color(cat.color)
      const noteCount = visibleNotes.filter(n => n.category_id === cat.id).length

      // 항성 크기 (노트 수에 따라 약간 변동)
      const sunR = Math.max(5, 4 + noteCount * 0.25)

      // 항성 본체 (자체 발광 - BasicMaterial)
      const sunMesh = new THREE.Mesh(
        new THREE.SphereGeometry(sunR, 24, 18),
        new THREE.MeshBasicMaterial({ color }),
      )
      sunMesh.position.copy(pos)

      // 항성 코어 (더 밝은 흰색 중심)
      const coreMesh = new THREE.Mesh(
        new THREE.SphereGeometry(sunR * 0.55, 16, 12),
        new THREE.MeshBasicMaterial({ color: 0xffffff }),
      )
      coreMesh.material.transparent = true
      coreMesh.material.opacity = 0.35
      sunMesh.add(coreMesh)

      // 근거리 글로우
      const innerGlow = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTex, color,
        transparent: true, opacity: 0.9,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      innerGlow.scale.setScalar(sunR * 5.5)
      sunMesh.add(innerGlow)

      // 원거리 코로나 글로우
      const coronaGlowScale = sunR * 12
      const coronaGlow = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTex, color,
        transparent: true, opacity: 0.28,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      coronaGlow.scale.setScalar(coronaGlowScale)
      sunMesh.add(coronaGlow)

      // 카테고리 이름 레이블
      const label = makeLabelSprite(cat.name, color)
      label.position.set(0, sunR + 6, 0)
      sunMesh.add(label)

      // 은하 성운 배경 (항성 주변 확산 빛)
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

    // ── 노트 행성 ────────────────────────────────────────────
    const starMeshes: THREE.Mesh[] = []
    const orbits: OrbitData[] = []
    const noteIds: string[] = []

    visibleNotes.forEach((note, i) => {
      const catIdx = categories.findIndex(c => c.id === note.category_id)
      const center = (catIdx >= 0
        ? STAR_POSITIONS[catIdx % STAR_POSITIONS.length]
        : new THREE.Vector3(0, 0, 0)
      ).clone()
      const catColor = catIdx >= 0
        ? new THREE.Color(categories[catIdx].color)
        : new THREE.Color(0x6688aa)

      // 행성 타입: 0=가스거성(큰링), 1=얼음거성(작은링), 2=암석행성(링없음)
      const pType = i % 3
      const pal = PLANET_PALETTES[i % PLANET_PALETTES.length]
      const planetR = pType === 0 ? 3.8 : pType === 1 ? 3.2 : 2.5

      // 행성 본체 (MeshPhongMaterial → 조명/그림자 반응)
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(planetR, 16, 12),
        new THREE.MeshPhongMaterial({
          color: new THREE.Color(pal.base),
          emissive: catColor.clone().multiplyScalar(0.1),
          shininess: 55,
          specular: new THREE.Color(0x334455),
        }),
      )

      // 행성 링 (가스·얼음거성)
      if (pType <= 1) {
        const rMid = planetR + (pType === 0 ? 4.8 : 3.5)
        const rTube = pType === 0 ? 0.72 : 0.42
        const ring = new THREE.Mesh(
          new THREE.TorusGeometry(rMid, rTube, 4, 44),
          new THREE.MeshBasicMaterial({
            color: new THREE.Color(pal.ring),
            transparent: true, opacity: pType === 0 ? 0.78 : 0.58,
          }),
        )
        ring.rotation.x = 0.85 + (i % 5) * 0.12
        ring.rotation.z = (i % 7) * 0.08
        mesh.add(ring)
      }

      // 행성 대기 글로우 스프라이트
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: glowTex, color: catColor,
        transparent: true, opacity: 0.55,
        depthWrite: false, blending: THREE.AdditiveBlending,
      }))
      sprite.scale.setScalar(planetR * 5.5)
      mesh.add(sprite)

      // 공전 파라미터 (항성 반경보다 충분히 큰 거리부터 시작)
      const sunR = Math.max(5, 4 + visibleNotes.filter(n => n.category_id === note.category_id).length * 0.25)
      const orbRadius = sunR + 20 + (i % visibleNotes.length) / visibleNotes.length * 60 + Math.random() * 15
      const angle = (i * 2.399963) % (Math.PI * 2)  // 황금각 분산
      const inclination = (Math.random() - 0.5) * Math.PI * 0.65
      const speed = (0.0003 + Math.random() * 0.0006) * (Math.random() < 0.5 ? 1 : -1)

      mesh.position.set(
        center.x + orbRadius * Math.cos(angle),
        center.y + orbRadius * Math.sin(angle) * Math.cos(inclination),
        center.z + orbRadius * Math.sin(angle) * Math.sin(inclination),
      )

      scene.add(mesh)
      starMeshes.push(mesh)
      orbits.push({
        center, radius: orbRadius, speed, angle, inclination,
        selfRotY: 0.012 + Math.random() * 0.02,
      })
      noteIds.push(note.id)
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
      camR = Math.max(40, Math.min(1000, camR + e.deltaY * 0.5))
      updateCamera()
    }, { passive: false })

    // ── 애니메이션 ───────────────────────────────────────────
    let animId: number
    function animate() {
      animId = requestAnimationFrame(animate)
      const t = Date.now() * 0.0012

      // 항성 자전 + 코로나 맥동
      sunDatas.forEach(s => {
        s.mesh.rotation.y += 0.003
        const pulse = 1 + Math.sin(t + s.phase) * 0.1
        s.glow.scale.setScalar(s.glowBase * pulse)
      })

      // 행성 공전 + 자전
      starMeshes.forEach((mesh, i) => {
        const od = orbits[i]
        od.angle += od.speed
        mesh.position.set(
          od.center.x + od.radius * Math.cos(od.angle),
          od.center.y + od.radius * Math.sin(od.angle) * Math.cos(od.inclination),
          od.center.z + od.radius * Math.sin(od.angle) * Math.sin(od.inclination),
        )
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
      renderer.dispose()
      try { el.removeChild(canvas) } catch { /* */ }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories, notes, starMapFilter])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%', background: '#020408', overflow: 'hidden' }}
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
