// Lays a Hebrew message out right-to-left for surfaces that draw our own tree (the desktop and mobile apps).
//
// Those surfaces decide a paragraph's alignment themselves, and an element tree has no direction or text-align
// prop, so invisible marks alone leave Hebrew against the left edge. What does work everywhere is a row pushed to
// the right edge (`justifyContent: 'flex-end'`). So each paragraph is wrapped here into lines that fit the
// viewport, every line becomes its own right-aligned row, and the line's text sits inside a right-to-left isolate
// (RLI ... PDI) so its punctuation, numbers and English words fall in the right order.
//
// Blocks with no Hebrew (English text, code fences, tables) are handed back as markdown, drawn as the app draws it.

export const RLI = '⁧'
export const LRI = '⁦'
export const PDI = '⁩'

const RTL_LETTER = /[֐-׿؀-ۿݐ-ݿࢠ-ࣿיִ-﷿ﹰ-﻿]/

export type Span = { text: string; bold?: boolean; code?: boolean; link?: boolean }

export type Block =
  | { kind: 'rtl'; lines: Span[][]; heading: boolean; indent: number; hanging: number; gapBefore: boolean }
  | { kind: 'md'; text: string; gapBefore: boolean }

export function hasRtl(text: string): boolean {
  return RTL_LETTER.test(text)
}

// **bold**, `code` and [text](url) inside a line; everything else stays as written.
export function parseInline(text: string): Span[] {
  const spans: Span[] = []
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\([^)]+\)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) spans.push({ text: text.slice(last, m.index) })
    if (m[1] !== undefined) spans.push({ text: m[1], bold: true })
    else if (m[2] !== undefined) spans.push({ text: m[2], code: true })
    else spans.push({ text: m[3], link: true })
    last = m.index + m[0].length
  }
  if (last < text.length) spans.push({ text: text.slice(last) })
  return spans.filter(s => s.text.length > 0)
}

// Greedy word wrap of styled spans into lines of at most `width` characters. A word longer than a line is kept whole.
export function wrapSpans(spans: Span[], width: number): Span[][] {
  const lines: Span[][] = [[]]
  let used = 0
  const push = (piece: Span) => {
    const line = lines[lines.length - 1]
    const prev = line[line.length - 1]
    if (prev && prev.bold === piece.bold && prev.code === piece.code && prev.link === piece.link) prev.text += piece.text
    else line.push({ ...piece })
    used += piece.text.length
  }
  for (const span of spans) {
    const words = span.text.split(/(\s+)/).filter(w => w.length > 0)
    for (const w of words) {
      const isSpace = /^\s+$/.test(w)
      if (isSpace) {
        if (used > 0) push({ ...span, text: ' ' })
        continue
      }
      if (used > 0 && used + w.length > width) {
        const line = lines[lines.length - 1]
        const tail = line[line.length - 1]
        if (tail) tail.text = tail.text.replace(/\s+$/, '')
        lines.push([])
        used = 0
      }
      push({ ...span, text: w })
    }
  }
  return lines.filter(l => l.length > 0)
}

const FENCE = /^\s{0,3}(`{3,}|~{3,})/
const TABLE_ROW = /^\s*\|/
const HEADING = /^\s*(#{1,6})\s+(.*)$/
const BULLET = /^(\s*)(?:>\s?)?([-*+])\s+(?:\[[ xX]\]\s+)?(.*)$/
const NUMBERED = /^(\s*)(\d{1,9})[.)]\s+(.*)$/
const QUOTE = /^\s*>\s?(.*)$/

// Splits a markdown message into blocks: right-to-left paragraphs/list items/headings, and markdown passed through.
export function layout(text: string, width: number): Block[] {
  const blocks: Block[] = []
  const lines = text.split('\n')
  let gap = false
  let md: string[] = []
  let para: string[] = []

  const flushMd = () => {
    if (md.length) {
      blocks.push({ kind: 'md', text: md.join('\n'), gapBefore: gap })
      gap = false
      md = []
    }
  }
  const addRtl = (body: string, opts: { marker?: string; heading?: boolean; indent?: number }) => {
    const spans = parseInline(body)
    const markerSpan: Span[] = opts.marker ? [{ text: opts.marker + ' ' }] : []
    const w = Math.max(16, width - (opts.indent ?? 0) * 2)
    blocks.push({ kind: 'rtl', lines: wrapSpans([...markerSpan, ...spans], w), heading: !!opts.heading, indent: opts.indent ?? 0, hanging: opts.marker ? 2 : 0, gapBefore: gap })
    gap = false
  }
  const flushPara = () => {
    if (!para.length) return
    const body = para.join(' ')
    para = []
    if (hasRtl(body)) {
      flushMd()
      addRtl(body, {})
    } else {
      md.push(body)
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const fence = FENCE.exec(line)
    if (fence) {
      flushPara()
      const block = [line]
      i++
      while (i < lines.length) {
        block.push(lines[i])
        const close = FENCE.exec(lines[i])
        if (close && close[1][0] === fence[1][0] && close[1].length >= fence[1].length) break
        i++
      }
      md.push(...block)
      continue
    }
    if (TABLE_ROW.test(line)) {
      flushPara()
      md.push(line)
      continue
    }
    if (!line.trim()) {
      flushPara()
      flushMd()
      gap = blocks.length > 0
      continue
    }
    const h = HEADING.exec(line)
    const b = BULLET.exec(line)
    const n = NUMBERED.exec(line)
    if (h || b || n) {
      flushPara()
      const body = h ? h[2] : b ? b[3] : n![3]
      if (!hasRtl(body)) {
        md.push(line)
        continue
      }
      flushMd()
      const indent = Math.min(3, Math.floor(((b ?? n)?.[1].length ?? 0) / 2))
      if (h) addRtl(body, { heading: true })
      else if (b) addRtl(body, { marker: '•', indent })
      else addRtl(body, { marker: `${LRI}${n![2]}.${PDI}`, indent })
      continue
    }
    const q = QUOTE.exec(line)
    para.push(q ? q[1] : line)
  }
  flushPara()
  flushMd()
  return blocks
}
