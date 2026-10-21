import type { RouteRelation } from '../types'

/** 항로 근거를 한 줄로 — "FAISS —인스턴스이다→ 벡터DB", 노드 공유는 "공유: FAISS" */
export function formatRelation(r: RouteRelation): string {
  return r.p === '공유' ? `공유: ${r.s}` : `${r.s} —${r.p}→ ${r.o}`
}
