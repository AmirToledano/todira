import { test, expect } from 'claude-code/testing'

import { isRtlLine, isolateRtl } from './format'

const RLI = '⁧'
const PDI = '⁩'

test('detects right-to-left lines', () => {
  expect(isRtlLine('שלום עולם')).toBe(true)
  expect(isRtlLine('مرحبا بالعالم')).toBe(true)
  expect(isRtlLine('hello world')).toBe(false)
  expect(isRtlLine('12345 ...')).toBe(false)
  expect(isRtlLine('שלום hello')).toBe(true)
  expect(isRtlLine('run the tests עכשיו')).toBe(false)
})

test('wraps a Hebrew line and leaves English alone', () => {
  expect(isolateRtl('שלום עולם.')).toBe(`${RLI}שלום עולם.${PDI}`)
  expect(isolateRtl('plain english')).toBe('plain english')
})

test('keeps the markdown marker first', () => {
  expect(isolateRtl('- פריט ראשון')).toBe(`- ${RLI}פריט ראשון${PDI}`)
  expect(isolateRtl('1. שלב')).toBe(`1. ${RLI}שלב${PDI}`)
  expect(isolateRtl('## כותרת')).toBe(`## ${RLI}כותרת${PDI}`)
  expect(isolateRtl('> ציטוט')).toBe(`> ${RLI}ציטוט${PDI}`)
})

test('skips code fences, table rows, indented code and blank lines', () => {
  const text = ['שלום', '```', 'שלום בתוך קוד', '```', '| עמודה | עמודה |', '    קוד', '', 'סוף'].join('\n')
  const out = isolateRtl(text).split('\n')
  expect(out[0]).toBe(`${RLI}שלום${PDI}`)
  expect(out[2]).toBe('שלום בתוך קוד')
  expect(out[4]).toBe('| עמודה | עמודה |')
  expect(out[5]).toBe('    קוד')
  expect(out[6]).toBe('')
  expect(out[7]).toBe(`${RLI}סוף${PDI}`)
})

test('is idempotent', () => {
  const once = isolateRtl('שלום עולם')
  expect(isolateRtl(once)).toBe(once)
})
