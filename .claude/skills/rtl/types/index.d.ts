// Whether messages are drawn right-to-left. The drawing reads it, so /rtl redraws the transcript.
export type RtlEnabled = boolean

declare module 'claude-code' {
  interface PluginState {
    rtl: { isEnabled: boolean }
  }
}
