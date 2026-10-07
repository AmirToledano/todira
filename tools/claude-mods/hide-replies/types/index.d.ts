export type HideRepliesMarker = true

declare module 'claude-code' {
  interface PluginState {
    'hide-replies': { hidden: boolean }
  }
}
