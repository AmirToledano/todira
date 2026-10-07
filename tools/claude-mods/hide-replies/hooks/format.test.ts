import { test, expect } from 'claude-code/testing'

import { hiddenLine } from './format'

test('the stand-in line counts lines and characters, never shows the text', () => {
  expect(hiddenLine('one')).toBe('▸ reply hidden (1 line, 3 chars)')
  expect(hiddenLine('a\n\nb\nc')).toBe('▸ reply hidden (3 lines, 6 chars)')
  expect(hiddenLine('secret')).not.toContain('secret')
})
