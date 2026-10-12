import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import { PDI, RLI, hasRtl, layout } from './layout'
import type { Block, Span } from './layout'
import { applyRtl } from './rtl'

const STORE_KEY = 'isEnabled'
const isEnabled = atom({ plugin: 'rtl', key: 'isEnabled' } as const, true)

const USAGE = '/rtl on | off | toggle'

// The app surfaces (desktop, mobile, VS Code) lay text out themselves: there a Hebrew message is redrawn as
// right-aligned rows (see layout.ts). The terminal honours bidi marks, so there it keeps the engine's own drawing.
type Ui = {
  Box: (props: Record<string, unknown>) => unknown
  Text: (props: Record<string, unknown>) => unknown
  Markdown: (props: Record<string, unknown>) => unknown
}

function spanNode(t: Ui, s: Span): unknown {
  if (!s.bold && !s.link && !s.code) return s.text
  return t.Text({ bold: s.bold || undefined, underline: s.link || undefined, italic: s.code || undefined, children: s.text })
}

function blockNode(t: Ui, b: Block, i: number): unknown {
  if (b.kind === 'md') {
    return t.Box({ marginTop: b.gapBefore ? 1 : 0, children: t.Markdown({ text: b.text }) })
  }
  const rows = b.lines.map((line, j) =>
    t.Box({
      flexDirection: 'row',
      justifyContent: 'flex-end',
      paddingRight: b.indent * 2 + (j > 0 ? b.hanging : 0),
      children: t.Text({ bold: b.heading || undefined, children: [RLI, ...line.map(s => spanNode(t, s)), PDI] }),
    }),
  )
  return t.Box({ flexDirection: 'column', marginTop: b.gapBefore ? 1 : 0, children: rows })
}

async function beat($: { fs: { read: (p: string) => Promise<unknown>; write: (p: string, t: string) => Promise<void> } }, surface: string, columns: number | undefined) {
  if (seen.has(surface)) return
  seen.add(surface)
  try {
    let prev = ''
    try { prev = String(await $.fs.read(HEARTBEAT)) } catch {}
    await $.fs.write(HEARTBEAT, `${prev}drawing on ${surface}, ${columns ?? '?'} columns, ${new Date().toISOString()}\n`)
  } catch {}
}

export function drawRtl(t: Ui, text: string, columns: number | undefined): unknown {
  const width = Math.max(20, Math.floor((columns ?? 80) * 0.85) - 2)
  const blocks = layout(text, width)
  return t.Box({ flexDirection: 'column', width: '100%', children: blocks.map((b, i) => blockNode(t, b, i)) })
}

// One line per load and per surface, so a session can tell from outside whether the mod runs and where it draws.
const HEARTBEAT = '/tmp/rtl-mod-heartbeat.txt'
const seen = new Set<string>()

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    try { await $.fs.write(HEARTBEAT, `loaded ${new Date().toISOString()}\n`) } catch {}
    const saved = await $.store.get(STORE_KEY)

    if (typeof saved === 'boolean') {
      await update($, isEnabled, () => saved)
    }

    await $.command.register({
      name: 'rtl',
      description: 'Show messages right-to-left: /rtl on, /rtl off, or /rtl to toggle',
    })

    return next(e)
  })

  on('command.run', { command: 'rtl' }, async ($, e) => {
    const word = (e.args ?? '').trim().toLowerCase()
    const current = await read($, isEnabled)
    const next = word === '' || word === 'toggle' ? !current : word === 'on' ? true : word === 'off' ? false : null

    if (next === null) {
      return { text: `RTL is ${current ? 'on' : 'off'}. Use ${USAGE}.` }
    }

    await update($, isEnabled, () => next)
    await $.store.set(STORE_KEY, next)

    return { text: `RTL is ${next ? 'on' : 'off'}.` }
  })

  // The person's own messages, as the transcript draws them (the stored message is not changed).
  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    await beat($, e.surface, e.viewport?.columns)
    if (!(await read($, isEnabled)) || !hasRtl(e.props.text)) {
      return next(e)
    }
    if (e.surface === 'terminal') {
      const text = applyRtl(e.props.text)
      return text === e.props.text ? next(e) : next({ ...e, props: { ...e.props, text } })
    }
    // a collapsed row (one dim line naming another sender) keeps the engine's drawing
    if (!e.props.isExpanded && e.props.from) {
      return next(e)
    }
    return drawRtl($.ui.resolve(e) as unknown as Ui, e.props.text, e.viewport?.columns) as never
  })

  // Claude's answers, block by block.
  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    await beat($, e.surface, e.viewport?.columns)
    if (!(await read($, isEnabled)) || !hasRtl(e.props.text) || e.props.isSummary) {
      return next(e)
    }
    if (e.surface === 'terminal') {
      const text = applyRtl(e.props.text)
      return text === e.props.text ? next(e) : next({ ...e, props: { ...e.props, text } })
    }
    return drawRtl($.ui.resolve(e) as unknown as Ui, e.props.text, e.viewport?.columns) as never
  })
}
