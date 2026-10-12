import { expect, mock, test } from 'claude-code/testing'

import { RLM, applyRtl, hasRtl } from './rtl'

test('plain English is left exactly as it is', () => {
  const text = 'Hello there.\n\n- one\n- two'
  expect(applyRtl(text)).toBe(text)
  expect(hasRtl(text)).toBe(false)
})

test('a Hebrew line gets one right-to-left mark at its start', () => {
  expect(applyRtl('שלום עולם')).toBe(`${RLM}שלום עולם`)
})

test('a Hebrew line that opens with English, a number or a URL still becomes right-to-left', () => {
  expect(applyRtl('Todira היא שירות')).toBe(`${RLM}Todira היא שירות`)
  expect(applyRtl('123 דירות חדשות')).toBe(`${RLM}123 דירות חדשות`)
  expect(applyRtl('https://todira.app הוא האתר')).toBe(`${RLM}https://todira.app הוא האתר`)
})

test('the mark goes after the markdown that opens the line, so the markdown still works', () => {
  expect(applyRtl('- פריט')).toBe(`- ${RLM}פריט`)
  expect(applyRtl('3. פריט')).toBe(`3. ${RLM}פריט`)
  expect(applyRtl('  * [ ] משימה')).toBe(`  * [ ] ${RLM}משימה`)
  expect(applyRtl('## כותרת')).toBe(`## ${RLM}כותרת`)
  expect(applyRtl('> ציטוט')).toBe(`> ${RLM}ציטוט`)
  expect(applyRtl('> - ציטוט ברשימה')).toBe(`> - ${RLM}ציטוט ברשימה`)
})

test('each Hebrew line is marked, English lines in the same message are not', () => {
  expect(applyRtl('שורה אחת\nplain english\nעוד שורה')).toBe(`${RLM}שורה אחת\nplain english\n${RLM}עוד שורה`)
})

test('fenced code is never touched, and the text after the fence is marked again', () => {
  const text = 'הנה הקוד:\n```ts\nconst שם = "ערך"\n```\nוזהו.'
  expect(applyRtl(text)).toBe(`${RLM}הנה הקוד:\n\`\`\`ts\nconst שם = "ערך"\n\`\`\`\n${RLM}וזהו.`)
  const tilde = '~~~\nשלום\n~~~'
  expect(applyRtl(tilde)).toBe(tilde)
})

test('a longer fence is closed only by an equal or longer fence of the same kind', () => {
  const text = 'ראשון\n````\nשלום\n```\nעדיין קוד\n````\nאחרון'
  expect(applyRtl(text)).toBe(`${RLM}ראשון\n\`\`\`\`\nשלום\n\`\`\`\nעדיין קוד\n\`\`\`\`\n${RLM}אחרון`)
})

test('table rows are left alone', () => {
  const table = '| שם | ערך |\n| --- | --- |\n| א | ב |'
  expect(applyRtl(table)).toBe(table)
})

test('applying it twice changes nothing more', () => {
  const once = applyRtl('- שלום\n## כותרת\nטקסט')
  expect(applyRtl(once)).toBe(once)
})

test('Arabic is handled the same way', () => {
  expect(applyRtl('مرحبا بالعالم')).toBe(`${RLM}مرحبا بالعالم`)
})

test('an empty message and a message of only spaces are unchanged', () => {
  expect(applyRtl('')).toBe('')
  expect(applyRtl('   \n')).toBe('   \n')
})

test('/rtl switches the mod off and on and says which it is', async ($, on) => {
  mock.store(on)

  const turnedOff = await $.command.run({ command: 'rtl', args: 'off' })
  expect(turnedOff.text).toBe('RTL is off.')

  const turnedOn = await $.command.run({ command: 'rtl', args: 'on' })
  expect(turnedOn.text).toBe('RTL is on.')

  const toggled = await $.command.run({ command: 'rtl' })
  expect(toggled.text).toBe('RTL is off.')

  const unknown = await $.command.run({ command: 'rtl', args: 'sideways' })
  expect(unknown.text).toContain('Use /rtl on | off | toggle')
})
