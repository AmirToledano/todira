export type Limit = { kind: string; percentUsed: number; resetsAt?: string }
export type Snap = {
  limits: Limit[]
  contextPercent: number | null
  costUsd: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'usage-band': { snap: Snap | null }
  }
}
