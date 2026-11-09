import { useEffect, useRef, useState } from 'react'

// 진행률을 알 수 없는 단건 LLM 작업의 예상 소요 시간(초) — 이 시간에 90%까지 차고, 넘으면 99% 쪽으로 천천히 다가간다
export const EXPECTED_SECONDS = {
  summarize: 20,        // AI 요약
  graphNote: 20,        // 노트 하나 지식 그래프 추출
  keywordNote: 10,      // 노트 하나 AI 키워드 추출
  pythonNote: 3,        // 노트 하나 파이썬 키워드 추출
}

interface ProgressBarProps {
  label: string
  percent: number       // 0~100
  detail?: string       // 오른쪽 보조 문구 (예: "24/577 · 약 70분")
}

export function ProgressBar({ label, percent, detail }: ProgressBarProps) {
  const p = Math.max(0, Math.min(100, percent))
  return (
    <div className="sn-progress" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(p)}>
      <div className="sn-progress-head">
        <span>{label}</span>
        <span>{detail ?? `${Math.round(p)}%`}</span>
      </div>
      <div className="sn-progress-track">
        <div className="sn-progress-fill" style={{ width: `${p}%` }} />
      </div>
    </div>
  )
}

/** active인 동안 예상 시간 기준 %를 돌려준다 (실제 진행과는 무관한 추정). 끝나면 호출 쪽에서 100%를 보여 준다. */
export function useEstimatedProgress(active: boolean, expectedSeconds: number): number {
  const [percent, setPercent] = useState(0)
  const startRef = useRef(0)
  useEffect(() => {
    if (!active) return
    startRef.current = performance.now()
    setPercent(0)
    const timer = setInterval(() => {
      const t = (performance.now() - startRef.current) / 1000
      const e = expectedSeconds
      setPercent(t < e ? (90 * t) / e : 90 + 9 * (1 - Math.exp(-(t - e) / e)))
    }, 250)
    return () => clearInterval(timer)
  }, [active, expectedSeconds])
  return percent
}

/** 남은 개수와 관측한 처리 속도로 남은 시간을 문구로 — 속도를 아직 모르면 null */
export function etaText(remaining: number, perMinute: number | null): string | null {
  if (!perMinute || perMinute <= 0) return null
  const minutes = Math.ceil(remaining / perMinute)
  return minutes >= 60 ? `약 ${Math.floor(minutes / 60)}시간 ${minutes % 60}분` : `약 ${minutes}분`
}
