/** The one dim line that stands in for a hidden reply: what it was, never the text itself. */
export function hiddenLine(text: string): string {
  const lines = text.split('\n').filter(l => l.trim() !== '').length
  const chars = text.length

  return `▸ reply hidden (${lines} ${lines === 1 ? 'line' : 'lines'}, ${chars} chars)`
}
