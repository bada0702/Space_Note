import { useEffect, useMemo, useState } from 'react'
import { constellationsApi } from '../../api/constellationsApi'
import { useNotesStore } from '../../store/notesStore'
import type { ConstellationGraph as Graph, ConstellationGraphEdge } from '../../types'

// 별자리 개념을 가운데 두고 관계로 이어진 개념을 원형으로 둘러 그린다.
// 선 중간에 관계 이름을 적고, 선을 누르면 근거 문장과 출처 노트를 보여 준다.

const W = 560
const H = 460
const RING = 170
const MARGIN = 40
const MIN_FROM_CENTER = 110
const NODE_R = 7
const CENTER_R = 11
const PARALLEL_GAP = 26 // 같은 두 개념 사이에 관계가 여럿이면 곡선으로 벌린다

interface Props {
  conceptId: string
}

interface Placed {
  x: number
  y: number
}

function short(name: string, max = 12) {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name
}

export default function ConstellationGraph({ conceptId }: Props) {
  const { openNote, setTab } = useNotesStore()
  const [graph, setGraph] = useState<Graph | null>(null)
  const [error, setError] = useState(false)
  const [open, setOpen] = useState(true)
  const [selected, setSelected] = useState<number | null>(null)

  useEffect(() => {
    let alive = true
    setGraph(null); setError(false); setSelected(null)
    constellationsApi.graph(conceptId)
      .then(g => { if (alive) setGraph(g) })
      .catch(() => { if (alive) setError(true) })
    return () => { alive = false }
  }, [conceptId])

  const layout = useMemo(() => {
    if (!graph) return null
    const pos = new Map<string, Placed>()
    pos.set(graph.center.id, { x: W / 2, y: H / 2 })
    const ring = graph.nodes.filter(n => n.id !== graph.center.id)
    ring.forEach((n, i) => {
      const a = (i / ring.length) * Math.PI * 2 - Math.PI / 2
      pos.set(n.id, { x: W / 2 + RING * Math.cos(a), y: H / 2 + RING * Math.sin(a) })
    })
    // 원형 배치에서 출발해 반발력·용수철로 다듬는다. 이웃끼리 이어진 개념은 서로 가까워져
    // 선이 가운데를 가로지르지 않는다. 중심 개념은 고정하고, 결정적이라 매번 같은 모양이 나온다.
    const linked = graph.edges.map(e => [e.source, e.target] as const)
    for (let step = 0; step < 300; step++) {
      const cool = 1 - step / 300
      const force = new Map(ring.map(n => [n.id, { x: 0, y: 0 }]))
      const push = (id: string, fx: number, fy: number) => {
        const f = force.get(id) // 중심 개념은 force에 없어서 움직이지 않는다
        if (f) { f.x += fx; f.y += fy }
      }
      for (let i = 0; i < graph.nodes.length; i++) {
        for (let j = i + 1; j < graph.nodes.length; j++) {
          const a = pos.get(graph.nodes[i].id)!, b = pos.get(graph.nodes[j].id)!
          const dx = a.x - b.x, dy = a.y - b.y
          const d2 = Math.max(dx * dx + dy * dy, 25)
          const f = 16000 / d2
          const d = Math.sqrt(d2)
          push(graph.nodes[i].id, (dx / d) * f, (dy / d) * f)
          push(graph.nodes[j].id, -(dx / d) * f, -(dy / d) * f)
        }
      }
      for (const [s, t] of linked) {
        const a = pos.get(s)!, b = pos.get(t)!
        const dx = b.x - a.x, dy = b.y - a.y
        const d = Math.hypot(dx, dy) || 1
        const rest = s === graph.center.id || t === graph.center.id ? RING : RING * 0.7
        const f = (d - rest) * 0.04
        push(s, (dx / d) * f, (dy / d) * f)
        push(t, -(dx / d) * f, -(dy / d) * f)
      }
      force.forEach((f, id) => {
        const p = pos.get(id)!
        const len = Math.hypot(f.x, f.y) || 1
        const move = Math.min(len, 12 * cool + 0.5)
        p.x = Math.min(W - MARGIN, Math.max(MARGIN, p.x + (f.x / len) * move))
        p.y = Math.min(H - MARGIN, Math.max(MARGIN / 2, p.y + (f.y / len) * move))
        // 중심 개념 가까이로 끌려 들어가 겹치지 않게 최소 거리를 둔다
        const cx = p.x - W / 2, cy = p.y - H / 2
        const r = Math.hypot(cx, cy) || 1
        if (r < MIN_FROM_CENTER) { p.x = W / 2 + (cx / r) * MIN_FROM_CENTER; p.y = H / 2 + (cy / r) * MIN_FROM_CENTER }
      })
    }
    const byPair = new Map<string, number[]>()
    graph.edges.forEach((e, i) => {
      const key = [e.source, e.target].sort().join('|')
      byPair.set(key, [...(byPair.get(key) ?? []), i])
    })
    const edges = graph.edges.map((e, i) => {
      const a = pos.get(e.source)!
      const b = pos.get(e.target)!
      const siblings = byPair.get([e.source, e.target].sort().join('|'))!
      // 쌍 안의 순서로 벌리되, 방향이 반대인 관계도 같은 쪽 기준으로 계산되도록 정렬된 끝점을 쓴다
      const [p, q] = e.source < e.target ? [a, b] : [b, a]
      const offset = (siblings.indexOf(i) - (siblings.length - 1) / 2) * PARALLEL_GAP
      const dx = q.x - p.x, dy = q.y - p.y
      const len = Math.hypot(dx, dy) || 1
      const nx = -dy / len, ny = dx / len
      const cx = (a.x + b.x) / 2 + nx * offset * 2
      const cy = (a.y + b.y) / 2 + ny * offset * 2
      // 2차 베지어의 t=0.5 지점 = 선의 한가운데
      const mx = 0.25 * a.x + 0.5 * cx + 0.25 * b.x
      const my = 0.25 * a.y + 0.5 * cy + 0.25 * b.y
      // 화살촉이 노드 원에 가리지 않도록 끝점을 반지름만큼 당긴다
      const endR = (e.target === graph.center.id ? CENTER_R : NODE_R) + 3
      const tx = b.x - cx, ty = b.y - cy
      const tl = Math.hypot(tx, ty) || 1
      const path = `M${a.x},${a.y} Q${cx},${cy} ${b.x - (tx / tl) * endR},${b.y - (ty / tl) * endR}`
      return { e, path, mx, my }
    })
    return { pos, edges }
  }, [graph])

  const sel: ConstellationGraphEdge | null = selected !== null && graph ? graph.edges[selected] : null
  const nameOf = (id: string) => graph?.nodes.find(n => n.id === id)?.name ?? id

  return (
    <section className="sn-cgraph" aria-label="별자리 관계도">
      <button className="sn-cgraph-head" onClick={() => setOpen(o => !o)} aria-expanded={open}>
        <span>관계도{graph ? ` · 개념 ${graph.nodes.length}개, 관계 ${graph.edges.length}개` : ''}</span>
        <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="sn-cgraph-body">
          {error && <p className="sn-cgraph-empty">관계도를 불러오지 못했습니다</p>}
          {!error && !graph && <p className="sn-cgraph-empty">불러오는 중…</p>}
          {graph && layout && graph.edges.length === 0 && (
            <p className="sn-cgraph-empty">이 개념과 이어진 관계가 아직 없습니다</p>
          )}
          {graph && layout && graph.edges.length > 0 && (
            <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${graph.center.name} 관계도`}>
              <defs>
                <marker id="sn-cgraph-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className="sn-cgraph-arrowhead" />
                </marker>
              </defs>
              {layout.edges.map(({ e, path }, i) => (
                <path
                  key={`l${i}`}
                  d={path}
                  className={`sn-cgraph-edge${selected === i ? ' is-selected' : ''}`}
                  markerEnd="url(#sn-cgraph-arrow)"
                  onClick={() => setSelected(selected === i ? null : i)}
                >
                  <title>{`${nameOf(e.source)} –${e.pred}→ ${nameOf(e.target)}`}</title>
                </path>
              ))}
              {graph.nodes.map(n => {
                const p = layout.pos.get(n.id)!
                const isCenter = n.id === graph.center.id
                return (
                  <g key={n.id} transform={`translate(${p.x},${p.y})`}>
                    <circle r={isCenter ? CENTER_R : NODE_R} className={`sn-cgraph-node${isCenter ? ' is-center' : ''}`} />
                    <text y={(isCenter ? CENTER_R : NODE_R) + 13} textAnchor="middle" className="sn-cgraph-name">
                      {short(n.name)}
                      <title>{`${n.name} (${n.type})`}</title>
                    </text>
                  </g>
                )
              })}
              {layout.edges.map(({ e, mx, my }, i) => (
                <text
                  key={`t${i}`}
                  x={mx}
                  y={my}
                  dy="0.35em"
                  textAnchor="middle"
                  className={`sn-cgraph-pred${selected === i ? ' is-selected' : ''}`}
                  onClick={() => setSelected(selected === i ? null : i)}
                >
                  {e.pred}
                </text>
              ))}
            </svg>
          )}
          {sel && (
            <div className="sn-cgraph-detail">
              <p className="sn-cgraph-triple">
                {nameOf(sel.source)} <b>–{sel.pred}→</b> {nameOf(sel.target)}
              </p>
              {sel.evidence
                ? <blockquote>{sel.evidence}</blockquote>
                : <p className="sn-cgraph-empty">근거 문장 없음</p>}
              <ul>
                {sel.notes.map(n => (
                  <li key={n.id}>
                    <button onClick={() => openNote(n.id).then(() => setTab('edit'))}>{n.title}</button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
