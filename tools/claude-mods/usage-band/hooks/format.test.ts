import { test, expect } from 'claude-code/testing'

import { bar, colorFor, untilReset, labelFor, whole } from './format'

test('bar fills in proportion and clamps', () => {
  expect(bar(0)).toBe('░░░░░░░░░░')
  expect(bar(50)).toBe('█████░░░░░')
  expect(bar(100)).toBe('██████████')
  expect(bar(250)).toBe('██████████')
  expect(bar(-5)).toBe('░░░░░░░░░░')
})

test('colour turns warning at 70 and error at 90', () => {
  expect(colorFor(10)).toBe('success')
  expect(colorFor(70)).toBe('warning')
  expect(colorFor(89.9)).toBe('warning')
  expect(colorFor(90)).toBe('error')
})

test('reset countdown reads in days, hours or minutes, blank when unknown', () => {
  const now = Date.parse('2026-10-07T10:00:00Z')
  expect(untilReset('2026-10-07T12:13:00Z', now)).toBe('2h13m')
  expect(untilReset('2026-10-07T10:45:00Z', now)).toBe('45m')
  expect(untilReset('2026-10-10T14:00:00Z', now)).toBe('3d4h')
  expect(untilReset(undefined, now)).toBe('')
  expect(untilReset('2026-10-07T09:00:00Z', now)).toBe('')
})

test('labels and rounding', () => {
  expect(labelFor('five_hour')).toBe('5h')
  expect(labelFor('seven_day')).toBe('7d')
  expect(labelFor('weird')).toBe('weird')
  expect(whole(23.5)).toBe(24)
})
