// 확대했을 때 육각형·팻말을 보일지 정하는 거리 기준.
// 화면 중심점까지의 거리(cam.r)로 정하면 중심점에서 먼 은하는 행성 바로 옆까지 가도 켜지지 않으므로,
// 카메라에서 가장 가까운 행성까지의 거리로 정한다.
export const HEX_FADE = { near: 1500, far: 2200, opacity: 0.75 }

interface Point { x: number; y: number; z: number }

/** 카메라에서 가장 가까운 (타임라인상 존재하는) 행성까지의 거리. 행성이 없으면 Infinity */
export function nearestPlanetDistance(cam: Point, planets: Point[], alive: boolean[]): number {
  let best = Infinity
  for (let i = 0; i < planets.length; i++) {
    if (!alive[i]) continue
    const p = planets[i]
    const d = (p.x - cam.x) ** 2 + (p.y - cam.y) ** 2 + (p.z - cam.z) ** 2
    if (d < best) best = d
  }
  return Math.sqrt(best)
}

/** 거리 → 0(숨김)~1(보임). near 안쪽은 1, far 바깥은 0, 사이는 선형으로 */
export function hexFadeFor(distance: number): number {
  return Math.min(1, Math.max(0, (HEX_FADE.far - distance) / (HEX_FADE.far - HEX_FADE.near)))
}
