import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import { hiddenLine } from './format'

const hidden = atom({ plugin: 'hide-replies', key: 'hidden' } as const, false)
const STORE_KEY = 'hidden'

export const register: Register = on => {
  // The choice survives a restart: read it back from the store the host keeps across sessions.
  on('session.start', async ($, e, next) => {
    const saved = (await $.store.get(STORE_KEY)) === true
    await update($, hidden, () => saved)

    return next(e)
  })

  // The button joins whatever the band already shows: draw what the plugins beneath draw (the usage row, say), then
  // add the toggle beside it. Nothing here replaces another mod's row.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const below = await next(e)
    if (e.props.hasSurvey) return below

    const isHidden = await read($, hidden)
    const { Box, Button } = $.ui.resolve(e)

    return (
      <Box>
        {below}
        <Button
          key="toggle-replies"
          label={isHidden ? 'Show replies' : 'Hide replies'}
          onPress={async () => {
            const flipped = !(await read($, hidden))
            await update($, hidden, () => flipped)
            await $.store.set(STORE_KEY, flipped)
          }}
        />
      </Box>
    )
  })

  // While hidden, each reply block draws as one dim line. The stored message is untouched: ctrl+o shows it whole.
  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    if (!(await read($, hidden))) return next(e)
    const { Text } = $.ui.resolve(e)

    return <Text dimColor>{hiddenLine(e.props.text)}</Text>
  })
}
