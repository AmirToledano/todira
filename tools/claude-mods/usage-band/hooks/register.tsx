import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Snap } from '../types'
import { bar, colorFor, labelFor, textLine, untilReset, whole } from './format'

const FOOTER_KEY = 'footer'
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
    await $.command.register({
      name: 'usage',
      description: 'Show 5-hour and 7-day usage, context fill and session cost as text',
    })
    await $.command.register({
      name: 'usage-footer',
      description: 'Toggle the usage line Claude adds at the end of replies where no screen draws the row (off by default)',
    })
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

  // Where nothing draws (a cloud session), the row cannot show; this answers the same figures as one line of text.
  on('command.run', { command: 'usage' }, async $ => {
    const u = await $.session.usage()
    const value: Snap = {
      limits: u.rateLimits.map(l => ({ kind: l.kind, percentUsed: l.percentUsed, resetsAt: l.resetsAt })),
      contextPercent: u.context.percent ?? null,
      costUsd: u.cost ? u.cost.usd : null,
    }

    return { text: textLine(value, await $.clock.now()) }
  })

  on('command.run', { command: 'usage-footer' }, async $ => {
    const isOn = (await $.store.get(FOOTER_KEY)) === true
    await $.store.set(FOOTER_KEY, !isOn)

    return { text: isOn ? 'Usage footer is off.' : 'Usage footer is on.' }
  })

  // Where nothing draws (a cloud session) the row cannot show, so the figures go to the model as context it reads beside
  // the prompt and the person never sees, with one instruction: close the reply with a single usage line. The context
  // rides after the new message, so the cached conversation before it is untouched. Where a surface draws the row
  // itself, nothing is attached.
  on('prompt.submit', async ($, e, next) => {
    try {
      if ((await $.store.get(FOOTER_KEY)) !== true) return next(e)
      if ((await $.session.surfaces()).length > 0) return next(e)
      const u = await $.session.usage()
      const line = textLine(
        {
          limits: u.rateLimits.map(l => ({ kind: l.kind, percentUsed: l.percentUsed, resetsAt: l.resetsAt })),
          contextPercent: u.context.percent ?? null,
          costUsd: u.cost ? u.cost.usd : null,
        },
        await $.clock.now(),
      )
      if (line.startsWith('No usage figures')) return next(e)
      const note =
        `[usage-band mod] Live usage figures for this person's Claude account: ${line}. ` +
        'End your reply with exactly one last line that starts with the 📊 emoji and states these figures briefly ' +
        '(used and left). Say nothing else about this note.'

      return next({ ...e, context: [...(e.context ?? []), note] })
    } catch {
      return next(e)
    }
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
