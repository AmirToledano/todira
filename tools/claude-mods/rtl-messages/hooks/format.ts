// Pure helpers (no engine calls) so the tests can run them directly.

const RLI = '⁧' // right-to-left isolate: the line's own base direction becomes RTL
const PDI = '⁩' // pop directional isolate

const RTL_LETTER = /[֐-׿؀-ۿݐ-ݿיִ-﷿ﹰ-﻿]/
const ANY_LETTER = /\p{L}/u

// Markdown that must stay the first thing on its line for the renderer to see it: list markers, quotes, headings.
const MARKDOWN_PREFIX = /^(?:\s*(?:[-*+]\s+|\d+[.)]\s+|>\s*|#{1,6}\s+))*/

/** True when the line reads right-to-left: its first letter is Hebrew/Arabic, or RTL letters outnumber the rest. */
export function isRtlLine(line: string): boolean {
  let rtl = 0
  let other = 0
  let first: 'rtl' | 'other' | null = null
  for (const ch of line) {
    if (!ANY_LETTER.test(ch)) continue
    const isRtl = RTL_LETTER.test(ch)
    if (first === null) first = isRtl ? 'rtl' : 'other'
    if (isRtl) rtl += 1
    else other += 1
  }
  if (rtl === 0) return false

  return first === 'rtl' || rtl >= other
}

/**
 * Wraps every right-to-left line of a markdown text in an RTL isolate, so punctuation, numbers and embedded English land
 * on the right side. Code fences, table rows, indented code and blank lines are left alone, and the markdown marker
 * that opens a line (list, quote, heading) stays first.
 */
export function isolateRtl(text: string): string {
  let inFence = false

  return text
    .split('\n')
    .map(line => {
      if (/^\s*(```|~~~)/.test(line)) {
        inFence = !inFence

        return line
      }
      if (inFence || line.trim() === '' || /^\s*\|/.test(line)) return line

      const prefix = (MARKDOWN_PREFIX.exec(line) ?? [''])[0]
      const rest = line.slice(prefix.length)
      const isIndentedCode = prefix === '' && /^( {4}|\t)/.test(line)
      if (isIndentedCode || rest.startsWith(RLI) || !isRtlLine(rest)) return line

      return `${prefix}${RLI}${rest}${PDI}`
    })
    .join('\n')
}
