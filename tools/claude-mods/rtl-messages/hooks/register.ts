import type { Register } from 'claude-code'

import { isolateRtl } from './format'

const KEY = 'enabled'

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'rtl',
      description: 'Toggle right-to-left drawing of Hebrew and Arabic messages (on by default)',
    })

    return next(e)
  })

  on('command.run', { command: 'rtl' }, async $ => {
    const isOn = (await $.store.get(KEY)) !== false
    await $.store.set(KEY, !isOn)
    $.ui.invalidate('ui.render')

    return { text: isOn ? 'RTL drawing is off.' : 'RTL drawing is on.' }
  })

  // Rewriting `text` redraws the row with the engine's own styling (the prompt marker, markdown, colours); only the
  // text changes, and the stored message is untouched.
  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    if ((await $.store.get(KEY)) === false) return next(e)
    const text = isolateRtl(e.props.text)

    return text === e.props.text ? next(e) : next({ ...e, props: { ...e.props, text } })
  })

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    if ((await $.store.get(KEY)) === false) return next(e)
    const text = isolateRtl(e.props.text)

    return text === e.props.text ? next(e) : next({ ...e, props: { ...e.props, text } })
  })
}
