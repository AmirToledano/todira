// Turns a message's text into text a renderer lays out right-to-left.
//
// A renderer decides a paragraph's direction from its first "strong" character. A Hebrew message that opens with a
// word in English, a number, a URL, a code span or an emoji is laid out left-to-right, so it sits against the left
// edge with its punctuation in the wrong place. The fix is one invisible right-to-left mark (U+200F, RLM) at the
// start of each line that holds Hebrew or Arabic: it is a strong right-to-left character, so the paragraph is
// right-to-left whatever follows it. Nothing visible changes and the stored message is never touched.
//
// What is left alone, because a mark there would break it: fenced code blocks, table rows, and the markdown that
// opens a line (quote marks, list bullets and numbers, task boxes, heading hashes) — the mark goes after those.

export const RLM = '‏'

// Hebrew, Arabic (+ supplement and extended), Hebrew/Arabic presentation forms.
const RTL_LETTER = /[֐-׿؀-ۿݐ-ݿࢠ-ࣿיִ-﷿ﹰ-﻿]/

// A mark that already fixes the direction: RLM, ALM, RLE, RLO, RLI.
const ALREADY_MARKED = /^[‏؜‫‮⁧]/

const FENCE = /^\s{0,3}(`{3,}|~{3,})/
const TABLE_ROW = /^\s*\|/
// quote marks, a list bullet or number, a task box, a heading: the line's markdown, kept in front of the mark.
const MARKDOWN_PREFIX = /^(\s*(?:>\s?)*(?:(?:[-*+]|\d{1,9}[.)])\s+(?:\[[ xX]\]\s+)?)?(?:#{1,6}\s+)?)/

export function hasRtl(text: string): boolean {
  return RTL_LETTER.test(text)
}

export function applyRtl(text: string): string {
  if (!hasRtl(text)) {
    return text
  }

  let fence: string | null = null
  const lines = text.split('\n')

  return lines
    .map(line => {
      const opening = FENCE.exec(line)

      if (fence !== null) {
        if (opening !== null && opening[1][0] === fence[0] && opening[1].length >= fence.length) {
          fence = null
        }

        return line
      }

      if (opening !== null) {
        fence = opening[1]

        return line
      }

      if (TABLE_ROW.test(line) || !RTL_LETTER.test(line)) {
        return line
      }

      const prefix = MARKDOWN_PREFIX.exec(line)?.[1] ?? ''
      const rest = line.slice(prefix.length)

      return ALREADY_MARKED.test(rest) ? line : prefix + RLM + rest
    })
    .join('\n')
}
