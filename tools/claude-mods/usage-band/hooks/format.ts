// Pure helpers: no engine calls, so the tests can run them directly.

export const BAR_WIDTH = 10

/** 0-100 (clamped) -> a bar of BAR_WIDTH cells, filled in proportion to `percent`. */
export function bar(percent: number): string {
  const p = Math.max(0, Math.min(100, percent))
  const filled = Math.round((p / 100) * BAR_WIDTH)
  return '█'.repeat(filled) + '░'.repeat(BAR_WIDTH - filled)
}

/** Theme colour by how full the window is: calm, getting close, nearly out. */
export function colorFor(percentUsed: number): 'success' | 'warning' | 'error' {
  if (percentUsed >= 90) return 'error'
  if (percentUsed >= 70) return 'warning'
  return 'success'
}

/** "2h13m", "45m", "3d4h" until `resetsAt`; '' when unknown or already past. */
export function untilReset(resetsAt: string | undefined, nowMs: number): string {
  if (!resetsAt) return ''
  const ms = Date.parse(resetsAt) - nowMs
  if (!Number.isFinite(ms) || ms <= 0) return ''
  const minutes = Math.floor(ms / 60_000)
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const mins = minutes % 60
  if (days > 0) return `${days}d${hours}h`
  if (hours > 0) return `${hours}h${String(mins).padStart(2, '0')}m`
  return `${mins}m`
}

const LABELS: Record<string, string> = { five_hour: '5h', seven_day: '7d', spend_limit: '$cap' }

export function labelFor(kind: string): string {
  return LABELS[kind] ?? kind
}

/** Whole percent for display; one decimal is noise on a status row. */
export function whole(percent: number): number {
  return Math.round(percent)
}

type LimitIn = { kind: string; percentUsed: number; resetsAt?: string }
type SnapIn = { limits: LimitIn[]; contextPercent: number | null; costUsd: number | null }

/** One plain line for where nothing draws: "5h used 62% (left 38%, resets 2h13m) | 7d ... | ctx ... | cost $0.42". */
export function textLine(s: SnapIn, nowMs: number): string {
  const parts: string[] = []
  for (const l of s.limits) {
    const used = whole(l.percentUsed)
    const reset = untilReset(l.resetsAt, nowMs)
    parts.push(`${labelFor(l.kind)} used ${used}% (left ${Math.max(0, 100 - used)}%${reset ? `, resets ${reset}` : ''})`)
  }
  if (s.contextPercent !== null) {
    const used = whole(s.contextPercent)
    parts.push(`ctx ${used}% full (${Math.max(0, 100 - used)}% left)`)
  }
  if (s.costUsd !== null) parts.push(`cost $${s.costUsd.toFixed(2)}`)

  return parts.length > 0 ? parts.join(' | ') : 'No usage figures yet (they appear after the first reply).'
}
