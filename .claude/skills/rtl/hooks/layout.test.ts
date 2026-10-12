import { expect, test } from 'claude-code/testing'

import { LRI, PDI, layout, parseInline, wrapSpans } from './layout'

test('inline bold, code and links become styled spans', () => {
  expect(parseInline('שלום **עולם** ו-`קוד` ו[קישור](https://x.y)')).toEqual([
    { text: 'שלום ' },
    { text: 'עולם', bold: true },
    { text: ' ו-' },
    { text: 'קוד', code: true },
    { text: ' ו' },
    { text: 'קישור', link: true },
  ])
})

test('wrapping keeps words whole and stays within the width', () => {
  const lines = wrapSpans([{ text: 'אחת שתיים שלוש ארבע חמש שש שבע' }], 12).map(l => l.map(s => s.text).join(''))
  expect(lines).toEqual(['אחת שתיים', 'שלוש ארבע', 'חמש שש שבע'])
})

test('a Hebrew paragraph becomes a right-to-left block; English and code stay markdown', () => {
  const blocks = layout('שלום לך\n\nplain english\n\n```ts\nconst a = 1\n```', 40)
  expect(blocks.map(b => b.kind)).toEqual(['rtl', 'md', 'md'])
})

test('bullets and numbers sit at the start of the right-to-left line', () => {
  const [bullet, numbered] = layout('- פריט ראשון\n2. פריט שני', 40)
  expect(bullet.kind === 'rtl' && bullet.lines[0][0].text.startsWith('• ')).toBe(true)
  expect(numbered.kind === 'rtl' && numbered.lines[0][0].text.startsWith(`${LRI}2.${PDI} `)).toBe(true)
})

for (const surface of ['desktop', 'mobile', 'vscode'] as const) {
  test(`an assistant reply in Hebrew draws as right-aligned rows on ${surface}`, async $ => {
    const ui = await $.ui.mount({
      plugin: 'rtl',
      surface,
      component: 'AssistantMessage',
      props: { text: '## כותרת\n\nשלום, זו **תשובה** בעברית.\n\n- פריט\n\n```\ncode\n```', isFirstOfReply: true },
      viewport: { columns: 60, rows: 40 },
    })
    const tree = JSON.stringify(await ui.drawn())
    expect(tree.includes('flex-end')).toBe(true)
    expect(tree.includes('Markdown')).toBe(true)
  })
}

test('an English reply keeps the engine drawing on desktop', async ($, on) => {
  on('ui.render', { component: 'AssistantMessage' }, ($e, e) => $e.ui.resolve(e).Text({ children: 'engine' }))
  const ui = await $.ui.mount({
    plugin: 'rtl',
    surface: 'desktop',
    component: 'AssistantMessage',
    props: { text: 'Just English here.', isFirstOfReply: true },
    viewport: { columns: 60, rows: 40 },
  })
  const tree = JSON.stringify(await ui.drawn())
  expect(tree.includes('flex-end')).toBe(false)
  expect(tree.includes('engine')).toBe(true)
})
