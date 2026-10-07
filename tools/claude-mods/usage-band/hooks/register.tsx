import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Snap } from '../types'
import { bar, colorFor, labelFor, untilReset, whole } from './format'

const snap = atom({ plugin: 'usage-band', key: 'snap' } as const, null)

export const register: Register = on => {
  // The engine pushes a measurement after each turn and whenever a limit window moves a whole point.
  on('session.measure', async ($, e, next) => {
    const value: Snap = {
      limits: e.rateLimits.map(l => ({ kind: l.kind, percentUsed: l.percentUsed, resetsAt: l.resetsAt })),
      contextPercent: e.context.percent ?? null,
      costUsd: e.cost ? e.cost.usd : null,
    }
    await update($, snap, () => value)

    return next(e)
  })

  // A fresh start (or reload) has no measurement yet: read the same figures once so the row is not empty.
  on('session.start', async ($, e, next) => {
    try {
      const u = await $.session.usage()
      const value: Snap = {
        limits: u.rateLimits.map(l => ({ kind: l.kind, percentUsed: l.percentUsed, resetsAt: l.resetsAt })),
        contextPercent: u.context.percent ?? null,
        costUsd: u.cost ? u.cost.usd : null,
      }
      await update($, snap, () => value)
    } catch {
      // No reading yet: the row simply stays hidden until the first measurement.
    }

    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, snap)
    // Draw what the plugins beneath draw (another mod's button, say) and add this row to it, never replace it.
    const below = await next(e)

    // A survey owns the band while it is up; with no figures at all there is nothing true to show.
    if (e.props.hasSurvey || s === null) return below
    if (s.limits.length === 0 && s.contextPercent === null && s.costUsd === null) return below

    const now = await $.clock.now()
    const { Box, Text } = $.ui.resolve(e)
    const rows = []

    for (const l of s.limits) {
      const used = whole(l.percentUsed)
      const left = Math.max(0, 100 - used)
      const reset = untilReset(l.resetsAt, now)
      rows.push(
        <Box key={l.kind}>
          <Text bold>{labelFor(l.kind)} </Text>
          <Text color={colorFor(l.percentUsed)}>{bar(l.percentUsed)}</Text>
          <Text> used {used}% · left {left}%</Text>
          {reset ? <Text dimColor> · resets {reset}</Text> : null}
          <Text dimColor>{'   '}</Text>
        </Box>,
      )
    }

    if (s.contextPercent !== null) {
      const used = whole(s.contextPercent)
      rows.push(
        <Box key="context">
          <Text bold>ctx </Text>
          <Text color={colorFor(s.contextPercent)}>{bar(s.contextPercent)}</Text>
          <Text> {used}% full · {Math.max(0, 100 - used)}% left</Text>
          <Text dimColor>{'   '}</Text>
        </Box>,
      )
    }

    if (s.costUsd !== null) {
      rows.push(
        <Box key="cost">
          <Text bold>cost </Text>
          <Text>${s.costUsd.toFixed(2)}</Text>
        </Box>,
      )
    }

    return (
      <Box flexDirection="column">
        {below}
        <Box>{rows}</Box>
      </Box>
    )
  })
}
